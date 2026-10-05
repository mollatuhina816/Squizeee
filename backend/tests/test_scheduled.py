from datetime import datetime, timedelta, timezone
import uuid
from sqlalchemy import select
from app.models import ScheduledQuiz, Slide
from conftest import register


def setup_quiz(client):
    teacher = register(client)
    base = f"/api/v1/organizations/{teacher['organization_id']}/presentations"
    presentation = client.post(base, json={'title':'Scheduled test'}).json()
    endpoint = f"{base}/{presentation['id']}"
    question = {'kind':'mcq','title':'Choose A','options':['A','B'],'correct_answers':['A'],'marks':'2'}
    assert client.put(endpoint+'/slides', json={'revision':1,'questions':[question]}).status_code == 200
    return endpoint, question


def schedule(client, endpoint, **overrides):
    now = datetime.now(timezone.utc)
    data = {'revision':2,'students':['student@example.com'], 'starts_at':(now-timedelta(minutes=1)).isoformat(), 'ends_at':(now+timedelta(hours=1)).isoformat(), **overrides}
    return client.post(endpoint+'/schedule', json=data)


def student(client, email='student@example.com'):
    result = client.post('/api/v1/auth/register',json={'name':'Student','profession':'student','email':email,'password':'Ab1!xy'})
    assert result.status_code == 201, result.text


def test_assignment_snapshot_submission_and_isolation(client, store):
    endpoint, question = setup_quiz(client)
    result = schedule(client, endpoint)
    assert result.status_code == 201, result.text
    quiz_id = result.json()['id']
    question['title'] = 'Edited after scheduling'
    assert client.put(endpoint+'/slides',json={'revision':2,'questions':[question]}).status_code == 200
    student(client)
    assert client.get('/api/v1/student/quizzes').json()[0]['status'] == 'open'
    url = f'/api/v1/student/quizzes/{quiz_id}'
    assert 'questions' not in client.get(url).json()
    assert client.post(url+'/start').status_code == 200
    detail = client.get(url).json()
    assert detail['questions'][0]['title'] == 'Choose A'
    assert 'correct_answers' not in detail['questions'][0]
    assert 'explanation' not in detail['questions'][0]
    assert client.get(url+'/results').status_code == 409
    assert client.post(url+'/submit',json={'answers':[]}).status_code == 422
    assert client.post(url+'/submit',json={'answers':['invalid']}).status_code == 422
    result = client.post(url+'/submit',json={'answers':['A']})
    assert result.status_code == 200
    assert result.json()['score'] == 2000
    assert client.post(url+'/submit',json={'answers':['B']}).status_code == 409
    assert 'questions' not in client.get(url).json()
    student(client,'other@example.com')
    assert client.get(url).status_code == 404
    assert client.get('/api/v1/student/quizzes').json() == []
    assert client.post(endpoint+'/schedule',json={'revision':3,'students':['other@example.com'],'starts_at':datetime.now(timezone.utc).isoformat(),'ends_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}).status_code == 404


def test_submitted_student_can_review_correct_answer_and_marked_mistake(client):
    endpoint, _ = setup_quiz(client)
    scheduled = schedule(client, endpoint)
    quiz_id = scheduled.json()['id']
    student(client)
    url = f'/api/v1/student/quizzes/{quiz_id}'

    assert client.post(url+'/start').status_code == 200
    response = client.post(url+'/submit', json={'answers':['B']})
    assert response.status_code == 200
    assert response.json()['score'] == 0

    review = client.get(url+'/results')
    assert review.status_code == 200
    question = review.json()['questions'][0]
    assert question['answer'] == 'B'
    assert question['correct_answers'] == ['A']
    assert question['correct'] is False
    assert question['status'] == 'incorrect'


def test_schedule_time_window_and_revision(client, store):
    endpoint, _ = setup_quiz(client)
    assert schedule(client,endpoint,revision=1).status_code == 409
    assert schedule(client,endpoint,ends_at=datetime.now(timezone.utc).isoformat(),starts_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()).status_code == 422
    result = schedule(client,endpoint,starts_at=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat())
    quiz_id = result.json()['id']
    student(client)
    url=f'/api/v1/student/quizzes/{quiz_id}'
    assert client.get(url).json()['status']=='upcoming'
    assert 'questions' not in client.get(url).json()
    assert client.post(url+'/submit',json={'answers':['A']}).status_code==409
    with store() as db:
        quiz=db.get(ScheduledQuiz,uuid.UUID(quiz_id))
        quiz.starts_at=datetime.now(timezone.utc)-timedelta(hours=2)
        quiz.ends_at=datetime.now(timezone.utc)-timedelta(hours=1)
        db.commit()
    assert client.get(url).json()['status']=='closed'
    assert client.post(url+'/submit',json={'answers':['A']}).status_code==409


def test_six_character_password_login(client):
    student(client)
    client.post('/api/v1/auth/logout')
    assert client.post('/api/v1/auth/login',json={'email':'student@example.com','password':'Ab1!xy'}).status_code==200
    assert client.post('/api/v1/auth/register',json={'name':'Short','profession':'student','email':'short@example.com','password':'Ab1!x'}).status_code==422
