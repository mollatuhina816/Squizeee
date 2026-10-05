import uuid

import pytest

from app.bootstrap_super_admin import create_first_super_admin, promote_first_super_admin
from app.models import Answer, AuditEvent, LiveSession, Participant, ParticipantProfile, Presentation, User
from conftest import register


def test_admin_directories_require_super_admin(client):
    assert client.get('/api/v1/admin/summary').status_code == 401
    register(client)
    assert client.get('/api/v1/admin/summary').status_code == 403
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.get("/api/v1/admin/participants").status_code == 403


def test_create_first_super_admin_hashes_password_and_audits(store):
    with store() as db:
        user = create_first_super_admin(db, " Tuhina ", "ADMIN@example.com", "Strong-Admin-123!")
        user_id = user.id
        assert user.name == "Tuhina"
        assert user.email == "admin@example.com"
        assert user.is_super_admin
        assert user.password_hash != "Strong-Admin-123!"
        db.commit()
    with store() as db:
        assert db.get(User, user_id).password_hash.startswith("$argon2id$")
        assert db.query(AuditEvent).filter_by(action="super_admin.bootstrapped").count() == 1
        with pytest.raises(ValueError, match="already configured"):
            create_first_super_admin(db, "Other Admin", "other@example.com", "Strong-Admin-123!")


@pytest.mark.parametrize("password", ["abc123", "StrongPassword!", "STRONG-123!"])
def test_create_first_super_admin_rejects_weak_password(store, password):
    with store() as db:
        with pytest.raises(ValueError, match="Password must"):
            create_first_super_admin(db, "Tuhina", "admin@example.com", password)


def test_super_admin_can_view_accounts_and_live_participant_details(client, store):
    account = register(client)
    admin_cookie = client.cookies.get("quizeee_access")
    student_response = client.post("/api/v1/auth/register", json={
        "email": "student-account@example.com",
        "password": "Strong-password-123",
        "name": "Student Account",
        "profession": "student",
    })
    assert student_response.status_code == 201, student_response.text
    student_cookie = client.cookies.get("quizeee_access")

    with store() as db:
        admin = db.get(User, uuid.UUID(account["id"]))
        admin_email = promote_first_super_admin(db, admin.email)
        presentation = Presentation(
            organization_id=uuid.UUID(account["organization_id"]),
            owner_id=admin.id,
            title="Admin visibility test",
        )
        db.add(presentation)
        db.flush()
        session = LiveSession(
            organization_id=presentation.organization_id,
            presentation_id=presentation.id,
            owner_id=admin.id,
            join_code="123456",
            questions=[{"kind": "content", "title": "Welcome", "options": []}],
        )
        profile = ParticipantProfile(name="Joined Student", email="joined@example.com", phone="+12025550123")
        db.add_all([session, profile])
        db.flush()
        participant = Participant(
            session_id=session.id,
            profile_id=profile.id,
            nickname="Joined Student",
            token_hash="f" * 64,
        )
        db.add(participant)
        db.flush()
        db.add(Answer(
            session_id=session.id,
            participant_id=participant.id,
            question_index=0,
            value={"answer": "Welcome"},
            correct=True,
            score=1250,
            elapsed_ms=900,
        ))
        db.commit()

    client.cookies.set("quizeee_access", admin_cookie)
    assert client.get("/api/v1/auth/me").json()["is_super_admin"] is True
    accounts = client.get("/api/v1/admin/users?limit=1&offset=0").json()
    assert accounts["total"] == 2
    assert len(accounts["items"]) == 1
    assert "password_hash" not in accounts["items"][0]
    searched_accounts = client.get("/api/v1/admin/users?q=student-account@example.com").json()
    assert [row["email"] for row in searched_accounts["items"]] == ["student-account@example.com"]
    assert admin_email == "owner@example.com"
    assert client.get('/api/v1/admin/summary').json()['students'] == 1
    assert client.get('/api/v1/admin/summary').json()['teachers'] == 1
    filtered = client.get('/api/v1/admin/users?profession=student').json()
    assert filtered['total'] == 1
    assert filtered['items'][0]['email'] == 'student-account@example.com'
    assert client.get('/api/v1/admin/users?profession=admin').status_code == 422

    participants = client.get("/api/v1/admin/participants?q=joined@example.com").json()
    assert participants["total"] == 1
    assert participants["items"][0]["email"] == "joined@example.com"
    assert participants["items"][0]["phone"] == "+12025550123"
    assert participants["items"][0]["score"] == 1250
    assert "token_hash" not in participants["items"][0]

    client.cookies.set("quizeee_access", student_cookie)
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.get("/api/v1/admin/participants").status_code == 403

    with store() as db:
        assert db.query(AuditEvent).filter_by(action="super_admin.bootstrapped").count() == 1
        with pytest.raises(ValueError, match="already configured"):
            promote_first_super_admin(db, "student-account@example.com")
