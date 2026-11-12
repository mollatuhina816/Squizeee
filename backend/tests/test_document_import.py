import base64
import io
import zipfile

import pytest
from pptx import Presentation
from pptx.util import Inches
from reportlab.pdfgen.canvas import Canvas

from app.import_routes import parse_upload
from conftest import register

TEXT = 'Question 1: Capital of France?\nA) Paris\nB) London\nAnswer: A\nExplanation: Paris is the capital.\nMarks: 2'


def document(format, text=TEXT, notes=None):
    output = io.BytesIO()
    if format == 'pdf':
        canvas = Canvas(output)
        for i, line in enumerate(text.splitlines()):
            canvas.drawString(40, 800 - i * 18, line)
        canvas.showPage(); canvas.save()
    else:
        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(5)).text = text
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
        deck.save(output)
    return output.getvalue()


@pytest.mark.parametrize('format', ['pdf', 'pptx'])
def test_extract_answer_and_explanation(format):
    rows, errors = parse_upload(document(format), format)
    assert not errors
    q = rows[0]['question']
    assert q['title'] == 'Capital of France?'
    assert q['correct_answers'] == ['Paris']
    assert q['explanation'] == 'Paris is the capital.'
    assert q['marks'] == '2'


def test_pptx_answer_in_speaker_notes():
    rows, errors = parse_upload(document('pptx', 'Question 1: Prime numbers?\nA) 2\nB) 4\nC) 3', 'Answer: A, C'), 'pptx')
    assert not errors
    assert rows[0]['question']['kind'] == 'multiple_select'
    assert rows[0]['question']['correct_answers'] == ['2', '3']


def test_pptx_with_embedded_payloads_imports_slide_text_only():
    source = document('pptx')
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(output, 'w') as deck:
        for item in original.infolist():
            deck.writestr(item, original.read(item.filename))
        deck.writestr('ppt/embeddings/embedded.bin', b'embedded payload is not extracted')
        deck.writestr('ppt/vbaProject.bin', b'macro payload is never executed')

    rows, errors = parse_upload(output.getvalue(), 'pptx')
    assert not errors
    assert rows[0]['question']['title'] == 'Capital of France?'
    assert b'embedded payload' not in str(rows).encode()


def test_multiple_questions_on_pdf_page():
    rows, errors = parse_upload(document('pdf', TEXT + '\nQuestion 2: Two plus two?\nA) 4\nB) 5\nAnswer: 4'), 'pdf')
    assert not errors
    assert len(rows) == 2
    assert rows[1]['question']['correct_answers'] == ['4']


@pytest.mark.parametrize('answer', ['', 'Answer: Z', 'Answer: A) London'])
def test_no_inferred_or_mismatched_answers(answer):
    rows, errors = parse_upload(document('pdf', 'Capital?\nA) Paris\nB) London\n' + answer), 'pdf')
    if not answer:
        assert not errors and rows[0]['requires_review']
        assert rows[0]['question']['correct_answers'] == []
    else:
        assert not rows
        assert 'Page 1' in errors[0]['message']


def test_pptx_single_line_question_with_inline_options_and_answer():
    rows, errors = parse_upload(document('pptx', 'Question 1: Capital of France? A) Paris B) London C) Berlin Answer: A'), 'pptx')
    assert not errors
    assert rows[0]['question']['title'] == 'Capital of France?'
    assert rows[0]['question']['options'] == ['Paris', 'London', 'Berlin']
    assert rows[0]['question']['correct_answers'] == ['Paris']


def test_unreadable_and_encrypted_pdf():
    rows, errors = parse_upload(document('pdf', ''), 'pdf')
    assert not rows and 'OCR' in errors[0]['message']
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(document('pdf'))))
    writer.encrypt('secret'); output = io.BytesIO(); writer.write(output)
    with pytest.raises(ValueError, match='Password-protected'):
        parse_upload(output.getvalue(), 'pdf')


@pytest.mark.parametrize('format', ['pdf', 'pptx'])
def test_import_append_preserves_existing_and_answers(client, format):
    org = register(client)['organization_id']
    base = f'/api/v1/organizations/{org}'
    p = client.post(base + '/presentations', json={'title': 'Imported quiz'}).json()
    slides = f"{base}/presentations/{p['id']}/slides"
    existing = {'kind': 'mcq', 'title': 'Existing?', 'options': ['Yes', 'No'], 'correct_answers': ['Yes']}
    assert client.put(slides, json={'revision': 1, 'questions': [existing]}).status_code == 200
    preview = client.post(base + '/imports/preview', json={'format': format, 'content_base64': base64.b64encode(document(format)).decode()}).json()
    assert preview['can_commit']
    path = f"{base}/imports/{preview['id']}/presentation/{p['id']}"
    assert client.post(path, json={'revision': 1}).status_code == 409
    result = client.post(path, json={'revision': 2})
    assert result.status_code == 200, result.text
    assert result.json()['revision'] == 3
    assert [q['title'] for q in result.json()['questions']] == ['Existing?', 'Capital of France?']
    assert client.get(slides).json()['questions'][1]['correct_answers'] == ['Paris']
    assert client.post(path, json={'revision': 3}).status_code == 409
    assert len(client.get(slides).json()['questions']) == 2


def test_invalid_document_blocks_save_and_other_owner(client):
    org = register(client)['organization_id']
    base = f'/api/v1/organizations/{org}'
    p = client.post(base + '/presentations', json={'title': 'Quiz'}).json()
    preview = client.post(base + '/imports/preview', json={'format': 'pptx', 'content_base64': base64.b64encode(document('pptx', 'Question?\nA) Yes\nB) No')).decode()}).json()
    path = f"{base}/imports/{preview['id']}/presentation/{p['id']}"
    assert not preview['can_commit']
    assert client.post(path, json={'revision': 1}).status_code == 422
    register(client, 'other@example.com')
    assert client.post(path, json={'revision': 1}).status_code in {403, 404}


@pytest.mark.parametrize('format', ['pdf', 'pptx'])
def test_corrupt_document_returns_validation_error(client, format):
    org = register(client)['organization_id']
    response = client.post(f'/api/v1/organizations/{org}/imports/preview', json={'format': format, 'content_base64': base64.b64encode(b'broken document').decode()})
    assert response.status_code == 422


def test_multipart_powerpoint_upload_preview(client):
    org = register(client)['organization_id']
    response = client.post(
        f'/api/v1/organizations/{org}/imports/preview/file',
        files={'file': ('lesson.pptx', document('pptx'), 'application/vnd.openxmlformats-officedocument.presentationml.presentation')},
    )
    assert response.status_code == 200, response.text
    assert response.json()['can_commit']
    assert response.json()['rows'][0]['question']['title'] == 'Capital of France?'


def test_multipart_import_rejects_unsupported_file_type(client):
    org = register(client)['organization_id']
    response = client.post(
        f'/api/v1/organizations/{org}/imports/preview/file',
        files={'file': ('lesson.ppt', b'legacy PowerPoint', 'application/octet-stream')},
    )
    assert response.status_code == 415


@pytest.mark.parametrize('answer', ['Ans: A', 'Correct Answer - (A)', 'Answer: A) Paris', 'Answer: Option A', 'Answer:\nA'])
def test_common_answer_formats(answer):
    rows, errors = parse_upload(document('pdf', '1. Capital?\nA) Paris\nB) London\n' + answer), 'pdf')
    assert not errors
    assert rows[0]['question']['correct_answers'] == ['Paris']


def test_heading_and_question_split_across_pdf_pages():
    from app.document_import import parse_sections
    rows, errors = parse_sections([
        ('Page 1', 'Geography Quiz\nChoose the correct answer\n1. Capital of France?\nA) Paris\nB) London\nAnswer: A\n2. Capital of Italy?\nA) Rome\nPage 1 of 2'),
        ('Page 2', 'B) Paris\nCorrect Answer: (A)\nPage 2 of 2'),
    ])
    assert not errors
    assert len(rows) == 2
    assert rows[1]['question']['title'] == 'Capital of Italy?'
    assert rows[1]['question']['correct_answers'] == ['Rome']


def test_missing_key_not_silently_skipped_with_heading():
    from app.document_import import parse_sections
    rows, errors = parse_sections([('Page 1', 'Quiz heading\n1. Missing key?\nA) Yes\nB) No\n2. Has key?\nA) Yes\nB) No\nAnswer: A')])
    assert len(rows) == 1 and len(errors) == 1
    assert 'Missing key?' in errors[0]['message']
