from sqlalchemy import func, select

from app.models import Participant, ParticipantProfile
from test_builder_live import setup_session


def test_first_visit_requires_phone_then_name_reuses_profile(client, monkeypatch, store):
    live, base, presentation = setup_session(client, monkeypatch)
    entry = {'code': live['join_code'], 'name': 'Asha', 'join_by_name': True}
    assert client.post('/api/v1/sessions/join', json=entry).json()['registration_required']
    first = client.post('/api/v1/sessions/join', json={**entry, 'phone': '+91 90000 00001'})
    assert first.status_code == 201 and 'token' in first.json()
    assert 'quizeee_profile' in client.cookies
    second = client.post(f"{base}/{presentation['id']}/sessions").json()
    joined = client.post('/api/v1/sessions/join', json={**entry, 'code': second['join_code'], 'name': 'ASHA'})
    assert 'token' in joined.json(), joined.text
    with store() as db:
        assert db.scalar(select(func.count()).select_from(ParticipantProfile)) == 1
        profile = db.scalar(select(ParticipantProfile))
        assert profile.phone == '+919000000001' and profile.email is None
        assert db.scalar(select(func.count()).select_from(Participant)) == 2


def test_student_details_are_saved_per_quiz_and_update_on_resume(client, monkeypatch, store):
    live, base, presentation = setup_session(client, monkeypatch)
    entry = {
        'code': live['join_code'],
        'name': 'Asha',
        'join_by_name': True,
        'stream': 'Science',
        'semester': 'Semester 1',
        'institution_name': 'North College',
    }
    assert client.post('/api/v1/sessions/join', json=entry).json()['registration_required']
    first = client.post('/api/v1/sessions/join', json={**entry, 'phone': '+919000000001'}).json()
    headers = {'X-Participant-Token': first['token']}
    second_session = client.post(f'{base}/{presentation["id"]}/sessions').json()
    second_entry = {
        **entry,
        'code': second_session['join_code'],
        'stream': 'Arts',
        'semester': 'Semester 2',
        'institution_name': 'South Institute',
    }
    second = client.post('/api/v1/sessions/join', json=second_entry).json()
    assert second['participant_id'] != first['participant_id']
    resumed = client.post(
        '/api/v1/sessions/join',
        headers=headers,
        json={
            **entry,
            'stream': 'Commerce',
            'semester': 'Semester 3',
            'institution_name': 'West University',
        },
    )
    assert resumed.json()['participant_id'] == first['participant_id']

    with store() as db:
        participants = list(db.scalars(select(Participant).order_by(Participant.created_at)))
        assert {(p.stream, p.semester, p.institution_name) for p in participants} == {
            ('Commerce', 'Semester 3', 'West University'),
            ('Arts', 'Semester 2', 'South Institute'),
        }


def test_same_name_on_another_browser_does_not_identify_existing_student(client, monkeypatch, store):
    live, _, _ = setup_session(client, monkeypatch)
    entry = {'code': live['join_code'], 'name': 'Asha', 'join_by_name': True}
    first = client.post('/api/v1/sessions/join', json={**entry, 'phone': '+919000000001'}).json()
    client.cookies.clear()
    assert client.post('/api/v1/sessions/join', json=entry).json()['registration_required']
    other = client.post('/api/v1/sessions/join', json={**entry, 'phone': '+919000000002'}).json()
    assert other['participant_id'] != first['participant_id']
    with store() as db:
        assert db.scalar(select(func.count()).select_from(ParticipantProfile)) == 2


def test_resume_requires_saved_attempt_and_name_change_requires_registration(client, monkeypatch):
    live, _, _ = setup_session(client, monkeypatch)
    entry = {'code': live['join_code'], 'name': 'Asha', 'join_by_name': True}
    first = client.post('/api/v1/sessions/join', json={**entry, 'phone': '+919000000001'}).json()
    assert client.post('/api/v1/sessions/join', json=entry).status_code == 409
    resumed = client.post('/api/v1/sessions/join', json=entry, headers={'X-Participant-Token': first['token']})
    assert resumed.json()['participant_id'] == first['participant_id']
    assert client.post('/api/v1/sessions/join', json={**entry, 'name':'Other student'}).json()['registration_required']


def test_invalid_phone_and_forged_cookie_do_not_register(client, monkeypatch, store):
    live, _, _ = setup_session(client, monkeypatch)
    entry = {'code':live['join_code'], 'name':'Asha', 'join_by_name':True}
    assert client.post('/api/v1/sessions/join', json={**entry, 'phone':'abc1234'}).status_code == 422
    client.cookies.set('quizeee_profile', 'forged')
    assert client.post('/api/v1/sessions/join', json=entry).json()['registration_required']
    with store() as db:
        assert db.scalar(select(func.count()).select_from(ParticipantProfile)) == 0
