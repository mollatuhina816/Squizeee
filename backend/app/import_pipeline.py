"""All formats enter the same versioned JSON preview and faculty review pipeline."""
import csv
import io
import json
from pydantic import ValidationError
from .document_structure import detect_format, checked_archive, extract_structure
from .import_schema import CanonicalDocument, from_bank, preview_row, question_adapter
from .import_parser import parse_structure


def json_rows(raw,filename):
    data=json.loads(raw.decode('utf-8-sig'))
    if isinstance(data,dict):
        if data.get('schema_version','1.0') != '1.0':raise ValueError('Unsupported canonical schema version; expected 1.0')
        if set(data)-{'schema_version','questions'}:raise ValueError('Unsupported JSON document fields')
        values=data.get('questions',[])
    else:values=data
    if not isinstance(values,list) or len(values)>500:raise ValueError('JSON must contain at most 500 questions')
    result=[];errors=[]
    for index,value in enumerate(values,1):
        try:
            if isinstance(value,dict) and 'type' in value:item=question_adapter.validate_python(value)
            elif isinstance(value,dict) and 'kind' in value:item=from_bank({'question':value})
            elif isinstance(value,dict) and 'question' in value:item=from_bank(value)
            else:raise ValueError('Expected a canonical or platform question object')
            item.source.filename=filename
            if item.answer_origin=='missing' and (getattr(item,'correct_answers',[]) or getattr(item,'accepted_answers',[]) or getattr(item,'model_answer','')):item.answer_origin='source'
            if item.type=='short_answer' and not item.accepted_answers and not item.model_answer:item.requires_review=True
            result.append(preview_row(item))
        except (ValueError,ValidationError,KeyError,TypeError) as exc:errors.append({'row':index,'message':str(exc)[:800]})
    return result,errors


def table_rows(raw,format,filename):
    sheets=[]
    if format=='csv':
        text=raw.decode('utf-8-sig')
        try:dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t')
        except csv.Error:dialect=csv.excel
        rows=[]
        for row in csv.reader(io.StringIO(text),dialect):
            if len(rows)>=501:raise ValueError('Maximum 500 question rows')
            if len(row)>30:raise ValueError('Maximum 30 columns')
            rows.append(row)
        sheets=[('CSV',rows)]
    else:
        from openpyxl import load_workbook
        with checked_archive(raw) as archive:
            if any('vbaproject' in e.filename.lower() or 'externallinks' in e.filename.lower() for e in archive.infolist()):raise ValueError('Macros and external links are not supported')
        book=load_workbook(io.BytesIO(raw),read_only=True,data_only=False,keep_links=False)
        try:
            for sheet in book.worksheets:
                if (sheet.max_row or 0)>501 or (sheet.max_column or 0)>30:raise ValueError('Maximum 500 rows and 30 columns per worksheet')
                rows=[]
                for cells in sheet.iter_rows():
                    if any(c.data_type=='f' for c in cells):raise ValueError('Formula cells are not supported')
                    rows.append([str(c.value) if c.value is not None else '' for c in cells])
                    if len(rows)>501:raise ValueError('Maximum 500 rows per worksheet')
                if any(any(row) for row in rows):sheets.append((sheet.title,rows))
        finally:book.close()
    result=[];errors=[]
    for sheet,rows in sheets:
        if not rows:continue
        if len(rows)>501:raise ValueError('Maximum 500 question rows')
        headers=[str(h).strip().lower().replace(' ','_') for h in rows[0]]
        aliases={'question':'title','question_text':'title','type':'kind','correct_answer':'correct_answers','answer':'correct_answers'}
        headers=[aliases.get(h,h) for h in headers]
        if len(set(headers))!=len(headers):raise ValueError('Use unique column headers')
        if 'title' not in headers:raise ValueError('Include a question or title column')
        allowed={'kind','title','options','correct_answers','accepted_answers','model_answer','subject','chapter','topic','difficulty','marks','explanation','tags','minimum','maximum','duration_seconds'}
        option_headers={h for h in headers if h in list('abcdefghijklmnopqrst') or h.startswith('option_')}
        unknown=set(headers)-allowed-option_headers
        if unknown:raise ValueError('Unsupported columns: '+', '.join(sorted(unknown)))
        for number,row in enumerate(rows[1:],2):
            if not any(row):continue
            if len(row)>len(headers) or any(len(str(x))>5000 for x in row):errors.append({'row':number,'message':f'{sheet}: Oversized row or cell'});continue
            cells=dict(zip(headers,row));options=[]
            if cells.get('options'):options=[{'id':chr(65+i),'text':v.strip()} for i,v in enumerate(cells['options'].split('|')) if v.strip()]
            else:
                for header in headers:
                    if header in option_headers and cells.get(header):options.append({'id':header.removeprefix('option_').upper(),'text':cells[header].strip()})
            kind=(cells.get('kind') or ('mcq' if options else 'short_answer')).lower().replace(' ','_').replace('/','_')
            raw_item={'type':kind,'question':cells.get('title',''),'source':{'filename':filename,'row_number':number,'answer_evidence':cells.get('correct_answers','')},'answer_origin':'source' if cells.get('correct_answers') or cells.get('accepted_answers') else 'missing'}
            for key in ['subject','chapter','topic','difficulty','marks','explanation','duration_seconds','minimum','maximum','model_answer']:
                if cells.get(key):raw_item[key]=cells[key]
            if cells.get('tags'):raw_item['tags']=[v.strip() for v in cells['tags'].split('|') if v.strip()]
            if kind in {'mcq','quiz','multiple_select','true_false','survey','poll','ranking'}:
                if kind=='true_false' and not options:options=[{'id':'True','text':'True'},{'id':'False','text':'False'}]
                raw_item['options']=options
                if kind in {'mcq','quiz','multiple_select','true_false'}:
                    answers=[]
                    for token in cells.get('correct_answers','').split('|'):
                        if not token.strip():continue
                        answer=next((o['id'] for o in options if token.strip().casefold() in {o['id'].casefold(),o['text'].casefold()}),token.strip())
                        answers.append(answer)
                    raw_item['correct_answers']=answers
            elif kind=='short_answer':
                raw_item['accepted_answers']=[a.strip() for a in (cells.get('accepted_answers') or cells.get('correct_answers','')).split('|') if a.strip()]
                raw_item['requires_review']=not bool(raw_item['accepted_answers'] or raw_item.get('model_answer'))
            try:result.append(preview_row(question_adapter.validate_python(raw_item)))
            except (ValueError,ValidationError) as exc:errors.append({'row':number,'message':f'{sheet}: {str(exc)[:800]}'})
    if len(result)>500:raise ValueError('Maximum 500 questions per import')
    return result,errors


def deterministic_preview(raw,format,filename):
    if format=='json':return (*json_rows(raw,filename),[])
    if format in {'csv','xlsx'}:return (*table_rows(raw,format,filename),[])
    from xml.etree.ElementTree import ParseError
    from lxml.etree import XMLSyntaxError
    try:sections=extract_structure(raw,format,filename)
    except (ParseError,XMLSyntaxError,KeyError,OSError) as exc:raise ValueError('Unable to read document structure; export a fresh supported copy') from exc
    rows,errors=parse_structure(sections,filename,format)
    return rows,errors,sections


def difficult_structure(sections):
    for section in sections:
        if section.get('images') or section.get('warnings'):return True
        # Flattened reading order cannot safely represent independent columns,
        # option boxes, or a question continued in an unlabelled shape.
        positioned=[b for b in section['blocks'] if b.get('text') and 'x' in b]
        if len(positioned)>1:return True
        colors=set()
        for block in section['blocks']:
            if block.get('parent') is not None or block.get('table'):return True
            for p in block.get('paragraphs',[]):
                for run in p.get('runs',[]):
                    if run.get('text','').strip():colors.add(run.get('color') or run.get('theme_color') or 'default')
        if len(colors)>1:return True
    return False


async def prepare_preview(raw,filename,expected=None,reserve_ai=None):
    from .config import settings
    from .document_ai import convert_legacy,render_sections,understand_document
    from .ai_question_generator import AIGenerationError
    from starlette.concurrency import run_in_threadpool
    from starlette.exceptions import HTTPException
    if len(raw)>40_000_000:raise ValueError('Maximum upload size is 40 MB')
    format=detect_format(raw,filename,expected)
    original=filename
    if format=='legacy':raw=await convert_legacy(raw,filename);format='pdf'
    rows,errors,sections=await run_in_threadpool(deterministic_preview,raw,format,original)
    difficult=bool(sections and (errors or difficult_structure(sections) or any(row.get('requires_review') for row in rows)))
    resolved_text_layout=bool(rows and not errors and not any(row.get('requires_review') for row in rows)
                              and all(not s.get('images') and not s.get('warnings')
                                      and (s.get('classification') in {'context','answer_key'} or s.get('parser_layout_resolved')) for s in sections))
    # Explicit question IDs, option labels and final keys are already understood.
    # Multiple boxes alone need no second extraction when relationships are
    # resolved and there is no uninspected visual content.
    if resolved_text_layout:difficult=False
    if difficult:
        # A fallback failure must never turn a tentative text extraction into
        # an approved import. Keep the usable draft, but require review.
        for row in rows:row['requires_review']=True;row['canonical']['requires_review']=True
    if difficult and settings().gemini_api_key.get_secret_value():
        try:
            if reserve_ai:reserve_ai()
            # Rendering retains full layout; embedded image vision remains useful if no renderer is configured.
            rendering_errors=[]
            if format in {'pptx','pdf','docx'} and settings().document_renderer_url:
                try:await render_sections(raw,original if format!='pdf' or filename.lower().endswith('.pdf') else 'converted.pdf',sections)
                except (ValueError,KeyError,TypeError,OSError) as exc:
                    # Text, notes and embedded images can still be understood.
                    rendering_errors.append({'row':0,'message':f'Full document rendering failed: {str(exc)[:600]}. Check visual content against the original.'})
            extracted,ai_errors=await understand_document(sections,original)
            if len(extracted)<len(rows):
                ai_errors.append({'row':0,'message':'AI extracted fewer questions than the text parser. The original text draft was retained; compare the document before approval.'})
                extracted=rows
            elif any('fully cover' in error['message'] for error in ai_errors) and rows and not errors:
                # Incomplete AI coverage must not erase explicit source answers
                # already found by the conservative parser.
                extracted=rows
            rows,errors=extracted,[*rendering_errors,*ai_errors]
        except (AIGenerationError,ValueError,ValidationError) as exc:
            errors.append({'row':0,'message':str(exc)[:800]})
        except HTTPException as exc:
            errors.append({'row':0,'message':f'Automatic document understanding unavailable: {str(exc.detail)[:700]}. Review the extracted draft or retry.'})
    elif difficult:
        for section in sections:
            if section.get('images') or section.get('warnings'):
                errors.append({'row':0,'message':f"{section['label']}: Visual content requires Gemini vision/faculty review; configure GEMINI_API_KEY and optionally DOCUMENT_RENDERER_URL"})
        for row in rows:row['requires_review']=True;row['canonical']['requires_review']=True
    if not rows and not errors:errors=[{'row':0,'message':'No questions found; review the source document'}]
    return rows,errors,format
