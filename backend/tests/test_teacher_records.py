from datetime import datetime, timedelta, timezone
import uuid
from sqlalchemy import select
from app.models import Department, DepartmentAssignment, Membership, Presentation, LiveSession, Participant, ParticipantProfile, Answer, ScheduledQuiz, QuizAssignment
from app.questions import Question
from conftest import register


def test_delete_department_preserves_quiz_and_restricts_scope(client, store):
    account = register(client)
    org = account['organization_id']
    base = f'/api/v1/organizations/{org}'
    department = client.post(base+'/departments', json={'name':'DSA'}).json()
    presentation = client.post(base+'/presentations', json={'title':'Retained quiz','department_id':department['id']}).json()
    with store() as db:
        membership = db.scalar(select(Membership).where(Membership.user_id==uuid.UUID(account['id'])))
        db.add(DepartmentAssignment(organization_id=uuid.UUID(org), membership_id=membership.id, department_id=uuid.UUID(department['id'])))
        db.commit()
    response = client.delete(base+'/departments/'+department['id'])
    assert response.status_code == 200, response.text
    assert client.get(base+'/departments').json() == []
    assert client.get(base+'/presentations').json()[0]['id'] == presentation['id']
    with store() as db:
        item=db.get(Presentation,uuid.UUID(presentation['id']))
        assert item.department_id is None and item.revision==2
        assert list(db.scalars(select(DepartmentAssignment)))==[]
    assert client.delete(base+'/departments/'+department['id']).status_code==404
    foreign = register(client, 'other@example.com')
    assert client.delete(base+'/departments/'+department['id']).status_code==404
    ownbase=f"/api/v1/organizations/{foreign['organization_id']}"
    dept=client.post(ownbase+'/departments',json={'name':'Restricted'}).json()
    with store() as db:
        member=db.scalar(select(Membership).where(Membership.user_id==uuid.UUID(foreign['id'])))
        member.role='faculty';db.commit()
    assert client.delete(ownbase+'/departments/'+dept['id']).status_code==403


def test_teacher_records_include_live_and_assigned_answer_details(client,store):
    account=register(client)
    org=uuid.UUID(account['organization_id']); owner=uuid.UUID(account['id'])
    questions=[Question(kind='mcq',title=f'Question {i}',options=['A','B'],correct_answers=['A'],explanation='A is right.',marks='2').model_dump(mode='json') for i in range(3)]
    now=datetime.now(timezone.utc)
    with store() as db:
        presentation=Presentation(organization_id=org,owner_id=owner,title='Results quiz');db.add(presentation);db.flush()
        session=LiveSession(organization_id=org,owner_id=owner,presentation_id=presentation.id,state='ended',questions=questions);db.add(session);db.flush()
        profile=ParticipantProfile(name='Learner',email='learner@example.com',phone='+919000000001');db.add(profile);db.flush()
        participant=Participant(session_id=session.id,profile_id=profile.id,nickname='Learner',token_hash='test-only');db.add(participant);db.flush()
        db.add_all([Answer(session_id=session.id,participant_id=participant.id,question_index=0,value={'answer':'A'},correct=True,score=2000),Answer(session_id=session.id,participant_id=participant.id,question_index=1,value={'answer':'B'},correct=False,score=0)])
        quiz=ScheduledQuiz(presentation_id=presentation.id,owner_id=owner,title='Assigned results',starts_at=now-timedelta(hours=1),ends_at=now+timedelta(hours=1),questions=questions);db.add(quiz);db.flush()
        db.add_all([QuizAssignment(quiz_id=quiz.id,email='learner@example.com',submitted_at=now,answers=['A','B',None],score=2000),QuizAssignment(quiz_id=quiz.id,email='absent@example.com')]);db.commit()
        sid=str(session.id);qid=str(quiz.id)
    history=client.get(f'/api/v1/organizations/{org}/sessions').json()
    assert {r['record_type'] for r in history}=={'live','assigned'}
    for url in [f'/api/v1/sessions/{sid}/analytics',f'/api/v1/scheduled-quizzes/{qid}/analytics']:
        response=client.get(url);assert response.status_code==200,response.text
        report=response.json();person=next(p for p in report['individuals'] if p['email']=='learner@example.com')
        assert (person['right_count'],person['wrong_count'],person['unanswered_count'])==(1,1,1)
        assert person['score']==2
        assert [q['status'] for q in person['questions']]==['correct','incorrect','unanswered']
        assert person['questions'][1]['answer']=='B' and person['questions'][1]['correct_answers']==['A']
        assert person['questions'][1]['explanation']=='A is right.'
    assigned=client.get(f'/api/v1/scheduled-quizzes/{qid}/analytics').json()
    assert next(p for p in assigned['individuals'] if p['email']=='absent@example.com')['status']=='not started'
    register(client,'outsider@example.com')
    assert client.get(f'/api/v1/sessions/{sid}/analytics').status_code==404
    assert client.get(f'/api/v1/scheduled-quizzes/{qid}/analytics').status_code==404
