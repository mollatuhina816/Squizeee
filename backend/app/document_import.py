"""Deterministic question extraction. Never infer an absent answer key."""
import io
import re
import zipfile
from pydantic import ValidationError
from .builder_routes import BankInput

START = re.compile(r'^(?:(?:question|q)\s*\d*\s*[:.)-]|\d+[.)])\s*(.*)$', re.I)
OPTION = re.compile(r'^\(?([A-T])\s*[).:]\s*(.+)$', re.I)
ANSWER = re.compile(r'^(?:correct\s+(?:answers?|options?)|answers?|ans\.?)\s*[:=\u2013\u2014-]\s*(.*)$', re.I)


def split_inline_question_parts(line):
    line = line.strip()
    if not line:
        return []
    answer_match = re.search(r'(?i)\b(?:correct\s+(?:answers?|options?)|answers?|ans\.?)\s*[:=\u2013\u2014-]', line)
    if answer_match and answer_match.start() == 0:
        return [line]
    matches = list(re.finditer(r'(?<![A-Za-z])([A-T])\s*[).:]\s*', line, re.I))
    if not matches:
        return [line]
    if answer_match is not None:
        matches = [m for m in matches if m.start() < answer_match.start()]
    if not matches:
        return [line]
    parts = []
    cursor = 0
    for index, match in enumerate(matches):
        if match.start() > cursor:
            prefix = line[cursor:match.start()].strip()
            if prefix:
                parts.append(prefix)
        option = match.group(1).upper()
        next_option = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        answer_match_after = re.search(r'(?i)\b(?:correct\s+(?:answers?|options?)|answers?|ans\.?)\s*[:=\u2013\u2014-]', line[match.end():])
        if answer_match_after is not None:
            next_answer = match.end() + answer_match_after.start()
            next_option = min(next_option, next_answer)
        value = line[match.end():next_option].strip()
        if value:
            parts.append(f'{option}) {value.strip()}')
        cursor = next_option
    if cursor < len(line):
        tail = line[cursor:].strip()
        if tail:
            parts.append(tail)
    return parts


def parse_block(lines):
    title=[];options={};answers=[];explanation=[];marks='1';mode='title';last=None
    for line in lines:
        for logical_line in split_inline_question_parts(line):
            answer=ANSWER.match(logical_line)
            option=OPTION.match(logical_line)
            if answer:
                if answers: raise ValueError('Use one Answer: line per question')
                answers=[answer.group(1).strip()];mode='answer'
            elif re.match(r'^explanation\s*:',logical_line,re.I):
                explanation.append(logical_line.split(':',1)[1].strip());mode='explanation'
            elif re.match(r'^marks\s*:',logical_line,re.I):
                marks=logical_line.split(':',1)[1].strip()
            elif option and mode not in {'answer','explanation'}:
                last=option.group(1).upper()
                if last in options: raise ValueError(f'Duplicate option label {last}')
                options[last]=option.group(2).strip();mode='option'
            elif mode=='answer' and answers==['']: answers[0]=logical_line
            elif mode=='title': title.append(logical_line)
            elif mode=='option': options[last]+=' '+logical_line
            elif mode=='explanation': explanation.append(logical_line)
            else: raise ValueError('Unexpected text after Answer:. Put feedback after Explanation:')
    if not answers or not answers[0]: raise ValueError('Missing Answer: line. Add the correct option letter or exact option text')
    raw=answers[0]
    if raw in options.values(): correct=[raw]
    else:
        # Accept A, C / A|C / B) London. Labels must exist in this question.
        tokens=[x.strip() for x in re.split(r'[,|;]',raw)]
        correct=[]
        for token in tokens:
            match=re.fullmatch(r'(?:option\s+)?\(?([A-T])(?:\)|[.:])?(?:\s*[-:.)]?\s+(.+))?',token,re.I)
            if not match or match.group(1).upper() not in options:
                raise ValueError('Answer must match an option letter or exact option text')
            value=options[match.group(1).upper()]
            if match.group(2) and match.group(2).strip()!=value:
                raise ValueError('Answer letter and answer text disagree')
            correct.append(value)
    item=BankInput(question={'kind':'multiple_select' if len(correct)>1 else 'mcq','title':' '.join(title),
        'options':list(options.values()),'correct_answers':correct,'marks':marks,'explanation':' '.join(explanation)})
    return item.model_dump(mode='json')


def parse_sections(sections):
    valid=[];errors=[];blocks=[];current=[];location='';numbered=False
    footer=re.compile(r'^(?:page\s+\d+(?:\s*(?:of|/)\s*\d+)?|\d+\s*(?:of|/)\s*\d+)$',re.I)

    def finish():
        nonlocal current, numbered
        if current:
            blocks.append((location,current))
        current=[]
        numbered=False

    for page,text in sections:
        lines=[line.strip() for line in text.replace('\v','\n').splitlines() if line.strip()]
        lines=[line for line in lines if not footer.fullmatch(line)]
        if not lines:
            errors.append({'row':len(blocks)+1,'message':f'{page}: No readable text. Scanned/image-only questions need OCR before importing.'})
            continue
        # A numbered PDF question can continue onto the next page. Unnumbered
        # questions remain page/slide based unless the next page starts with
        # an option or answer, which is an explicit continuation.
        continuation=bool(OPTION.match(lines[0]) or ANSWER.match(lines[0]))
        if current and (page.startswith('Slide ') or (not numbered and not continuation)):
            finish()
        for line in lines:
            start=START.match(line)
            if start:
                # Text before the first numbered question is a document heading,
                # not an extra question. Never discard a block containing options.
                if current and (numbered or any(OPTION.match(x) or ANSWER.match(x) for x in current)):
                    finish()
                current=[start.group(1)] if start.group(1) else []
                location=page;numbered=True
            else:
                if not current:location=page
                current.append(line)
    finish()
    if len(blocks)>100:raise ValueError('PDF/PowerPoint imports support at most 100 questions')
    for number,(page,block) in enumerate(blocks,1):
        try:valid.append(parse_block(block))
        except (ValueError,ValidationError) as exc:
            message='; '.join(x['msg'] for x in exc.errors()) if isinstance(exc,ValidationError) else str(exc)
            excerpt=' '.join(block)[:180]
            errors.append({'row':number,'message':f'{page}: {message}. Extracted text: {excerpt}'})
    return valid,errors


def extract_document_sections(data, format):
    sections=[]
    if format=='pdf':
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
        try:
            reader=PdfReader(io.BytesIO(data))
            if reader.is_encrypted:raise ValueError('Password-protected PDFs are not supported. Export an unprotected copy')
            if len(reader.pages)>100:raise ValueError('Maximum 100 PDF pages')
            for i,page in enumerate(reader.pages,1):
                text=page.extract_text() or ''
                if len(text)>50000:raise ValueError('A PDF page contains too much text')
                sections.append((f'Page {i}',text))
        except PdfReadError as exc:raise ValueError('Unable to read this PDF. Export a text-based PDF and try again') from exc
    else:
        from pptx import Presentation
        from lxml.etree import XMLSyntaxError
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries=archive.infolist()
            if len(entries)>2000 or sum(x.file_size for x in entries)>20_000_000:
                raise ValueError('PowerPoint expands beyond the permitted size')
            if any('vbaproject' in x.filename.lower() or '/embeddings/' in x.filename.lower() for x in entries):
                raise ValueError('Remove macros and embedded files before importing')
        try:deck=Presentation(io.BytesIO(data))
        except (ValueError,KeyError,XMLSyntaxError) as exc:raise ValueError('Unable to read PowerPoint. Save the file as .pptx') from exc
        if len(deck.slides)>100:raise ValueError('Maximum 100 PowerPoint slides')
        def shape_text(shapes):
            for shape in sorted(shapes,key=lambda s:(s.top,s.left)):
                if shape.has_text_frame:yield shape.text
                elif shape.has_table:
                    for row in shape.table.rows:
                        yield '\n'.join(cell.text for cell in row.cells)
                elif hasattr(shape,'shapes'):yield from shape_text(shape.shapes)
        for i,slide in enumerate(deck.slides,1):
            text='\n'.join(shape_text(slide.shapes))
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes=slide.notes_slide.notes_text_frame.text.strip()
                if notes:text+='\n'+notes
            if len(text)>50000:raise ValueError('A slide contains too much text')
            sections.append((f'Slide {i}',text))
    if not sections:raise ValueError('The document has no pages or slides')
    return sections


def extract_document(data, format):
    return parse_sections(extract_document_sections(data, format))
