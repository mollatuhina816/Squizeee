"""Bounded, non-executing extraction of document structure and visual evidence."""
import base64
import io
import json
import re
import zipfile
from xml.etree import ElementTree as ET
from PIL import Image, UnidentifiedImageError

SUPPORTED = {'pdf','docx','pptx','xlsx','csv','txt','json'}


def checked_archive(data, *, max_entries=3000, maximum=80_000_000):
    archive = zipfile.ZipFile(io.BytesIO(data))
    entries = archive.infolist()
    if len(entries) > max_entries or sum(e.file_size for e in entries) > maximum:
        archive.close(); raise ValueError('Document expands beyond the permitted size')
    if any(e.flag_bits & 1 for e in entries):
        archive.close(); raise ValueError('Encrypted documents are not supported')
    return archive


def detect_format(data, filename='', expected=None):
    extension = filename.rsplit('.',1)[-1].lower() if '.' in filename else expected
    if data.startswith(b'%PDF-'): detected = 'pdf'
    elif data.startswith(b'PK'):
        with checked_archive(data) as archive:
            names = set(archive.namelist())
            detected = next((fmt for marker,fmt in [('ppt/presentation.xml','pptx'),('word/document.xml','docx'),('xl/workbook.xml','xlsx')] if marker in names), None)
        if not detected: raise ValueError('Unsupported ZIP document')
    elif data.startswith(bytes.fromhex('D0CF11E0A1B11AE1')) or (extension and extension not in SUPPORTED):
        return 'legacy'
    else:
        text = data.decode('utf-8-sig')
        if '\x00' in text: raise ValueError('Upload a readable UTF-8 text document')
        try: json.loads(text); detected = 'json'
        except ValueError: detected = 'csv' if extension == 'csv' else 'txt'
    if extension in SUPPORTED and extension != detected:
        raise ValueError(f'File contents are {detected.upper()}, but the filename declares {extension.upper()}')
    return detected


def table_text(table):
    lines=[]
    for row in table:
        cells=[c.strip() for c in row if c.strip()]
        if cells and re.fullmatch(r'\(?[A-T][).:]?',cells[0],re.I) and len(cells)>1:
            lines.append(cells[0].strip('().:')+') '+' '.join(cells[1:]))
        else:lines.extend(cells)
    return '\n'.join(lines)


def image_part(blob):
    try:
        with Image.open(io.BytesIO(blob)) as image:
            if image.width * image.height > 20_000_000: raise ValueError('Embedded image exceeds 20 megapixels')
            image.thumbnail((1800,1800))
            output=io.BytesIO();image.convert('RGB').save(output,format='JPEG',quality=85)
            return {'mime_type':'image/jpeg','data':base64.b64encode(output.getvalue()).decode()}
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError):
        return None


def paragraph_structure(frame):
    paragraphs=[]
    for paragraph in frame.paragraphs:
        runs=[]
        for run in paragraph.runs:
            color=run.font.color
            try:rgb=str(color.rgb) if color.type else None
            except (AttributeError,TypeError):rgb=None
            try:theme=str(color.theme_color) if color.type and not rgb else None
            except (AttributeError,TypeError):theme=None
            runs.append({'text':run.text,'color':rgb,'theme_color':theme,'bold':run.font.bold,'size':run.font.size})
        paragraphs.append({'text':paragraph.text,'level':paragraph.level,'runs':runs})
    return paragraphs


def extract_structure(data, format, filename=''):
    if format == 'pptx':
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        with checked_archive(data): pass
        deck=Presentation(io.BytesIO(data))
        if len(deck.slides)>100: raise ValueError('Maximum 100 PowerPoint slides')
        sections=[];image_bytes=0
        for number,slide in enumerate(deck.slides,1):
            blocks=[];images=[];warnings=[]
            def walk(shapes, parent=None):
                nonlocal image_bytes
                for shape in shapes: # Preserve z-order as well as coordinates.
                    block={'shape_id':shape.shape_id,'parent':parent,'x':shape.left,'y':shape.top,'width':shape.width,'height':shape.height,'kind':str(shape.shape_type)}
                    if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
                        try:
                            block['geometry']=str(shape.auto_shape_type)
                        except ValueError:
                            block['geometry']=shape._element.spPr.prstGeom.get('prst')
                    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                        block['group_transform']=ET.tostring(shape._element,encoding='unicode')[:1500]
                        blocks.append(block);walk(shape.shapes,shape.shape_id);continue
                    if shape.has_text_frame:
                        block['text']=shape.text
                        block['is_title']=slide.shapes.title is not None and shape.shape_id == slide.shapes.title.shape_id
                        block['paragraphs']=paragraph_structure(shape.text_frame)
                    if shape.has_table:
                        block['table']=[[cell.text for cell in row.cells] for row in shape.table.rows]
                        block['table_cells']=[{'row':r,'column':c,'paragraphs':paragraph_structure(cell.text_frame)}
                                              for r,row in enumerate(shape.table.rows) for c,cell in enumerate(row.cells)]
                        block['text']=table_text(block['table'])
                    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                        if len(images)>=8: warnings.append('More than eight images on this slide; render the slide for full visual review')
                        else:
                            part=image_part(shape.image.blob)
                            if part:
                                image_bytes+=len(part['data'])
                                if image_bytes>12_000_000: raise ValueError('Document images exceed the vision budget; split the document')
                                images.append({**part,'shape_id':shape.shape_id})
                            else: warnings.append('An embedded image cannot be decoded; slide rendering is required')
                    if not shape.has_text_frame and not shape.has_table and shape.shape_type not in {MSO_SHAPE_TYPE.PICTURE,MSO_SHAPE_TYPE.AUTO_SHAPE,MSO_SHAPE_TYPE.LINE}:
                        warnings.append(f'Shape {shape.shape_id} may contain diagrams or unsupported visual content')
                    blocks.append(block)
            walk(slide.shapes)
            notes=slide.notes_slide.notes_text_frame.text if slide.has_notes_slide and slide.notes_slide.notes_text_frame else ''
            ordered=sorted((b for b in blocks if b.get('text')),key=lambda b:(not b.get('is_title',False),b['y'],b['x']))
            text='\n'.join(b['text'] for b in ordered)
            if notes.strip(): text+='\n'+notes
            if len(text)>50000: raise ValueError('A slide contains too much text')
            sections.append({'number':number,'label':f'Slide {number}','text':text,'blocks':blocks,'notes':notes,'images':images,'warnings':warnings})
        # Repeated bottom-of-slide text is retained as context rather than being
        # appended to options or answer evidence by the text parser.
        footer_counts={}
        for section in sections:
            for block in section['blocks']:
                if block.get('text') and block['y']>=deck.slide_height*.85:
                    key=block['text'].strip()
                    footer_counts.setdefault(key,set()).add(section['number'])
        for section in sections:
            for block in section['blocks']:
                if block.get('text') and block['y']>=deck.slide_height*.85 and len(footer_counts.get(block['text'].strip(),set()))>=2:
                    block['is_footer']=True
        return sections
    if format == 'docx':
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        with checked_archive(data) as archive:
            root=ET.fromstring(archive.read('word/document.xml'))
            blocks=[];images=[];warnings=[]
            body=root.find('w:body',ns)
            for child in body:
                if child.tag.endswith('}p'):
                    blocks.append({'kind':'paragraph','text':''.join(child.itertext()) if not child.findall('.//w:t',ns) else ''.join(t.text or '' for t in child.findall('.//w:t',ns))})
                elif child.tag.endswith('}tbl'):
                    table=[[' '.join(t.text or '' for t in cell.findall('.//w:t',ns)) for cell in row.findall('w:tc',ns)] for row in child.findall('w:tr',ns)]
                    blocks.append({'kind':'table','table':table,'text':table_text(table)})
            for name in archive.namelist():
                if name.startswith('word/media/'):
                    if len(images)>=8: warnings.append('Additional document images require review');break
                    part=image_part(archive.read(name))
                    if part: images.append(part)
                    else: warnings.append('An embedded image cannot be decoded')
        text='\n'.join(b['text'] for b in blocks)
        if len(text)>250000: raise ValueError('Document contains too much text; split it into smaller documents')
        return [{'number':1,'label':'Document','text':text,'blocks':blocks,'images':images,'warnings':warnings}]
    if format == 'pdf':
        from .document_import import extract_document_sections
        from pypdf import PdfReader
        text_sections=extract_document_sections(data,format)
        reader=PdfReader(io.BytesIO(data));sections=[];total_images=0
        for i,((label,text),page) in enumerate(zip(text_sections,reader.pages),1):
            images=[];warnings=[]
            for image in page.images:
                if len(images)>=8 or total_images>=40:
                    warnings.append('Additional page images require rendering for full review');break
                part=image_part(image.data)
                if part:images.append(part);total_images+=1
                else:warnings.append('An embedded PDF image cannot be decoded')
            if not text.strip():warnings.append('Image-only page requires rendering and vision')
            sections.append({'number':i,'label':label,'text':text,'blocks':[],'images':images,'warnings':warnings})
        return sections
    text=data.decode('utf-8-sig')
    if len(text)>250000: raise ValueError('Document contains too much text')
    return [{'number':1,'label':'Text','text':text,'blocks':[],'images':[],'warnings':[]}]
