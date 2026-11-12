from datetime import datetime, timedelta, timezone
import uuid

import pytest
from app.models import LiveSession, Participant, ParticipantProfile
from app.questions import Question, evaluate
from app.student_routes import maximum_score
from test_builder_live import QUESTION, setup_session


def guest(client, session, name='Guest', token=''):
    result = client.post('/api/v1/sessions/join', headers={'X-Participant-Token': token},
                         json={'code': session['join_code'], 'name': name, 'guest': True})
    assert result.status_code == 201, result.text
    return result.json()


def configure(store, session, **options):
    with store() as db:
        live = db.get(LiveSession, uuid.UUID(session['id']))
        live.live_settings = options
        live.questions = [{**QUESTION, 'speaker_notes': 'PRIVATE notes'} for _ in range(5)]
        db.commit()


def command(client, base, action):
    revision = client.get(base + '/host').json()['revision']
    response = client.post(base + '/control', json={'action': action, 'revision': revision})
    assert response.status_code == 200, response.text


def test_guest_resume_teams_and_no_profile_creation(client, monkeypatch, store):
    session, _, _ = setup_session(client, monkeypatch)
    configure(store, session, team_mode=True)
    first = guest(client, session)
    resumed = guest(client, session, token=first['token'])
    assert first == resumed
    for i in range(7):
        guest(client, session, str(i))
    with store() as db:
        assert db.query(ParticipantProfile).count() == 0
        assert db.query(Participant).count() == 8
    host = client.get(f"/api/v1/sessions/{session['id']}/host").json()
    assert [t['members'] for t in host['teams']] == [2, 2, 2, 2]
    configure(store, session, allow_guests=False)
    assert client.post('/api/v1/sessions/join', json={'code': session['join_code'], 'name': 'No', 'guest': True}).status_code == 403


def test_guided_pause_reveal_progression_and_streak_scores(client, monkeypatch, store):
    session, _, _ = setup_session(client, monkeypatch)
    configure(store, session, delivery_mode='guided', streaks=True, team_mode=True)
    joined = guest(client, session)
    base = f"/api/v1/sessions/{session['id']}"
    headers = {'X-Participant-Token': joined['token']}
    command(client, base, 'open')
    command(client, base, 'pause')
    with store() as db:
        live = db.get(LiveSession, uuid.UUID(session['id']))
        live.opened_at = datetime.now(timezone.utc) - timedelta(seconds=90)
        live.paused_at = datetime.now(timezone.utc) - timedelta(seconds=89)
        db.commit()
    assert client.post(base + '/responses', headers=headers, json={'question_index': 0, 'answer': '2'}).status_code == 409
    command(client, base, 'resume')
    current = client.get(base + '/participant', headers=headers).json()
    assert 'speaker_notes' not in current['question']
    assert current['reveal'] is None
    assert current['paused_at'] is None
    assert client.get(base + '/host').json()['speaker_notes'] == 'PRIVATE notes'
    for index in range(5):
        result = client.post(base + '/responses', headers=headers, json={'question_index': index, 'answer': '2'})
        assert result.status_code == 201, result.text
        data = result.json()['snapshot']
        assert data['active_index'] == index  # never advance before presenter
        assert data['answered'] is True
        assert data['state'] == 'open'  # final answer waits for the host, too
        assert client.post(base + '/responses', headers=headers, json={'question_index': index, 'answer': '2'}).status_code == 409
        command(client, base, 'close')
        command(client, base, 'reveal')
        assert client.get(base + '/participant', headers=headers).json()['reveal']['correct_answers'] == ['2']
        rev = client.get(base + '/host').json()['revision']
        assert client.post(base + '/control', json={'action': 'reopen', 'revision': rev}).status_code == 409
        if index < 4:
            command(client, base, 'next')
            assert client.get(base + '/participant', headers=headers).json()['answered'] is False
            command(client, base, 'open')
    host = client.get(base + '/host').json()
    assert host['leaderboard'][0]['streak'] == 5
    assert host['leaderboard'][0]['score'] > 19000
    assert host['teams'][0]['score'] == host['leaderboard'][0]['score']
    assert client.get(base + '/results', headers=headers).status_code == 409
    command(client, base, 'end')
    assert client.get(base + '/results', headers=headers).status_code == 200


def test_moderated_audience_votes_and_session_isolation(client, monkeypatch, store):
    session, _, _ = setup_session(client, monkeypatch)
    first, second = guest(client, session, 'One'), guest(client, session, 'Two')
    a, b = ({'X-Participant-Token': p['token']} for p in (first, second))
    base = f"/api/v1/sessions/{session['id']}"
    result = client.post(base + '/audience', headers=a, json={'text': 'Why is two prime?'})
    assert result.status_code == 201
    qid = result.json()['id']
    assert client.get(base + '/audience', headers=b).json()['questions'] == []
    assert client.get(base + '/audience', headers=a).json()['questions'][0]['status'] == 'pending'
    assert client.post(base + f'/audience/{qid}/vote', headers=b).status_code == 404
    assert client.post(base + f'/audience/{qid}/moderate', json={'status': 'approved'}).status_code == 200
    assert client.post(base + f'/audience/{qid}/vote', headers=a).status_code == 409
    for _ in range(2):
        assert client.post(base + f'/audience/{qid}/vote', headers=b).status_code == 200
    assert client.get(base + '/audience', headers=b).json()['questions'][0]['votes'] == 1
    assert client.get(base + '/audience').status_code == 401
    client.cookies.clear()
    assert client.post(base + f'/audience/{qid}/moderate', headers=b, json={'status': 'hidden'}).status_code == 401


def test_reactions_and_random_picker_do_not_publish_credentials(client, monkeypatch):
    session, _, _ = setup_session(client, monkeypatch)
    joined = guest(client, session)
    events = []
    monkeypatch.setattr('app.live_routes.publish_event', lambda sid, event: events.append(event))
    base = f"/api/v1/sessions/{session['id']}"
    headers = {'X-Participant-Token': joined['token']}
    assert client.post(base + '/reactions', headers=headers, json={'emoji': '🔥'}).status_code == 202
    assert client.post(base + '/reactions', headers=headers, json={'emoji': '<script>'}).status_code == 422
    assert client.post(base + '/reactions', json={'emoji': '🔥'}).status_code == 401
    assert client.post(base + '/picker').json()['participant_id'] == joined['participant_id']
    assert all('token' not in str(e) and 'email' not in str(e) for e in events)


def test_hotspot_ranking_validation_and_maximum_score():
    q = Question(kind='hotspot', title='Pin it', image_url='https://example.com/map.png',
                 hotspot_target={'x': .5, 'y': .5, 'radius': .1}, speaker_notes='secret')
    assert evaluate(q, {'answer': {'x': .5, 'y': .5}}, 0) == (True, 1000)
    assert evaluate(q, {'answer': {'x': .9, 'y': .9}}, 0) == (False, 0)
    assert 'hotspot_target' not in q.public()
    assert 'speaker_notes' not in q.public()
    for invalid in ({'x': float('nan'), 'y': .5}, {'x': True, 'y': .5}, {'x': 2, 'y': 0}):
        with pytest.raises(ValueError):
            evaluate(q, {'answer': invalid}, 0)
    ranking = Question(kind='ranking', title='Order', options=['A', 'B'], correct_answers=['B', 'A'])
    assert evaluate(ranking, {'answer': ['B', 'A']}, 0)[0] is True
    assert evaluate(ranking, {'answer': ['A', 'B']}, 0)[0] is False
    assert maximum_score([QUESTION] * 5, streaks=True) == 21000
