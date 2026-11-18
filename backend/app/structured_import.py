"""Template-only extraction. This module intentionally has no AI dependencies."""
import io
import re
import subprocess
import tempfile
from pathlib import Path

from pydantic import ValidationError

from .config import settings
from .document_structure import checked_archive, detect_format
from .import_schema import question_adapter, to_bank
from .document_import import START, split_inline_question_parts
from .import_answers import resolve_choice_answer

class StructuredImportError(ValueError):
    """A safe, administrator-facing extraction error."""


HEADERS = ['Question', 'Option A', 'Option B', 'Option C', 'Option D', 'Correct Answer', 'Explanation']
SAMPLE = ('Question 1: What is the capital of India?\nA. Mumbai\nB. Delhi\n'
          'C. Kolkata\nD. Chennai\nCorrect Answer: B\nExplanation: Delhi is the capital of India.')
LABEL = re.compile(r'^\s*(?:([A-D])[.):\-]?\s+(.+)|(Correct\s+Answer|Answer|Ans\.?|Explanation)\s*:?\s+(.+))$', re.I)


def fingerprint(text):
    return ' '.join(text.casefold().split())


def validate_candidate(raw, seen):
    reasons = []
    key = fingerprint(raw.get('question', ''))
    if key and key in seen:
        reasons.append('Duplicate question; remove this row or change its statement.')
    if key:
        seen.add(key)
    try:
        item = question_adapter.validate_python(raw)
        if item.type != 'mcq':
            return reasons + ['Structured imports require a single-answer MCQ with four options.']
        if [o.id for o in item.options] != list('ABCD'):
            reasons.append('Exactly four options labelled A, B, C and D are required.')
        if len({fingerprint(o.text) for o in item.options}) != 4:
            reasons.append('Four distinct option texts are required.')
        if not item.correct_answers:
            reasons.append('Correct Answer must match an option letter or exact option text; review O/0 or I/1 OCR ambiguities manually.')
        if not reasons:
            to_bank(item)
    except (ValueError, ValidationError):
        reasons.append('Question and four distinct options are required and must fit the question bank limits (500/300 characters).')
    return reasons


def candidate(values, source, *, ocr=False, issues=None):
    title, *rest = (list(values) + [''] * 7)[:7]
    opts, answer, explanation = rest[:4], rest[4], rest[5]
    options = [{'id': chr(65+i), 'text': value} for i, value in enumerate(opts)]
    tail = ''
    try: resolved, tail = resolve_choice_answer(answer, options)
    except ValueError: resolved = []
    raw = {'type': 'mcq', 'question': title, 'options': options,
           'correct_answers': resolved, 'explanation': explanation, 'source': source,
           'answer_origin': 'source' if resolved else 'missing', 'requires_review': ocr or bool(issues) or bool(tail) or '\ufffd' in ' '.join(values)}
    raw['source']['answer_evidence'] = answer[:3000]
    if tail: raw['explanation'] = (explanation + ' ' + tail).strip()
    return {'canonical': raw, 'requires_review': raw['requires_review'], 'issues': issues or []}


def text_candidates(text, source, *, ocr=False, one=False):
    chunks = []
    current = []
    logical_lines = [part for line in text.replace('\v', '\n').splitlines() for part in split_inline_question_parts(line)]
    for line in logical_lines:
        if re.fullmatch(r'\s*---\s*QUESTION\s*---\s*', line, re.I) or START.match(line):
            if current:
                # A document title before the first numbered question is context,
                # not an extra invalid question. Keep any question-like content.
                preamble = not chunks and START.match(line) and not any(
                    START.match(value) or LABEL.match(value) or '?' in value for value in current
                )
                if not preamble:
                    chunks.append(current)
            current = []
            if START.match(line):
                current.append(line)
        elif line.strip():
            current.append(line.strip())
    if current:
        chunks.append(current)
    result = []
    for lines in chunks:
        values = [''] * 7
        issues = []
        field = 0
        labels = set()
        if not START.match(lines[0]):
            issues.append('Question must start with Question <number>:')
        for line in lines:
            start = START.match(line)
            label = LABEL.match(line)
            if start:
                values[0] = start.group(1); field = 0
            elif label:
                name = label.group(1).upper() if label.group(1) else label.group(3).lower()
                if name in labels:
                    issues.append('Repeated field or option label; check the source.')
                labels.add(name)
                field = ord(name)-64 if len(name) == 1 else 6 if name == 'explanation' else 5
                values[field] = label.group(2) if label.group(1) else label.group(4)
            else:
                values[field] = (values[field] + ' ' + line).strip()
        if one and len(chunks) != 1:
            issues.append('Exactly one question per slide is required.')
        result.append(candidate(values, source, ocr=ocr, issues=issues))
    return result


def complete(text):
    rows = text_candidates(text, {})
    return bool(rows) and all(not r['issues'] and not validate_candidate(r['canonical'], set()) for r in rows)


def ocr_image(image):
    import pytesseract
    if image.width * image.height > 20_000_000:
        raise StructuredImportError('OCR image exceeds 20 megapixels; use smaller images.')
    pytesseract.pytesseract.tesseract_cmd = settings().structured_tesseract_command
    try:
        return pytesseract.image_to_string(image, lang=settings().structured_ocr_language, timeout=30)
    except (RuntimeError, OSError, pytesseract.TesseractError) as exc:
        raise StructuredImportError('OCR unavailable or timed out. Install Tesseract and its language data, or upload selectable text.') from exc


def legacy_ppt(data):
    """Use an isolated local converter; never a remote service or an AI API."""
    with tempfile.TemporaryDirectory(prefix='quiz-structured-') as directory:
        root = Path(directory)
        source = root / 'source.ppt'
        source.write_bytes(data)
        profile = root / 'profile'
        (profile / 'user').mkdir(parents=True)
        (profile / 'user' / 'registrymodifications.xcu').write_text(
            '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item></oor:items>', encoding='utf-8')
        try:
            subprocess.run([settings().structured_libreoffice_command, '--headless',
                            '-env:UserInstallation=' + profile.as_uri(),
                            '--convert-to', 'pptx', '--outdir', str(root), str(source)],
                           check=True, timeout=60, capture_output=True)
            target = root / 'source.pptx'
            if not target.exists() or target.stat().st_size > settings().structured_import_max_bytes:
                raise StructuredImportError('PPT conversion failed or exceeded the size limit; save as PPTX.')
            return target.read_bytes()
        except (OSError, subprocess.SubprocessError) as exc:
            raise StructuredImportError('Legacy PPT requires local LibreOffice. Install it or save the file as PPTX.') from exc


def spreadsheet(data, fmt, filename):
    if fmt == 'xlsx':
        from openpyxl import load_workbook
        with checked_archive(data):
            pass
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
        def records():
            for sheet in book:
                if sheet.max_column > 7 or sheet.max_row > 10001:
                    raise StructuredImportError('Sheets must have seven columns and at most 10000 data rows.')
                yield sheet.title, (tuple(('=FORMULA' if c.data_type == 'f' else c.value) for c in row) for row in sheet.iter_rows())
    else:
        import xlrd
        book = xlrd.open_workbook(file_contents=data, on_demand=True)
        def records():
            for sheet in book.sheets():
                if sheet.ncols > 7 or sheet.nrows > 10001:
                    raise StructuredImportError('Sheets must have seven columns and at most 10000 data rows.')
                yield sheet.name, (sheet.row_values(i) for i in range(sheet.nrows))
    rows = []
    try:
        for name, records_iter in records():
            iterator = iter(records_iter)
            headers = [str(v or '').strip() for v in next(iterator, [])]
            if headers != HEADERS:
                raise StructuredImportError('Every sheet must have these exact headers: ' + ', '.join(HEADERS))
            for number, record in enumerate(iterator, 2):
                if number > 10001:
                    raise StructuredImportError('Maximum 10000 spreadsheet rows including empty rows.')
                values = [str(v).strip() if v is not None else '' for v in record]
                if not any(values):
                    continue
                issues = []
                if len(values) > 7 and any(values[7:]):
                    issues.append('Unexpected cells beyond the template columns.')
                if any(v.startswith('=') for v in values):
                    issues.append('Formula cells are not allowed; paste values instead.')
                row = candidate(values, {'filename': filename, 'row_number': number}, issues=issues)
                row['location'] = f'Sheet {name}, row {number}'
                rows.append(row)
                if len(rows) > 500:
                    raise StructuredImportError('Maximum 500 questions per import.')
    finally:
        if fmt == 'xlsx': book.close()
        else: book.release_resources()
    return rows


def extract(data, filename):
    if not data or len(data) > settings().structured_import_max_bytes:
        raise StructuredImportError('Empty file or configured upload size exceeded.')
    fmt = filename.rsplit('.', 1)[-1].lower()
    if fmt not in {'pdf', 'ppt', 'pptx', 'xls', 'xlsx'}:
        raise StructuredImportError('Choose PDF, PPT, PPTX, XLS or XLSX.')
    detected = detect_format(data, filename)
    if fmt in {'ppt', 'xls'}:
        import olefile
        if not olefile.isOleFile(io.BytesIO(data)):
            raise StructuredImportError('File contents do not match the selected legacy format.')
        with olefile.OleFileIO(io.BytesIO(data)) as ole:
            if not any(ole.exists(stream) for stream in (['PowerPoint Document'] if fmt == 'ppt' else ['Workbook', 'Book'])):
                raise StructuredImportError('File contents do not match the selected legacy format.')
    elif detected != fmt:
        raise StructuredImportError('File contents do not match the filename.')
    if fmt == 'ppt':
        data = legacy_ppt(data); fmt = 'pptx'
    errors = []
    rows = []
    if fmt in {'xls', 'xlsx'}:
        rows = spreadsheet(data, fmt, filename)
    elif fmt == 'pdf':
        import fitz
        from PIL import Image
        with fitz.open(stream=data, filetype='pdf') as document:
            if document.needs_pass or len(document) > 100:
                raise StructuredImportError('PDF must be unencrypted and contain at most 100 pages.')
            # Collect consecutive text pages to preserve questions crossing page boundaries.
            pending = []; pages = []
            def flush():
                if pending:
                    rows.extend(text_candidates('\n'.join(pending), {'filename': filename, 'page_number': pages[0], 'sections': list(pages)}))
                    pending.clear(); pages.clear()
            for number, page in enumerate(document, 1):
                text = page.get_text(sort=True)
                use_ocr = not complete(text) and (bool(page.get_images()) or len(re.sub(r'\W', '', text)) < 30)
                if use_ocr:
                    flush()
                    try:
                        scale = min(2.5, (20_000_000 / max(1, page.rect.width * page.rect.height)) ** .5)
                        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB)
                        with Image.frombytes('RGB', [pix.width, pix.height], pix.samples) as image:
                            extracted = ocr_image(image)
                        # Full page OCR replaces the text layer, avoiding duplicate extraction.
                        rows.extend(text_candidates(extracted, {'filename': filename, 'page_number': number}, ocr=True))
                        if not extracted.strip(): errors.append({'row': 0, 'message': f'Page {number}: OCR found no text.'})
                    except ValueError as exc:
                        rows.extend(text_candidates(text, {'filename': filename, 'page_number': number}, ocr=True))
                        errors.append({'row': 0, 'message': f'Page {number}: {exc}'})
                else:
                    pending.append(text); pages.append(number)
            flush()
    else:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        from PIL import Image
        with checked_archive(data): pass
        deck = Presentation(io.BytesIO(data))
        if len(deck.slides) > 100: raise StructuredImportError('Maximum 100 slides.')
        for number, slide in enumerate(deck.slides, 1):
            blocks = []; images = []
            def walk(shapes):
                for shape in shapes:
                    if shape.shape_type == MSO_SHAPE_TYPE.GROUP: walk(shape.shapes)
                    elif shape.has_text_frame: blocks.append((shape.top, shape.left, shape.text))
                    elif shape.has_table:
                        blocks.append((shape.top, shape.left, '\n'.join(c.text for r in shape.table.rows for c in r.cells)))
                    elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE: images.append((shape.top, shape.left, shape.image.blob))
            walk(slide.shapes)
            text = '\n'.join(b[2] for b in sorted(blocks))
            use_ocr = bool(images) and not complete(text)
            if use_ocr:
                seen_images = set()
                for top, left, blob in images:
                    if blob in seen_images: continue
                    seen_images.add(blob)
                    try:
                        with Image.open(io.BytesIO(blob)) as image:
                            found = ocr_image(image)
                        if fingerprint(found) not in fingerprint(text): blocks.append((top, left, found))
                    except (OSError, ValueError) as exc:
                        errors.append({'row': 0, 'message': f'Slide {number}: OCR unavailable or image unreadable. Check the source.'})
                text = '\n'.join(b[2] for b in sorted(blocks))
            if text.strip():
                rows.extend(text_candidates(text, {'filename': filename, 'slide_number': number}, ocr=use_ocr, one=True))
            elif images:
                errors.append({'row': 0, 'message': f'Slide {number}: No readable question found.'})
    if len(rows) > 500: raise StructuredImportError('Maximum 500 questions per import.')
    seen = set()
    for index, row in enumerate(rows, 1):
        reasons = row.pop('issues') + validate_candidate(row['canonical'], seen)
        if reasons:
            row['requires_review'] = row['canonical']['requires_review'] = True
            errors.extend({'row': index, 'message': row.get('location', f'Question {index}') + ': ' + reason} for reason in reasons)
    if not rows and not errors:
        errors.append({'row': 0, 'message': 'No questions found. Use the downloadable template.'})
    return rows, errors, fmt


def template(fmt):
    out = io.BytesIO()
    if fmt == 'xlsx':
        from openpyxl import Workbook
        book = Workbook(); sheet = book.active; sheet.title = 'Questions'
        sheet.append(HEADERS)
        sheet.append(['What is the capital of India?', 'Mumbai', 'Delhi', 'Kolkata', 'Chennai', 'B', 'Delhi is the capital of India.'])
        sheet.freeze_panes = 'A2'
        for col in 'ABCDEFG': sheet.column_dimensions[col].width = 30
        book.save(out)
        mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt == 'pptx':
        from pptx import Presentation
        from pptx.util import Inches, Pt
        deck = Presentation(); slide = deck.slides.add_slide(deck.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(.5), Inches(.5), Inches(9), Inches(6))
        box.text = SAMPLE
        for p in box.text_frame.paragraphs: p.font.size = Pt(22)
        deck.save(out); mime = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    elif fmt == 'pdf':
        from reportlab.pdfgen import canvas
        pdf = canvas.Canvas(out); text = pdf.beginText(50, 790); text.setFont('Helvetica', 12)
        for line in (SAMPLE + '\n\n--- QUESTION ---\n\n' + SAMPLE.replace('Question 1:', 'Question 2:').replace('capital of India?', 'capital of India (answer as text)?').replace('Correct Answer: B', 'Correct Answer: Delhi')).splitlines():
            text.textLine(line)
        pdf.drawText(text); pdf.save(); mime = 'application/pdf'
    else:
        raise StructuredImportError('Unknown template format.')
    return out.getvalue(), mime
