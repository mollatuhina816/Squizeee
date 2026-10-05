import json
import uuid
from sqlalchemy import select, func
from app.models import LiveSession, ParticipantProfile, Participant
from app.live_routes import notify
from test_builder_live import setup_session, QUESTION

CONTACT = {'name':'Student', 'phone':'+91 90000 00001', 'email':'student@example.com'}


def test_next_opens_and_broadcasts_public_question(client, monkeypatch, store):
    session, _, _ = setup_session(client, monkeypatch)
    sid = session['id']
    with store() as db:
        live = db.get(LiveSession, uuid.UUID(sid))
        live.questions = [QUESTION, {**QUESTION, 'title':'Second question'}]
        db.commit()
    joined = client.post('/api/v1/sessions/join',json={'code':session['join_code'],**CONTACT}).json()
    published=[];cached=[]
    monkeypatch.setattr('app.live_routes.notify',notify)
    monkeypatch.setattr('app.live_routes.cache.publish',lambda channel,data:published.append((channel,json.loads(data))))
    monkeypatch.setattr('app.live_routes.cache.setex',lambda key,ttl,data:cached.append(json.loads(data)))
    url=f'/api/v1/sessions/{sid}'
    assert client.post(url+'/control',json={'action':'open','revision':1}).status_code==200
    first=published[-1][1]['snapshot']
    assert first['question']['title']==QUESTION['title']
    token={'X-Participant-Token':joined['token']}
    response=client.post(url+'/responses',headers=token,json={'question_index':0,'answer':'2'})
    assert response.status_code==201
    second=response.json()['snapshot']
    assert second['state']=='open' and second['active_index']==1
    assert second['question']['title']=='Second question'
    assert second['opened_at']>=first['opened_at']
    wire=json.dumps(published[-1])
    assert 'correct_answers' not in wire and 'explanation' not in wire
    assert CONTACT['email'] not in wire and '90000' not in wire
    assert cached[-1]==published[-1][1]
    assert client.post(url+'/responses',headers=token,json={'question_index':0,'answer':'2'}).status_code==409
    result=client.post(url+'/responses',headers=token,json={'question_index':1,'answer':'2'})
    assert result.status_code==201
    assert result.json()['snapshot']['completed'] is True
    assert client.get(url+'/results',headers=token).status_code==200
    assert published[-1][1]['snapshot']['leaderboard'][0]['score']>=4000



def test_join_requires_contacts_and_resume_token(client, monkeypatch, store):
    session, base, presentation = setup_session(client,monkeypatch)
    payload={'code':session['join_code'],**CONTACT}
    assert client.post('/api/v1/sessions/join',json={'code':session['join_code'],'name':'No contact'}).status_code==422
    result=client.post('/api/v1/sessions/join',json=payload)
    assert result.status_code==201
    token=result.json()['token']
    assert client.post('/api/v1/sessions/join',json=payload).status_code==409
    resumed=client.post('/api/v1/sessions/join',json=payload,headers={'X-Participant-Token':token})
    assert resumed.json()['participant_id']==result.json()['participant_id']
    next_session=client.post(f"{base}/{presentation['id']}/sessions").json()
    next_join=client.post('/api/v1/sessions/join',json={**payload,'code':next_session['join_code']})
    assert next_join.status_code==201
    assert next_join.json()['token']!=token
    with store() as db:
        assert db.scalar(select(func.count()).select_from(ParticipantProfile))==1
        assert db.scalar(select(func.count()).select_from(Participant))==2
    assert client.get(f"/api/v1/sessions/{next_session['id']}/participant",headers={'X-Participant-Token':token}).status_code==401
