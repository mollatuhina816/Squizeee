from sqlalchemy import select, func
from app.models import Answer, Participant, ParticipantProfile, LiveSession
from test_builder_live import setup_session, QUESTION
import uuid


def test_rejoin_preserves_attempt_answers_score_and_timer(client, monkeypatch, store):
    session, _, _ = setup_session(client, monkeypatch)
    sid = session['id']
    with store() as db:
        live = db.get(LiveSession, uuid.UUID(sid))
        live.questions = [QUESTION, {**QUESTION, 'title': 'Second'}]
        db.commit()
    entry = {'code': session['join_code'], 'email': 'student@example.com', 'name': 'Student', 'phone': '+919000000001'}
    joined = client.post('/api/v1/sessions/join', json=entry).json()
    headers = {'X-Participant-Token': joined['token']}
    client.post(f'/api/v1/sessions/{sid}/control', json={'action': 'open', 'revision': 1})
    accepted = client.post(f'/api/v1/sessions/{sid}/responses', headers=headers, json={'question_index': 0, 'answer': '2'}).json()['snapshot']
    client.cookies.clear() # Closing a browser need not retain any login cookie.
    for code in [session['join_code'], sid]:
        resumed = client.post('/api/v1/sessions/join', headers=headers, json={'code': code, 'email': entry['email']})
        assert resumed.status_code == 201
        assert resumed.json() == joined
        state = client.get(f'/api/v1/sessions/{sid}/participant', headers=headers).json()
        assert state['active_index'] == 1
        assert state['score'] == accepted['score']
        assert state['opened_at'] == accepted['opened_at']
    assert client.post('/api/v1/sessions/join', json=entry).status_code == 409
    assert client.post('/api/v1/sessions/join', headers={'X-Participant-Token': 'forged'}, json=entry).status_code == 409
    with store() as db:
        for model in [Answer, Participant, ParticipantProfile]:
            assert db.scalar(select(func.count()).select_from(model)) == 1
    client.post(f'/api/v1/sessions/{sid}/responses', headers=headers, json={'question_index': 1, 'answer': '2'})
    assert client.get(f'/api/v1/sessions/{sid}/participant', headers=headers).json()['completed'] is True
