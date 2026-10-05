from sqlalchemy import select, func
from app.models import ParticipantProfile, Participant, AuthSession
from test_builder_live import setup_session


def test_email_registration_reused_across_quizzes(client, monkeypatch, store):
    session, base, presentation = setup_session(client, monkeypatch)
    entry = {'quiz_id': session['join_code'], 'email': 'New.Student@example.com'}
    with store() as db:
        login_count = db.scalar(select(func.count()).select_from(AuthSession))
    response = client.post('/api/v1/sessions/join', json=entry)
    assert response.json()['registration_required'] is True
    with store() as db:
        assert db.scalar(select(func.count()).select_from(ParticipantProfile)) == 0
    first = client.post('/api/v1/sessions/join', json={**entry, 'name': 'Student', 'phone': '+919000000001'})
    assert first.status_code == 201
    second = client.post(f"{base}/{presentation['id']}/sessions").json()
    joined = client.post('/api/v1/sessions/join', json={'quiz_id': second['id'], 'email': 'new.student@example.com'})
    assert joined.status_code == 201 and joined.json()['participant_id'] != first.json()['participant_id']
    # Resume requires the session credential; entering is not a new login.
    resumed = client.post('/api/v1/sessions/join', json={'quiz_id': second['id'], 'email': 'new.student@example.com'}, headers={'X-Participant-Token': joined.json()['token']})
    assert resumed.json()['participant_id'] == joined.json()['participant_id']
    with store() as db:
        assert db.scalar(select(func.count()).select_from(ParticipantProfile)) == 1
        assert db.scalar(select(func.count()).select_from(Participant)) == 2
        assert db.scalar(select(func.count()).select_from(AuthSession)) == login_count


def test_bad_quiz_does_not_register_student(client, monkeypatch, store):
    setup_session(client, monkeypatch)
    result = client.post('/api/v1/sessions/join', json={'quiz_id': 'invalid', 'email': 'new@example.com', 'name': 'New', 'phone': '+919000000001'})
    assert result.status_code == 422
    with store() as db:
        assert db.scalar(select(func.count()).select_from(ParticipantProfile)) == 0


def test_existing_student_account_can_join_with_email(client, monkeypatch):
    session, _, _ = setup_session(client, monkeypatch)
    from test_scheduled import student
    student(client)
    response = client.post('/api/v1/sessions/join', json={'quiz_id': session['join_code'], 'email': 'student@example.com'})
    assert response.status_code == 201 and 'token' in response.json()
