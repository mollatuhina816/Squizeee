import uuid
from datetime import datetime, timedelta, timezone

from app.models import LiveSession
from test_builder_live import setup_session


def test_reopen_accepts_answers_preserves_timer_and_rejects_stale_controls(client, monkeypatch):
    session, _, _ = setup_session(client, monkeypatch)
    base = f"/api/v1/sessions/{session['id']}"
    joined = client.post('/api/v1/sessions/join', json={
        'code': session['join_code'], 'email': 'learner@example.com',
        'name': 'Learner', 'phone': '+919000000001',
    }).json()
    headers = {'X-Participant-Token': joined['token']}
    assert client.post(base+'/control', json={'action': 'reopen', 'revision': 1}).status_code == 409
    assert client.post(base+'/control', json={'action': 'open', 'revision': 1}).status_code == 200
    before = client.get(base+'/participant', headers=headers).json()
    assert client.post(base+'/control', json={'action': 'close', 'revision': 2}).status_code == 200
    answer = {'question_index': 0, 'answer': '2'}
    assert client.post(base+'/responses', headers=headers, json=answer).status_code == 409
    assert client.post(base+'/control', json={'action': 'reopen', 'revision': 3}).status_code == 200
    after = client.get(base+'/participant', headers=headers).json()
    assert after['state'] == 'open'
    assert after['opened_at'] == before['opened_at']
    assert after['score'] == before['score']
    assert client.post(base+'/control', json={'action': 'reopen', 'revision': 3}).status_code == 409
    assert client.post(base+'/responses', headers=headers, json=answer).status_code == 201
    assert client.post(base+'/responses', headers=headers, json=answer).status_code == 409
    assert client.post(base+'/control', json={'action': 'end', 'revision': 4}).status_code == 200
    assert client.post(base+'/control', json={'action': 'reopen', 'revision': 5}).status_code == 409


def test_reopen_does_not_reset_expired_deadline(client, monkeypatch, store):
    session, _, _ = setup_session(client, monkeypatch)
    base = f"/api/v1/sessions/{session['id']}"
    client.post(base+'/control', json={'action': 'open', 'revision': 1})
    with store() as db:
        live = db.get(LiveSession, uuid.UUID(session['id']))
        live.opened_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    before = client.get(base+'/host').json()['opened_at']
    client.post(base+'/control', json={'action': 'close', 'revision': 2})
    assert client.post(base+'/control', json={'action': 'reopen', 'revision': 3}).status_code == 200
    assert client.get(base+'/host').json()['opened_at'] == before
