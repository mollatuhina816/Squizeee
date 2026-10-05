from test_scheduled import setup_quiz, schedule, student
from test_builder_live import setup_session
from test_live_broadcast import CONTACT


def test_scheduled_private_results_after_submission(client):
    endpoint,_=setup_quiz(client)
    quiz=schedule(client,endpoint).json()
    student(client)
    url=f"/api/v1/student/quizzes/{quiz['id']}"
    assert client.get(url+'/results').status_code==409
    assert 'correct_answers' not in client.get(url).text
    assert client.post(url+'/start').status_code==200
    assert client.post(url+'/submit',json={'answers':['B']}).status_code==200
    result=client.get(url+'/results').json()
    assert result['questions'][0]['answer']=='B'
    assert result['questions'][0]['correct_answers']==['A']
    assert result['questions'][0]['status']=='incorrect'
    assert result['score']==0
    student(client,'other@example.com')
    assert client.get(url+'/results').status_code==404


def test_live_results_only_after_end_and_for_current_participant(client,monkeypatch):
    session,_,_=setup_session(client,monkeypatch)
    sid=session['id'];base=f'/api/v1/sessions/{sid}'
    joined=client.post('/api/v1/sessions/join',json={'code':session['join_code'],**CONTACT}).json()
    headers={'X-Participant-Token':joined['token']}
    assert client.get(base+'/results',headers=headers).status_code==409
    assert client.post(base+'/control',json={'action':'open','revision':1}).status_code==200
    assert client.post(base+'/responses',headers=headers,json={'question_index':0,'answer':'4'}).status_code==201
    assert client.get(base+'/results',headers=headers).status_code==200
    assert client.post(base+'/control',json={'action':'end','revision':2}).status_code==200
    result=client.get(base+'/results',headers=headers).json()
    assert result['questions'][0]['correct_answers']==['2']
    assert result['questions'][0]['answer']=='4'
    assert result['questions'][0]['status']=='incorrect'
    assert result['score']==-500
    assert client.get(base+'/results').status_code==401
