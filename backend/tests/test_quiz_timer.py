from datetime import datetime, timedelta, timezone
import uuid
from sqlalchemy import select
from app.models import QuizAssignment, ScheduledQuiz
from app.scheduled_routes import expire_due_attempts
from test_scheduled import setup_quiz, schedule, student


def timed_quiz(client, duration=10, **schedule_options):
    endpoint, question = setup_quiz(client)
    response = client.put(endpoint+'/slides', json={'revision':2,'questions':[question,question], 'duration_minutes':duration})
    assert response.status_code == 200
    assert client.get(endpoint+'/slides').json()['duration_minutes'] == duration
    response = schedule(client, endpoint, revision=3, **schedule_options)
    assert response.status_code == 201
    student(client)
    return '/api/v1/student/quizzes/'+response.json()['id']


def test_server_start_is_persistent_and_idempotent(client):
    url = timed_quiz(client)
    initial=client.get(url).json()
    assert initial['started_at'] is None and 'questions' not in initial
    assert client.put(url+'/draft', json={'answers':['A',None]}).status_code == 409
    started=client.post(url+'/start').json()
    assert (datetime.fromisoformat(started['deadline_at'])-datetime.fromisoformat(started['started_at'])).total_seconds()==600
    assert client.post(url+'/start').json()['deadline_at']==started['deadline_at']
    assert client.get(url).json()['deadline_at']==started['deadline_at']
    assert client.put(url+'/draft', json={'answers':['A',None]}).status_code == 200
    assert client.get(url).json()['answers']==['A',None]


def test_expiry_scores_saved_answers_ignores_late_changes(client, store):
    url=timed_quiz(client)
    client.post(url+'/start')
    client.put(url+'/draft',json={'answers':['A',None]})
    with store() as db:
        a=db.scalar(select(QuizAssignment))
        a.deadline_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    response=client.post(url+'/submit',json={'answers':['B','A']})
    assert response.status_code==200
    assert response.json()['status']=='submitted' and response.json()['score']==2000
    assert client.put(url+'/draft',json={'answers':['B','A']}).json()['score']==2000
    assert client.post(url+'/start').json()['status']=='submitted'
    review=client.get(url+'/results').json()['questions']
    assert review[0]['answer']=='A' and review[1]['status']=='unanswered'


def test_background_expiry_without_student_request(client,store):
    url=timed_quiz(client)
    client.post(url+'/start')
    with store() as db:
        a=db.scalar(select(QuizAssignment));a.deadline_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
        expire_due_attempts(db)
        assert a.submitted_at is not None and a.score==0 and a.answers==[None,None]


def test_deadline_capped_by_quiz_close(client):
    end=datetime.now(timezone.utc)+timedelta(minutes=2)
    url=timed_quiz(client,ends_at=end.isoformat())
    assert datetime.fromisoformat(client.post(url+'/start').json()['deadline_at'])==end


def test_duration_validation_and_publish_snapshot(client,store):
    endpoint,question=setup_quiz(client)
    assert client.put(endpoint+'/slides',json={'revision':2,'questions':[question],'duration_minutes':11}).status_code==422
    assert client.put(endpoint+'/slides',json={'revision':2,'questions':[question],'duration_minutes':90}).status_code==200
    q=schedule(client,endpoint,revision=3).json()
    assert client.put(endpoint+'/slides',json={'revision':3,'questions':[question],'duration_minutes':10}).status_code==200
    with store() as db:
        assert db.get(ScheduledQuiz,uuid.UUID(q['id'])).duration_minutes==90


def test_partial_manual_submission(client):
    url=timed_quiz(client)
    client.post(url+'/start')
    assert client.post(url+'/submit',json={'answers':[None,'A']}).json()['score']==2000


def test_timer_actions_are_assignment_scoped(client):
    url=timed_quiz(client)
    student(client,'unassigned@example.com')
    assert client.post(url+'/start').status_code==404
    assert client.put(url+'/draft',json={'answers':[None,None]}).status_code==404
