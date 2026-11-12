from sqlalchemy import select
from app.models import LiveSession, Participant
from test_builder_live import setup_session, QUESTION


def test_saved_self_paced_options_survive_reload_and_control_new_sessions(client, monkeypatch, store):
    _, base, presentation = setup_session(client, monkeypatch)
    slides = f"{base}/{presentation['id']}/slides"
    current = client.get(slides).json()
    options = {'delivery_mode':'self_paced', 'team_mode':True, 'streaks':True, 'allow_guests':False}
    saved = client.put(slides, json={'revision':current['revision'], 'questions':[QUESTION, {**QUESTION,'title':'Next'}], 'live_settings':options})
    assert saved.status_code == 200, saved.text
    assert client.get(slides).json()['live_settings'] == options
    created = client.post(f"{base}/{presentation['id']}/sessions").json()
    host_url = f"/api/v1/sessions/{created['id']}"
    host = client.get(host_url+'/host').json()
    assert host['delivery_mode'] == 'self_paced'
    joined = client.post('/api/v1/sessions/join', json={'code':created['join_code'], 'email':'student@example.com','name':'Student','phone':'+919000000001'}).json()
    headers = {'X-Participant-Token':joined['token']}
    assert client.post(host_url+'/control', json={'action':'open','revision':host['revision']}).status_code == 200
    response = client.post(host_url+'/responses', headers=headers, json={'question_index':0,'answer':'2'})
    assert response.status_code == 201, response.text
    assert response.json()['snapshot']['active_index'] == 1
    assert response.json()['snapshot']['question']['title'] == 'Next'
    with store() as db:
        sessions = list(db.scalars(select(LiveSession)))
        assert any(s.live_settings == options for s in sessions)


def test_existing_session_unchanged_and_explicit_mode_can_override_saved_settings(client, monkeypatch):
    old, base, presentation = setup_session(client, monkeypatch)
    slides = f"{base}/{presentation['id']}/slides"
    current = client.get(slides).json()
    assert client.put(slides, json={'revision':current['revision'],'questions':current['questions'],
        'live_settings':{'delivery_mode':'guided'}}).status_code == 200
    assert client.get(f"/api/v1/sessions/{old['id']}/host").json()['delivery_mode'] == 'self_paced'
    new = client.post(f"{base}/{presentation['id']}/sessions", json={'delivery_mode':'self_paced'}).json()
    assert client.get(f"/api/v1/sessions/{new['id']}/host").json()['delivery_mode'] == 'self_paced'


def test_invalid_pacing_rejected_without_changing_presentation(client, monkeypatch):
    _, base, presentation = setup_session(client, monkeypatch)
    slides = f"{base}/{presentation['id']}/slides"
    current = client.get(slides).json()
    response = client.put(slides, json={'revision':current['revision'],'questions':current['questions'],
        'live_settings':{'delivery_mode':'invalid'}})
    assert response.status_code == 422
    assert client.get(slides).json()['revision'] == current['revision']
