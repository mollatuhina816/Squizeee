import io

import fitz
import pytest
from openpyxl import Workbook
from PIL import Image
from pptx import Presentation
from pptx.util import Inches

from app import structured_import as structured
from conftest import register


def xlsx(records):
    book = Workbook(); sheet = book.active
    sheet.append(structured.HEADERS)
    for record in records: sheet.append(record)
    stream = io.BytesIO(); book.save(stream)
    return stream.getvalue()


GOOD = ['Capital?', 'Mumbai', 'Delhi', 'Kolkata', 'Chennai', 'Delhi', 'Example']


@pytest.mark.parametrize('answer,expected', [('B', ['B']), ('Delhi', ['B']), ('D', ['D']), ('0', []), ('I', [])])
def test_answer_resolution_without_guessing(answer, expected):
    row = structured.candidate([*GOOD[:5], answer, ''], {})
    assert row['canonical']['correct_answers'] == expected


def test_ambiguous_letter_and_option_text_requires_review():
    row = structured.candidate(['Letter?', 'B', 'C', 'D', 'E', 'B', ''], {})
    assert row['canonical']['correct_answers'] == []


@pytest.mark.parametrize('fmt', ['pdf', 'pptx', 'xlsx'])
def test_templates_round_trip_without_ocr(fmt, monkeypatch):
    monkeypatch.setattr(structured, 'ocr_image', lambda _: pytest.fail('Unnecessary OCR'))
    data, _ = structured.template(fmt)
    rows, errors, _ = structured.extract(data, 'template.' + fmt)
    assert rows and not errors
    assert all(row['canonical']['correct_answers'] == ['B'] for row in rows)


def test_scanned_pdf_and_image_slide_ocr(monkeypatch):
    monkeypatch.setattr(structured, 'ocr_image', lambda image: structured.SAMPLE)
    image = Image.new('RGB', (800, 800), 'white')
    png = io.BytesIO(); image.save(png, 'PNG')
    pdf = fitz.open(); page = pdf.new_page(); page.insert_image(page.rect, stream=png.getvalue())
    rows, errors, _ = structured.extract(pdf.tobytes(), 'scan.pdf'); pdf.close()
    assert not errors and len(rows) == 1 and rows[0]['requires_review']
    deck = Presentation(); slide = deck.slides.add_slide(deck.slide_layouts[6])
    slide.shapes.add_picture(io.BytesIO(png.getvalue()), Inches(0), Inches(0), width=Inches(7))
    deck.slides.add_slide(deck.slide_layouts[6])  # Blank slides are ignored.
    out = io.BytesIO(); deck.save(out)
    rows, errors, _ = structured.extract(out.getvalue(), 'scan.pptx')
    assert not errors and len(rows) == 1 and rows[0]['requires_review']


def test_ocr_failure_returns_reviewable_error(monkeypatch):
    def unavailable(_): raise ValueError('OCR unavailable; install Tesseract.')
    monkeypatch.setattr(structured, 'ocr_image', unavailable)
    pdf = fitz.open(); pdf.new_page()
    rows, errors, _ = structured.extract(pdf.tobytes(), 'scan.pdf'); pdf.close()
    assert errors and 'OCR unavailable' in errors[0]['message']


def test_invalid_rows_duplicates_and_headers():
    raw = xlsx([GOOD, [], GOOD, ['Missing?', 'A', '', 'C', 'D', 'Z'], ['Formula?', '=1+1', 'B', 'C', 'D', 'A']])
    rows, errors, _ = structured.extract(raw, 'questions.xlsx')
    assert len(rows) == 4
    assert any('Duplicate' in e['message'] for e in errors)
    assert any('row 5' in e['message'] for e in errors)
    assert any('Formula' in e['message'] for e in errors)
    book = Workbook(); book.active.append(['Wrong']); out = io.BytesIO(); book.save(out)
    with pytest.raises(ValueError, match='headers'): structured.extract(out.getvalue(), 'bad.xlsx')


def test_content_type_and_limits(monkeypatch):
    with pytest.raises(ValueError): structured.extract(b'not a pdf', 'bad.pdf')
    with pytest.raises(ValueError): structured.extract(b'not an ole file', 'bad.xls')
    monkeypatch.setattr(structured.settings(), 'structured_import_max_bytes', 1024)
    with pytest.raises(ValueError, match='size'): structured.extract(b'x' * 1025, 'big.pdf')


def test_real_legacy_xls():
    import xlwt
    book = xlwt.Workbook(); sheet = book.add_sheet('Questions')
    for row, record in enumerate([structured.HEADERS, GOOD]):
        for col, value in enumerate(record): sheet.write(row, col, value)
    out = io.BytesIO(); book.save(out)
    rows, errors, fmt = structured.extract(out.getvalue(), 'legacy.xls')
    assert fmt == 'xls' and not errors
    assert rows[0]['canonical']['correct_answers'] == ['B']


def test_local_ppt_converter_failure_is_actionable(monkeypatch):
    monkeypatch.setattr(structured.settings(), 'structured_libreoffice_command', 'missing-quiz-converter')
    with pytest.raises(ValueError, match='LibreOffice'):
        structured.legacy_ppt(b'placeholder')


def test_actual_tesseract_when_installed():
    import shutil
    if not shutil.which(structured.settings().structured_tesseract_command):
        pytest.skip('Tesseract executable is not installed on this host')
    doc = fitz.open(); page = doc.new_page()
    page.insert_textbox(fitz.Rect(30, 30, 580, 750), structured.SAMPLE, fontsize=18)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    with Image.frombytes('RGB', [pix.width, pix.height], pix.samples) as image:
        found = structured.ocr_image(image)
    doc.close()
    rows = structured.text_candidates(found, {}, ocr=True)
    assert len(rows) == 1 and rows[0]['canonical']['correct_answers'] == ['B']


def test_partial_edit_review_and_shared_bank_without_ai(client, monkeypatch):
    org = register(client)['organization_id']
    def forbidden(*args, **kwargs): pytest.fail('Structured import invoked AI')
    monkeypatch.setattr('app.import_routes.ai_reservation', forbidden)
    monkeypatch.setattr('app.import_routes.prepare_preview', forbidden)
    monkeypatch.setattr('app.document_ai.understand_document', forbidden)
    base = f'/api/v1/organizations/{org}/imports'
    raw = xlsx([GOOD, ['Broken?', 'one', '', 'three', 'four', 'Z']])
    response = client.post(base + '/structured/preview/file', files={'file': ('test.xlsx', raw)})
    assert response.status_code == 200, response.text
    preview = response.json(); assert len(preview['rows']) == 2 and preview['errors']
    assert client.post(base + f"/{preview['id']}/commit").status_code == 422
    reviewed = preview['document']; reviewed['questions'] = reviewed['questions'][:1]
    reviewed['questions'][0]['question'] = 'Edited capital?'
    path = base + f"/structured/{preview['id']}/review"
    assert client.post(path, json={'document': reviewed}).status_code == 422
    approved = client.post(path, json={'document': reviewed, 'acknowledge_unresolved': True})
    assert approved.status_code == 200, approved.text
    assert client.post(base + f"/{preview['id']}/commit").json()['imported'] == 1
    bank = client.get(f'/api/v1/organizations/{org}/bank/questions').json()
    assert bank[0]['question']['title'] == 'Edited capital?'
    assert bank[0]['question']['correct_answers'] == ['Delhi']
    again = xlsx([['Edited capital?', *GOOD[1:]]])
    duplicate = client.post(base + '/structured/preview/file', files={'file': ('test.xlsx', again)}).json()
    assert any('Duplicate' in e['message'] for e in duplicate['errors'])
    for fmt in ['pdf', 'pptx', 'xlsx']:
        assert client.get(base + '/structured/template/' + fmt).status_code == 200


def test_review_rejects_missing_answer_and_three_options(client):
    org = register(client)['organization_id']; base = f'/api/v1/organizations/{org}/imports'
    preview = client.post(base + '/structured/preview/file', files={'file': ('test.xlsx', xlsx([GOOD]))}).json()
    doc = preview['document']; doc['questions'][0]['correct_answers'] = []
    assert client.post(base + f"/structured/{preview['id']}/review", json={'document': doc}).status_code == 422
    doc['questions'][0]['correct_answers'] = ['B']; doc['questions'][0]['options'].pop()
    assert client.post(base + f"/structured/{preview['id']}/review", json={'document': doc}).status_code == 422
    doc['questions'] = [{'type': 'short_answer', 'question': 'Wrong type'}]
    assert client.post(base + f"/structured/{preview['id']}/review", json={'document': doc}).status_code == 422


def test_one_hundred_rows_allows_ninety_five_valid(client):
    org = register(client)['organization_id']; base = f'/api/v1/organizations/{org}/imports'
    records = [[f'Question {i}?', *GOOD[1:]] for i in range(100)]
    for i in range(95, 100): records[i][5] = 'Unmatched answer'
    preview = client.post(base + '/structured/preview/file', files={'file': ('test.xlsx', xlsx(records))}).json()
    assert len(preview['rows']) == 100 and len(preview['errors']) == 5
    reviewed = {'schema_version': '1.0', 'questions': preview['document']['questions'][:95]}
    response = client.post(base + f"/structured/{preview['id']}/review", json={'document': reviewed, 'acknowledge_unresolved': True})
    assert response.status_code == 200, response.text
    assert client.post(base + f"/{preview['id']}/commit").json()['imported'] == 95
    assert len(client.get(f'/api/v1/organizations/{org}/bank/questions').json()) == 95


def test_invalid_extracted_question_can_be_corrected(client):
    org = register(client)['organization_id']; base = f'/api/v1/organizations/{org}/imports'
    preview = client.post(base + '/structured/preview/file', files={'file': ('test.xlsx', xlsx([['Capital?', 'Mumbai', '', 'Kolkata', 'Chennai', 'O', '']]))}).json()
    item = preview['document']['questions'][0]
    item['options'][1]['text'] = 'Delhi'; item['correct_answers'] = ['B']
    response = client.post(base + f"/structured/{preview['id']}/review", json={'document': preview['document'], 'acknowledge_unresolved': True})
    assert response.status_code == 200, response.text
    assert client.post(base + f"/{preview['id']}/commit").json()['imported'] == 1


def test_library_diagnostics_are_not_exposed(client, monkeypatch):
    org = register(client)['organization_id']
    def fail(*args): raise ValueError('Internal parser failure at C:/private/server/file')
    monkeypatch.setattr(structured, 'extract', fail)
    response = client.post(f'/api/v1/organizations/{org}/imports/structured/preview/file', files={'file': ('bad.pdf', b'%PDF-invalid')})
    assert response.status_code == 422
    assert 'private' not in response.text and 'Internal parser' not in response.text
