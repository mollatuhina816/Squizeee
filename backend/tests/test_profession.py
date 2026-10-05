import uuid
from sqlalchemy import select
from app.models import Membership, User
from conftest import register


def test_student_registration_login_and_permissions(client, store):
    teacher = register(client)
    result = client.post('/api/v1/auth/register', json={
        'email': 'student@example.com', 'password': 'Strong-password-123',
        'name': 'Student', 'profession': 'student'})
    assert result.status_code == 201, result.text
    assert result.json()['organization_id'] is None
    assert client.get('/api/v1/auth/me').json()['profession'] == 'student'
    assert client.get('/api/v1/organizations').json() == []
    assert client.post(f"/api/v1/organizations/{teacher['organization_id']}/presentations", json={'title':'Forbidden'}).status_code == 404
    with store() as db:
        uid = uuid.UUID(result.json()['id'])
        assert db.get(User, uid).profession == 'student'
        assert db.scalar(select(Membership).where(Membership.user_id == uid)) is None
    assert client.post('/api/v1/auth/logout').status_code == 200
    result = client.post('/api/v1/auth/login', json={'email':'student@example.com','password':'Strong-password-123'})
    assert result.status_code == 200
    assert result.json()['profession'] == 'student'


def test_teacher_registration_and_validation(client):
    assert register(client)['profession'] == 'teacher'
    assert client.get('/api/v1/organizations').json()[0]['role'] == 'owner'
    payload = {'email':'new@example.com','password':'Strong-password-123','name':'New'}
    assert client.post('/api/v1/auth/register', json={**payload,'profession':'teacher'}).status_code == 422
    assert client.post('/api/v1/auth/register', json={**payload,'profession':'admin','organization':'School'}).status_code == 422
