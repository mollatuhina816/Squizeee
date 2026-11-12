from sqlalchemy import select
from datetime import datetime, timedelta, timezone
import pytest
from app.models import LiveSession
from test_builder_live import setup_session, QUESTION


def test_question_only_reveal_options_and_teacher_advances_everyone(client, monkeypatch, store):
    session, _, _ = setup_session(client, monkeypatch)
    with store() as db:
        live = db.scalar(select(LiveSession))
        live.live_settings = {'delivery_mode':'guided'}
        live.questions = [QUESTION, {**QUESTION,'title':'Second question'}]
        db.commit()
    base = f"/api/v1/sessions/{session['id']}"
    joined = client.post('/api/v1/sessions/join',json={'code':session['join_code'],'name':'Student','guest':True}).json()
    headers = {'X-Participant-Token':joined['token']}
    def control(action):
        revision = client.get(base+'/host').json()['revision']
        return client.post(base+'/control',json={'action':action,'revision':revision})
    assert control('show_question').status_code == 200
    first = client.get(base+'/participant',headers=headers).json()
    assert first['state'] == 'question'
    assert first['question']['title'] == QUESTION['title']
    assert first['question']['options'] == []
    assert first['reveal'] is None
    with store() as db:
        assert db.scalar(select(LiveSession)).opened_at is None
    assert client.post(base+'/responses',headers=headers,json={'question_index':0,'answer':'2'}).status_code == 409
    assert control('reveal_options').status_code == 200
    current = client.get(base+'/participant',headers=headers).json()
    assert current['state'] == 'open'
    assert current['question']['options'] == QUESTION['options']
    assert current['reveal'] is None
    assert client.post(base+'/responses',headers=headers,json={'question_index':0,'answer':'2'}).status_code == 201
    assert control('next_question').status_code == 200
    next_question = client.get(base+'/participant',headers=headers).json()
    assert next_question['active_index'] == 1 and not next_question['answered']
    assert next_question['state'] == 'question' and next_question['question']['options'] == []
    assert next_question['question']['title'] == 'Second question'
    assert control('next_question').status_code == 409
    assert control('reveal_options').status_code == 200


def test_staged_controls_unavailable_for_self_paced(client,monkeypatch):
    session, _, _ = setup_session(client,monkeypatch)
    base = f"/api/v1/sessions/{session['id']}"
    for action in ['show_question','reveal_options','next_question']:
        assert client.post(base+'/control',json={'action':action,'revision':1}).status_code == 409


@pytest.mark.parametrize('mode,expected', [('guided',201),('self_paced',409)])
def test_only_self_paced_answers_expire(client,monkeypatch,store,mode,expected):
    session, _, _ = setup_session(client,monkeypatch)
    base = f"/api/v1/sessions/{session['id']}"
    joined = client.post('/api/v1/sessions/join',json={'code':session['join_code'],'name':'Student','guest':True}).json()
    headers = {'X-Participant-Token':joined['token']}
    assert client.post(base+'/control',json={'action':'open','revision':1}).status_code == 200
    with store() as db:
        live = db.scalar(select(LiveSession))
        live.live_settings = {'delivery_mode':mode}
        live.opened_at = datetime.now(timezone.utc)-timedelta(hours=2)
        from app.models import Participant
        db.scalar(select(Participant)).created_at = live.opened_at
        db.commit()
    answer = client.post(base+'/responses',headers=headers,json={'question_index':0,'answer':'2'})
    assert answer.status_code == expected,answer.text
    assert client.post(base+'/control',json={'action':'close','revision':2}).status_code == 200
    assert client.post(base+'/responses',headers=headers,json={'question_index':0,'answer':'2'}).status_code == 409
