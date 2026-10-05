from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import func, select

from app.models import AchievementSettings, ParticipantProfile, QuizAssignment, ScheduledQuiz, User
from app.student_routes import history_row, maximum_score
from test_builder_live import setup_session
from test_scheduled import schedule, setup_quiz, student


def test_profile_created_on_first_attempt_and_points_accumulate_once(client, store):
    endpoint, question = setup_quiz(client)
    question['marks'] = '1'
    assert client.put(endpoint+'/slides', json={'revision':2, 'questions':[question]*10}).status_code == 200
    ids = [schedule(client, endpoint, revision=3).json()['id'] for _ in range(3)]
    student(client)
    with store() as db:
        assert db.scalar(select(func.count()).select_from(ParticipantProfile)) == 0
    for quiz_id, count in zip(ids, (8, 7, 9)):
        url = f'/api/v1/student/quizzes/{quiz_id}'
        assert client.post(url+'/start').status_code == 200
        assert client.post(url+'/submit', json={'answers':['A']*count+['B']*(10-count)}).status_code == 200
        assert client.post(url+'/submit', json={'answers':['A']*10}).status_code == 409
    for _ in range(2):
        response = client.get('/api/v1/student/profile')
        assert response.status_code == 200, response.text
        profile = response.json()
        assert profile['email'] == 'student@example.com'
        assert profile['total_attempted'] == profile['completed_quizzes'] == 3
        assert profile['total_points'] == 240
        assert profile['average_score'] == 80
        assert profile['highest_score'] == 90
        assert profile['lowest_score'] == 70
        assert sorted(row['points'] for row in profile['history']) == [70, 80, 90]
        assert profile['next_achievement'] == {'name':'Gold','threshold':10,'remaining':7}
    with store() as db:
        assert db.scalar(select(func.count()).select_from(ParticipantProfile)) == 1
    student(client, 'another@example.com')
    assert client.get('/api/v1/student/profile').json()['history'] == []


def test_in_progress_and_expired_attempt_reconciled(client, store):
    endpoint, _ = setup_quiz(client)
    quiz_id = schedule(client, endpoint).json()['id']
    student(client)
    url = f'/api/v1/student/quizzes/{quiz_id}'
    assert client.post(url+'/start').status_code == 200
    profile = client.get('/api/v1/student/profile').json()
    assert profile['total_attempted'] == 1
    assert profile['completed_quizzes'] == profile['total_points'] == 0
    assert profile['average_score'] is None
    assert client.put(url+'/draft', json={'answers':['A']}).status_code == 200
    with store() as db:
        assignment = db.scalar(select(QuizAssignment).where(QuizAssignment.quiz_id == uuid.UUID(quiz_id)))
        assignment.deadline_at = datetime.now(timezone.utc)-timedelta(seconds=1)
        db.commit()
    for _ in range(2):
        profile = client.get('/api/v1/student/profile').json()
        assert profile['completed_quizzes'] == 1
        assert profile['total_points'] == 100
        assert profile['history'][0]['status'] == 'Completed'


def test_guest_dashboard_and_email_only_join_cannot_disclose_history(client, monkeypatch):
    live, base, presentation = setup_session(client, monkeypatch)
    joined = client.post('/api/v1/sessions/join', json={'code':live['join_code'],
        'email':'guest@example.com','name':'Guest Student','phone':'+919000000001'})
    assert 'HttpOnly' in joined.headers['set-cookie']
    assert client.get('/api/v1/student/profile').json()['email'] == 'guest@example.com'
    assert client.post(f"/api/v1/sessions/{live['id']}/control", json={'action':'open','revision':1}).status_code == 200
    headers = {'X-Participant-Token':joined.json()['token']}
    assert client.post(f"/api/v1/sessions/{live['id']}/responses", headers=headers,
                       json={'question_index':0,'answer':'2'}).status_code == 201
    profile = client.get('/api/v1/student/profile').json()
    assert profile['completed_quizzes'] == 1
    assert profile['history'][0]['total_marks'] == 3  # Includes maximum speed bonus.
    assert 66 <= profile['total_points'] <= 100
    second = client.post(f"{base}/{presentation['id']}/sessions").json()
    client.cookies.delete('quizeee_profile')
    assert client.get('/api/v1/student/profile').status_code == 401
    joined = client.post('/api/v1/sessions/join', json={'code':second['join_code'],'email':'guest@example.com'})
    assert joined.status_code == 201
    assert 'set-cookie' not in joined.headers
    assert client.get('/api/v1/student/profile').status_code == 401


def test_registered_live_student_reuses_profile_and_needs_login(client, monkeypatch, store):
    live, _, _ = setup_session(client, monkeypatch)
    student(client)
    client.get('/api/v1/student/profile')
    joined = client.post('/api/v1/sessions/join', json={'code':live['join_code'],'email':'STUDENT@example.com'})
    assert joined.status_code == 201
    assert 'set-cookie' not in joined.headers
    assert client.get('/api/v1/student/profile').json()['total_attempted'] == 1
    with store() as db:
        assert db.scalar(select(func.count()).select_from(ParticipantProfile)) == 1
    client.cookies.clear()
    assert client.get('/api/v1/student/profile').status_code == 401


def test_guest_profile_falls_back_when_access_cookie_is_invalid(client, monkeypatch):
    live, _, _ = setup_session(client, monkeypatch)
    joined = client.post('/api/v1/sessions/join', json={'code': live['join_code'],
        'email': 'stale-cookie@example.com', 'name': 'Guest Student', 'phone': '+919000000002'})
    assert joined.status_code == 201
    client.cookies.set('quizeee_access', 'not-a-valid-token')
    profile = client.get('/api/v1/student/profile').json()
    assert profile['email'] == 'stale-cookie@example.com'
    assert profile['account'] is False


def test_configurable_badges_permissions_validation_and_boundaries(client, store):
    endpoint, _ = setup_quiz(client)
    quiz_id = schedule(client, endpoint).json()['id']
    url = '/api/v1/admin/achievement-settings'
    assert client.put(url, json={'gold':1,'platinum':2,'diamond':3}).status_code == 403
    with store() as db:
        owner = db.scalar(select(User).where(User.email=='owner@example.com'))
        owner.is_super_admin = True
        db.commit()
    assert client.get(url).json() == {'gold':10,'platinum':50,'diamond':100}
    assert client.put(url, json={'gold':2,'platinum':2,'diamond':3}).status_code == 422
    assert client.put(url, json={'gold':0,'platinum':2,'diamond':3}).status_code == 422
    assert client.put(url, json={'gold':1,'platinum':2,'diamond':3}, headers={'origin':'https://evil.example'}).status_code == 403
    assert client.put(url, json={'gold':1,'platinum':2,'diamond':3}).status_code == 200
    student(client)
    assert client.put(url, json={'gold':1,'platinum':2,'diamond':3}).status_code == 403
    base = f'/api/v1/student/quizzes/{quiz_id}'
    client.post(base+'/start')
    client.post(base+'/submit', json={'answers':['A']})
    for count, expected in [(1,'Gold'),(2,'Platinum'),(3,'Diamond')]:
        if count > 1:
            with store() as db:
                original = db.get(ScheduledQuiz, uuid.UUID(quiz_id))
                quiz = ScheduledQuiz(presentation_id=original.presentation_id, owner_id=original.owner_id,
                    title='Another quiz', starts_at=original.starts_at, ends_at=original.ends_at, questions=original.questions)
                db.add(quiz);db.flush()
                db.add(QuizAssignment(quiz_id=quiz.id,email='student@example.com',
                    started_at=datetime.now(timezone.utc), submitted_at=datetime.now(timezone.utc), answers=['A'],score=2000))
                db.commit()
        profile = client.get('/api/v1/student/profile').json()
        assert profile['achievement'] == expected
        assert profile['total_points'] == count*100
        if count == 3:
            assert profile['next_achievement'] is None
        else:
            assert profile['next_achievement']['remaining'] == 1
    with store() as db:
        row = db.get(AchievementSettings, 1)
        row.gold, row.platinum, row.diamond = 10, 50, 100
        db.commit()
    profile = client.get('/api/v1/student/profile').json()
    assert profile['achievement'] is None
    assert profile['total_points'] == 300


def test_points_negative_ungraded_and_fractional_marks():
    date = datetime.now(timezone.utc)
    assert history_row('live',uuid.uuid4(),'Quiz',date,-500,2000,True)['points'] == 0
    assert history_row('live',uuid.uuid4(),'Quiz',date,1005,2000,True)['points'] == 50
    assert history_row('live',uuid.uuid4(),'Quiz',date,1010,2000,True)['points'] == 51
    assert history_row('live',uuid.uuid4(),'Poll',date,0,0,True)['percentage'] is None
    assert maximum_score([{'kind':'poll','title':'Poll','options':['A','B'],'marks':'10'}]) == 0
