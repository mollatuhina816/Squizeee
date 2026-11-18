"""Regressions for the user's zero-question PDF preview."""
import asyncio
import io

import pytest
from pydantic import SecretStr
from reportlab.pdfgen.canvas import Canvas

from app import document_ai, structured_import
from app.config import settings
from app.document_import import split_inline_question_parts
from app.import_pipeline import prepare_preview
from app.import_schema import to_bank
from app.import_parser import parse_question
from conftest import register


EXAMPLES = [
    ('What is the time complexity of binary search?', ['O(n)', 'O(log n)', 'O(n log n)', 'O(1)'], 'B) O(log n)', 'Binary search halves the search space at each step.'),
    ('Which data structure follows the LIFO principle?', ['Queue', 'Linked List', 'Stack', 'Tree'], 'C) Stack', 'LIFO means Last In, First Out.'),
    ('Which traversal visits nodes in Left-Root-Right order?', ['Preorder', 'Inorder', 'Postorder', 'Level order'], 'B) Inorder', 'Inorder traversal processes the left subtree, root, then the right subtree.'),
    ('What is the worst-case time complexity of linear search?', ['O(1)', 'O(log n)', 'O(n)', 'O(n squared)'], 'C) O(n)', ''),
    ('Which data structure is commonly used to implement BFS?', ['Stack', 'Queue', 'Heap', 'Hash table'], 'B) Queue', 'BFS explores nodes level by level using a queue.'),
]


def example_pdf():
    out = io.BytesIO(); pdf = Canvas(out)
    y = 800
    for index, (title, options, answer, explanation) in enumerate(EXAMPLES, 1):
        if index == 5: pdf.showPage(); y = 800
        lines = [f'Question {index}: {title}', ' '.join(f'{chr(65+i)}) {value}' for i, value in enumerate(options)), 'Answer: '+answer, explanation]
        for line in lines:
            pdf.drawString(30, y, line); y -= 18
        y -= 20
    pdf.save()
    return out.getvalue()


def test_mathematical_parentheses_are_not_option_labels():
    parts = split_inline_question_parts('A) O(n) B) O(log n) C) O(n log n) D) O(1)')
    assert parts == ['A) O(n)', 'B) O(log n)', 'C) O(n log n)', 'D) O(1)']
    assert split_inline_question_parts('A) O(log N) B) P(A) C) O(N) D) O(1)') == ['A) O(log N)', 'B) P(A)', 'C) O(N)', 'D) O(1)']


def test_letter_only_answer_with_unlabelled_explanation():
    item = parse_question(['LIFO?', 'A) Queue', 'B) Stack', 'Answer: B', 'LIFO means Last In, First Out.'], {})
    assert item.correct_answers == ['B'] and item.requires_review
    assert item.explanation == 'LIFO means Last In, First Out.'


@pytest.mark.parametrize('index', range(5))
def test_screenshot_answers_and_unlabelled_explanations(index):
    title, opts, answer, explanation = EXAMPLES[index]
    question = parse_question([title, *[f'{chr(65+i)}) {text}' for i,text in enumerate(opts)], 'Answer: '+answer, *([explanation] if explanation else [])], {})
    assert question.question == title
    assert [o.text for o in question.options] == opts
    assert question.correct_answers == [answer[0]]
    assert question.explanation == explanation
    assert question.requires_review == bool(explanation)


def test_ai_preview_retains_conflicting_answer_for_manual_review(monkeypatch):
    monkeypatch.setattr(settings(), 'gemini_api_key', SecretStr(''))
    text = b'Question 1: Capital?\nA) Paris\nB) London\nAnswer: A) London'
    rows, errors, _ = asyncio.run(prepare_preview(text, 'questions.txt'))
    assert len(rows) == 1 and errors and rows[0]['requires_review']
    item = rows[0]['canonical']
    assert item['question'] == 'Capital?' and item['correct_answers'] == []
    assert 'A) London' in item['source']['answer_evidence']
    assert item['options'][1]['text'] == 'London'


@pytest.mark.parametrize('method', ['', 'structured/'])
def test_screenshot_pdf_upload_review_and_existing_bank(client, monkeypatch, method):
    org = register(client)['organization_id']; base = f'/api/v1/organizations/{org}/imports'
    def forbidden(*args, **kwargs): pytest.fail('Readable source answers should not require an AI call')
    monkeypatch.setattr(document_ai, 'understand_document', forbidden)
    monkeypatch.setattr(settings(), 'gemini_api_key', SecretStr('configured-test-key'))
    if method:
        monkeypatch.setattr('app.import_routes.ai_reservation', forbidden)
        monkeypatch.setattr('app.import_routes.prepare_preview', forbidden)
        monkeypatch.setattr(structured_import, 'ocr_image', forbidden)
    response = client.post(base + f'/{method}preview/file', files={'file': ('screenshot-example.pdf', example_pdf())})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert len(preview['rows']) == 5 and not preview['errors']
    assert [q['correct_answers'] for q in preview['document']['questions']] == [['B'], ['C'], ['B'], ['C'], ['B']]
    assert preview['review_count'] == 4 and not preview['can_commit']
    response = client.post(base + f"/{method}{preview['id']}/review", json={'document':preview['document']})
    assert response.status_code == 200, response.text
    assert response.json()['can_commit']
    assert client.post(base + f"/{preview['id']}/commit").json()['imported'] == 5
    bank = client.get(f'/api/v1/organizations/{org}/bank/questions').json()
    assert len(bank) == 5
    assert {q['question']['correct_answers'][0] for q in bank} == {'O(log n)', 'Stack', 'Inorder', 'O(n)', 'Queue'}


def test_structured_conflicting_answers_stay_editable():
    text = 'Question 1: Capital?\nA. Paris\nB. London\nC. Rome\nD. Madrid\nCorrect Answer: A) London'
    rows = structured_import.text_candidates(text, {})
    assert len(rows) == 1 and rows[0]['canonical']['correct_answers'] == []
    assert structured_import.validate_candidate(rows[0]['canonical'], set())


def test_numbered_questions_with_heading_and_cross_page_explanation():
    from app.import_parser import parse_structure
    from app.structured_import import text_candidates
    pages = ['DSA - 5 Multiple-Choice Questions\nData Structures and Algorithms | Questions with Answers\n', 'In the worst case, every element may need to be checked.\n']
    for index, (title, options, answer, explanation) in enumerate(EXAMPLES, 1):
        lines = [f'{index}. {title}', *[f'{chr(65+i)}) {value}' for i, value in enumerate(options)], 'Answer: '+answer]
        if explanation: lines.append(explanation)
        pages[int(index == 5)] += '\n'.join(lines)+'\n'
    sections = [{'number': i, 'label': f'Page {i}', 'text': text} for i, text in enumerate(pages, 1)]
    smart, errors = parse_structure(sections, 'numbered.pdf', 'pdf')
    assert not errors
    structured = text_candidates('\n'.join(pages), {'filename': 'numbered.pdf'})
    for rows in [smart, structured]:
        assert len(rows) == 5
        assert [r['canonical']['correct_answers'] for r in rows] == [['B'], ['C'], ['B'], ['C'], ['B']]
        assert rows[0]['canonical']['question'] == EXAMPLES[0][0]
        assert 'every element' in rows[3]['canonical']['explanation']
    assert not any(row['issues'] for row in structured)
