import asyncio
import base64
import io
import json
import zipfile
from types import SimpleNamespace
import httpx
import pytest
from pydantic import SecretStr, ValidationError
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches
from pptx.dml.color import RGBColor
from openpyxl import Workbook
from app.import_schema import CanonicalDocument, question_adapter, to_bank
from app.import_routes import parse_upload
from app.document_structure import detect_format, extract_structure
from app import document_ai
from app.import_pipeline import prepare_preview
from app.questions import Question, evaluate
from conftest import register
from test_document_import import TEXT, document


def deck_bytes(slides):
    deck=Presentation()
    for texts,notes in slides:
        slide=deck.slides.add_slide(deck.slide_layouts[6])
        for index,text in enumerate(texts):
            slide.shapes.add_textbox(Inches(1),Inches(index+1),Inches(8),Inches(1)).text=text
        if notes:slide.notes_slide.notes_text_frame.text=notes
    stream=io.BytesIO();deck.save(stream);return stream.getvalue()


def mcq(**extra):
    return {'type':'mcq','question':'Capital?','options':[{'id':'A','text':'Paris'},{'id':'B','text':'London'}],'correct_answers':['A'],**extra}


def preview(client,org,name,raw):
    response=client.post(f'/api/v1/organizations/{org}/imports/preview/file',files={'file':(name,raw,'application/octet-stream')})
    assert response.status_code==200,response.text
    return response.json()


def test_type_specific_union_and_schema_version():
    assert question_adapter.validate_python({'type':'short_answer','question':'Explain gravity'}).accepted_answers==[]
    assert question_adapter.validate_python({'type':'survey','question':'Feedback?'}).options==[]
    with pytest.raises(ValidationError):question_adapter.validate_python({'type':'survey','question':'Feedback?','correct_answers':['Yes']})
    with pytest.raises(ValidationError):question_adapter.validate_python({**mcq(),'options':[{'id':'A','text':'Paris'},{'id':'A','text':'London'}]})
    with pytest.raises(ValidationError):CanonicalDocument(schema_version='2.0',questions=[])
    with pytest.raises(ValidationError):question_adapter.validate_python({**mcq(),'correct_answers':['Z']})


def test_gemini_transport_schema_keeps_types_without_decoder_state_explosion():
    schema=document_ai.inline_schema(document_ai.Understanding)
    item=schema['properties']['document']['properties']['questions']['items']
    assert len(item['properties']['type']['enum'])>=8
    assert {'accepted_answers','correct_answers','minimum','maximum'}.issubset(item['properties'])
    assert 'marks' not in item['properties']
    assert item['required']==['question','source','type']
    assert 'oneOf' not in item
    encoded=json.dumps(schema)
    assert 'maxItems' not in encoded and 'pattern' not in encoded
    assert '"const"' not in encoded
    assert schema['properties']['document']['properties']['schema_version']['enum']==['1.0']
    # Relaxing provider transport never relaxes canonical application validation.
    with pytest.raises(ValidationError):question_adapter.validate_python(mcq(marks=-1))


def test_multislide_continuation_and_separate_answer_key():
    raw=deck_bytes([(['Question 1: Capital?','A) Paris'],None),(['B) London'],None),(['Question 2: Prime?','A) 2','B) 4'],None),(['Answer key','1. A','2. A'],None)])
    rows,errors=parse_upload(raw,'pptx')
    assert not errors
    assert len(rows)==2
    assert rows[0]['question']['correct_answers']==['Paris']
    assert rows[0]['canonical']['source']['sections']==[1,2,4]
    assert rows[1]['canonical']['source']['slide_number']==3


def test_multiple_questions_on_slide_and_notes():
    rows,errors=parse_upload(deck_bytes([(['Question 1: Capital?','A) Paris','B) London','Answer: A','Question 2: Prime?','A) 2','B) 4'], 'Answer: A')]),'pptx')
    assert not errors and len(rows)==2
    assert rows[1]['question']['correct_answers']==['2']


def test_non_mcq_types_and_ungraded_short_response():
    raw=b'Type: true_false\nEarth is round.\nAnswer: True\nQuestion 2: Describe gravity.\nType: short_answer\nAnswer: attraction\nQuestion 3: Your favorite color?\nType: survey\nA) Red\nB) Blue'
    rows,errors=parse_upload(raw,'txt')
    assert not errors
    assert [r['question']['kind'] for r in rows]==['true_false','short_answer','poll']
    assert rows[2]['question']['correct_answers']==[]
    q=Question(kind='short_answer',title='Explain')
    assert evaluate(q,{'answer':'A considered explanation'},1)==(None,0)


def test_checkmarks_are_explicit_answer_evidence():
    rows,errors=parse_upload('Question 1: Capital?\nA) Paris \u2713\nB) London'.encode(),'txt')
    assert not errors and rows[0]['question']['correct_answers']==['Paris']


def test_content_detection_rejects_mismatched_extensions():
    assert detect_format(document('pptx'),'no-extension')=='pptx'
    with pytest.raises(ValueError,match='filename'):detect_format(document('pptx'),'fake.pdf')


def test_docx_paragraphs_and_tables_preserve_order():
    raw=io.BytesIO()
    xml='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Question 1: Capital?</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Paris</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>London</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:p><w:r><w:t>Answer: A</w:t></w:r></w:p></w:body></w:document>'
    with zipfile.ZipFile(raw,'w') as archive:archive.writestr('word/document.xml',xml)
    rows,errors=parse_upload(raw.getvalue(),'docx')
    assert not errors and rows[0]['question']['correct_answers']==['Paris']


def test_json_validates_each_row_and_preserves_drafts():
    rows,errors=parse_upload(json.dumps({'schema_version':'1.0','questions':[mcq(),mcq(correct_answers=[]),mcq(correct_answers=['Z'])]}).encode(),'json')
    assert len(rows)==2 and len(errors)==1 and errors[0]['row']==3
    assert rows[1]['requires_review'] and not rows[1]['question']['correct_answers']


def test_xlsx_all_sheets_and_flexible_headers():
    book=Workbook();sheet=book.active;sheet.append(['question','A','B','answer']);sheet.append(['Capital?','Paris','London','A'])
    sheet=book.create_sheet('More');sheet.append(['type','question','accepted_answers']);sheet.append(['short_answer','Prime?','2|3'])
    output=io.BytesIO();book.save(output)
    rows,errors=parse_upload(output.getvalue(),'xlsx')
    assert not errors and len(rows)==2
    assert rows[1]['question']['correct_answers']==['2','3']


def test_missing_answer_faculty_review_and_idempotent_bank_commit(client):
    org=register(client)['organization_id'];base=f'/api/v1/organizations/{org}/imports'
    data=preview(client,org,'quiz.txt',b'Question 1: Capital?\nA) Paris\nB) London')
    assert data['review_count']==1 and not data['can_commit']
    path=f"{base}/{data['id']}"
    assert client.post(path+'/commit').status_code==422
    draft=data['document'];draft['questions'][0]['correct_answers']=['A']
    assert client.post(path+'/review',json={'document':draft,'acknowledge_unresolved':bool(data['errors'])}).json()['can_commit']
    assert client.post(path+'/commit').json()['imported']==1
    assert client.post(path+'/commit').json()['already_committed']
    assert client.post(path+'/review',json={'document':draft}).status_code==409
    assert len(client.get(f'/api/v1/organizations/{org}/bank/questions').json())==1


def test_unresolved_content_needs_explicit_acknowledgment(client):
    org=register(client)['organization_id'];data=preview(client,org,'quiz.json',json.dumps({'schema_version':'1.0','questions':[mcq(),mcq(correct_answers=['Z'])]}).encode())
    path=f"/api/v1/organizations/{org}/imports/{data['id']}/review"
    assert client.post(path,json={'document':data['document']}).status_code==422
    assert client.post(path,json={'document':data['document'],'acknowledge_unresolved':True}).json()['can_commit']


def test_review_cannot_bypass_answer_validation(client):
    org=register(client)['organization_id'];data=preview(client,org,'quiz.json',json.dumps({'schema_version':'1.0','questions':[mcq(correct_answers=[])]}).encode())
    assert client.post(f"/api/v1/organizations/{org}/imports/{data['id']}/review",json={'document':data['document']}).status_code==422


def test_review_and_suggestions_are_owner_scoped(client):
    org=register(client)['organization_id'];data=preview(client,org,'quiz.json',json.dumps({'questions':[mcq()]}).encode())
    register(client,'other@example.com')
    base=f"/api/v1/organizations/{org}/imports/{data['id']}"
    assert client.post(base+'/review',json={'document':data['document']}).status_code in {403,404}
    assert client.post(base+'/questions/0/suggest-answer').status_code in {403,404}


def ai_config(monkeypatch):
    config=SimpleNamespace(gemini_api_key=SecretStr('test-key'),gemini_question_model='gemini-2.5-flash-lite',ai_request_timeout_seconds=5,ai_max_output_tokens=8000,import_ai_max_context_chars=350000,document_conversion_url='',document_renderer_url='',document_service_token=SecretStr(''))
    monkeypatch.setattr(document_ai,'settings',lambda:config)
    return config


def test_gemini_structured_context_and_vision_are_extraction_only(monkeypatch):
    ai_config(monkeypatch)
    calls=[]
    def handler(request):
        body=json.loads(request.content);calls.append(body)
        assert request.headers['x-goog-api-key']=='test-key' and 'key=' not in str(request.url)
        assert 'never generate' in body['systemInstruction']['parts'][0]['text']
        output={'document':{'schema_version':'1.0','questions':[mcq(source={'sections':[1],'answer_evidence':'Answer: A'})]},'covered_sections':[1],'unresolved':[]}
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(output)}]}}]})
    client_class=httpx.AsyncClient
    monkeypatch.setattr(document_ai.httpx,'AsyncClient',lambda **kw:client_class(transport=httpx.MockTransport(handler),**kw))
    sections=[{'number':1,'label':'Slide 1','text':'Capital? Answer: A','blocks':[{'x':100,'y':200,'text':'Capital?'}],'images':[{'mime_type':'image/png','data':base64.b64encode(b'image').decode()}],'warnings':[]}]
    rows,errors=asyncio.run(document_ai.understand_document(sections,'quiz.pptx'))
    assert not errors and rows[0]['requires_review']
    assert rows[0]['canonical']['source']['filename']=='quiz.pptx'
    assert calls[0]['contents'][0]['parts'][-1]['inlineData']['mimeType']=='image/png'
    assert '"x": 100' in calls[0]['contents'][0]['parts'][0]['text']


def test_ai_cannot_supply_answers_without_explicit_source_evidence(monkeypatch):
    ai_config(monkeypatch)
    async def fake(*args):return {'document':{'questions':[mcq(source={'sections':[1],'answer_evidence':'Paris'})]},'covered_sections':[1],'unresolved':[]}
    monkeypatch.setattr(document_ai,'gemini_json',fake)
    sections=[{'number':1,'label':'Slide 1','text':'Capital? Paris London','blocks':[],'images':[],'warnings':[]}]
    rows,errors=asyncio.run(document_ai.understand_document(sections,'quiz.pptx'))
    assert not errors
    assert rows[0]['canonical']['correct_answers']==[]
    assert rows[0]['canonical']['answer_origin']=='missing'


def test_ai_missing_coverage_and_visual_content_are_reported(monkeypatch):
    ai_config(monkeypatch)
    async def fake(*args):return {'document':{'questions':[mcq(source={'sections':[1],'answer_evidence':'Answer: A'})]},'covered_sections':[1],'unresolved':['Unreadable chart']}
    monkeypatch.setattr(document_ai,'gemini_json',fake)
    sections=[{'number':n,'label':f'Slide {n}','text':'Answer: A','blocks':[],'images':[],'warnings':[]} for n in [1,2]]
    rows,errors=asyncio.run(document_ai.understand_document(sections,'quiz.pptx'))
    assert len(errors)==2 and rows[0]['requires_review']


def test_answer_suggestion_is_unverified_and_does_not_change_saved_preview(client,monkeypatch):
    org=register(client)['organization_id'];data=preview(client,org,'quiz.json',json.dumps({'questions':[mcq(correct_answers=[])]}).encode())
    monkeypatch.setattr('app.ai_routes.reserve_generation',lambda *args:None)
    async def fake(item):return {'answers':['A'],'explanation':'Suggested','answer_origin':'ai_suggested','verified':False}
    monkeypatch.setattr(document_ai,'suggest_answer',fake)
    base=f"/api/v1/organizations/{org}/imports/{data['id']}"
    result=client.post(base+'/questions/0/suggest-answer').json()
    assert result['verified'] is False
    assert client.post(base+'/commit').status_code==422


def test_pptx_positions_group_table_colors_and_notes():
    deck=Presentation();slide=deck.slides.add_slide(deck.slide_layouts[6])
    group=slide.shapes.add_group_shape();shape=group.shapes.add_textbox(Inches(1),Inches(1),Inches(4),Inches(1));shape.text='Question 1: Capital?';shape.text_frame.paragraphs[0].runs[0].font.color.rgb=RGBColor(255,0,0)
    table=slide.shapes.add_table(2,2,Inches(1),Inches(3),Inches(5),Inches(2)).table
    table.cell(0,0).text='A';table.cell(0,1).text='Paris';table.cell(1,0).text='B';table.cell(1,1).text='London'
    slide.notes_slide.notes_text_frame.text='Answer: A'
    output=io.BytesIO();deck.save(output)
    section=extract_structure(output.getvalue(),'pptx')[0]
    assert section['notes']=='Answer: A'
    assert any(b.get('parent') for b in section['blocks'])
    assert any(b.get('table') for b in section['blocks'])
    runs=[r for b in section['blocks'] for p in b.get('paragraphs',[]) for r in p['runs']]
    assert runs[0]['color']=='FF0000'
    rows,errors=parse_upload(output.getvalue(),'pptx')
    assert not errors and rows[0]['question']['correct_answers']==['Paris']


def test_pptx_line_auto_shape_does_not_break_extraction():
    deck=Presentation();slide=deck.slides.add_slide(deck.slide_layouts[6])
    shape=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(1),Inches(1),Inches(2),Inches(1))
    shape._element.spPr.prstGeom.set('prst','line')
    output=io.BytesIO();deck.save(output)

    section=extract_structure(output.getvalue(),'pptx')[0]

    assert any(block.get('geometry')=='line' for block in section['blocks'])


def test_short_answer_model_and_accepted_answers_are_preserved():
    rows,errors=parse_upload(b'Question 1: Explain gravity.\nType: short_answer\nAccepted answers: attraction|gravitation\nModel answer: Masses attract each other.\nExplanation: A source explanation.','txt')
    assert not errors
    item=rows[0]['canonical']
    assert item['accepted_answers']==['attraction','gravitation']
    assert item['model_answer']=='Masses attract each other.'
    assert item['answer_origin']=='source'
    assert rows[0]['question']['model_answer']==item['model_answer']


def test_repeated_question_numbers_do_not_receive_a_shared_answer_key():
    raw=deck_bytes([(['Question 1: Capital?\nA) Paris\nB) London'],None),
                    (['Question 1: Prime?\nA) 2\nB) 4'],None),
                    (['Answer key\n1. A'],None)])
    rows,errors=parse_upload(raw,'pptx')
    assert len(rows)==2
    assert all(not r['canonical']['correct_answers'] for r in rows)
    assert any('Duplicate question number' in e['message'] for e in errors)


def test_ai_suggested_json_cannot_claim_to_be_reviewed():
    rows,errors=parse_upload(json.dumps({'questions':[mcq(answer_origin='ai_suggested',requires_review=False)]}).encode(),'json')
    assert not errors and rows[0]['canonical']['requires_review']


def pipeline_config(monkeypatch):
    config=ai_config(monkeypatch)
    monkeypatch.setattr('app.config.settings',lambda:config)
    return config


def test_independent_powerpoint_textboxes_invoke_ai(monkeypatch):
    pipeline_config(monkeypatch)
    calls=[]
    async def fake(sections,filename):
        calls.append(sections)
        return [],[{'row':0,'message':'Ambiguous layout needs review'}]
    monkeypatch.setattr(document_ai,'understand_document',fake)
    raw=deck_bytes([(['Question 1: Capital?','A) Paris','B) London','Answer: A'],None)])
    rows,errors,_=asyncio.run(prepare_preview(raw,'quiz.pptx'))
    assert len(calls)==1
    assert any('fewer questions' in e['message'] for e in errors)


def test_failed_ai_preserves_draft_and_requires_review(monkeypatch):
    pipeline_config(monkeypatch)
    async def fake(*args):raise document_ai.AIGenerationError('Unavailable','unavailable')
    monkeypatch.setattr(document_ai,'understand_document',fake)
    raw=deck_bytes([(['Question 1: Capital?','A) Paris','B) London','Answer: A'],None)])
    rows,errors,_=asyncio.run(prepare_preview(raw,'quiz.pptx'))
    assert len(rows)==1 and rows[0]['requires_review']
    assert rows[0]['canonical']['requires_review']
    assert errors[0]['message']=='Unavailable'


def test_ai_usage_control_failure_keeps_a_reviewable_preview(monkeypatch):
    from fastapi import HTTPException
    pipeline_config(monkeypatch)
    def reserve():raise HTTPException(503,'Usage controls unavailable')
    raw=deck_bytes([(['Question 1: Capital?','A) Paris','B) London','Answer: A'],None)])
    rows,errors,_=asyncio.run(prepare_preview(raw,'quiz.pptx',reserve_ai=reserve))
    assert len(rows)==1 and rows[0]['requires_review']
    assert 'Usage controls unavailable' in errors[0]['message']


def test_renderer_failure_still_uses_structural_ai(monkeypatch):
    config=pipeline_config(monkeypatch);config.document_renderer_url='https://renderer.invalid'
    calls=[]
    async def render(*args):raise ValueError('Renderer unavailable')
    async def understand(sections,filename):
        calls.append(sections)
        from app.import_schema import preview_row
        return [preview_row(question_adapter.validate_python(mcq(requires_review=True)))],[]
    monkeypatch.setattr(document_ai,'render_sections',render)
    monkeypatch.setattr(document_ai,'understand_document',understand)
    raw=deck_bytes([(['Question 1: Capital?','A) Paris','B) London','Answer: A'],None)])
    rows,errors,_=asyncio.run(prepare_preview(raw,'quiz.pptx'))
    assert len(calls)==1 and len(rows)==1
    assert any('rendering failed' in e['message'] for e in errors)


def test_badges_in_separate_shapes_and_context_slides():
    deck=Presentation()
    for heading in ['Quantum Physics 5 MCQs Revision Deck','Overview']:
        slide=deck.slides.add_slide(deck.slide_layouts[6])
        slide.shapes.add_textbox(Inches(.5),Inches(.5),Inches(8),Inches(.5)).text=heading
    for number in range(1,6):
        slide=deck.slides.add_slide(deck.slide_layouts[6])
        def box(text,x,y,w=3,h=.4):
            slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h)).text=text
        box(f'MCQ {number}: Topic',.5,.2)
        box(f'{number}/5',9,.2,1)
        box('Which value is supplied?',.5,1,8)
        # Text is slightly ABOVE its badge, and XML order differs from reading order.
        for label,text,x,y in [('D','Fourth',5,3),('A','First',.5,2),('C','Third',.5,3),('B','Second',5,2)]:
            box(text,x+.6,y,3)
            box(label,x,y+.07,.4,.25)
        box('Key idea: use the source.',6,4.1)
        box('Correct Answer: B. Second',.5,4.2,5)
        box('QUANTUM PHYSICS',.5,5.1)
        box('Based on source MCQ PDF',6,5.1)
    slide=deck.slides.add_slide(deck.slide_layouts[6])
    slide.shapes.add_textbox(Inches(.5),Inches(.5),Inches(8),Inches(.5)).text='Final revision snapshot'
    stream=io.BytesIO();deck.save(stream)
    rows,errors,sections=__import__('app.import_pipeline',fromlist=['deterministic_preview']).deterministic_preview(stream.getvalue(),'pptx','quantum.pptx')
    assert not errors and len(rows)==5
    assert [s['number'] for s in sections if s.get('classification')=='context']==[1,2,8]
    for row in rows:
        assert row['question']['kind']=='mcq'
        assert row['question']['title']=='Which value is supplied?'
        assert row['question']['options']==['First','Second','Third','Fourth']
        assert row['question']['correct_answers']==['Second']
        assert row['question']['explanation']=='use the source.'
        assert 'PDF' not in row['canonical']['source']['answer_evidence']


@pytest.mark.parametrize('continued_heading',['ANSWER KEY (11-20)',''])
def test_competition_banners_and_keys_on_final_slides(continued_heading):
    slides=[(['MBA QUIZ COMPETITION','20 MCQ QUESTIONS','Business and Management'],None)]
    for number in range(1,21):
        slides.append(([f'MBA QUIZ COMPETITION | QUESTION {number}/20',f'Choose the supplied value for question {number}?','A. First','B. Second'],None))
    slides.append((['ANSWER KEY (1-10)',*[f'Q{number:02}: '+('B' if number%2==0 else 'A') for number in range(1,11)]],None))
    slides.append((([continued_heading] if continued_heading else [])+[f'Q{number}: '+('B' if number%2==0 else 'A') for number in range(11,21)],None))
    rows,errors=parse_upload(deck_bytes(slides),'pptx')
    assert not errors and len(rows)==20
    for number,row in enumerate(rows,1):
        assert row['question']['title']==f'Choose the supplied value for question {number}?'
        assert row['canonical']['correct_answers']==(['B'] if number%2==0 else ['A'])
        assert row['canonical']['source']['sections']==[number+1,22 if number<=10 else 23]
        assert row['canonical']['source']['slide_number']==number+1


def test_resolved_banner_and_final_key_do_not_depend_on_gemini(monkeypatch):
    pipeline_config(monkeypatch)
    async def unexpected(*args):pytest.fail('Resolved text-only relationships must not depend on AI')
    monkeypatch.setattr(document_ai,'understand_document',unexpected)
    raw=deck_bytes([(['Quiz | QUESTION 1/1','Capital?','A. Paris','B. London'],None),(['ANSWER KEY','Q1: A'],None)])
    rows,errors,_=asyncio.run(prepare_preview(raw,'quiz.pptx'))
    assert not errors and len(rows)==1
    assert rows[0]['canonical']['correct_answers']==['A']
