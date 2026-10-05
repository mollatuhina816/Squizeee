import uuid
from sqlalchemy import select
from app.models import AuditEvent, Membership, Organization, Presentation, User
from conftest import register


def test_registration_password_cookie_and_revocation(client, store):
    data = register(client)
    assert client.get("/api/v1/auth/me").status_code == 200
    cookie = client.cookies.get("quizeee_access")
    with store() as db:
        user = db.get(User, uuid.UUID(data["id"]))
        assert user.password_hash.startswith("$argon2id$")
        assert not user.is_super_admin
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "organization.created"))
    assert client.post("/api/v1/auth/logout").status_code == 200
    client.cookies.set("quizeee_access", cookie)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_origin_and_overposting(client):
    assert client.post("/api/v1/auth/login", headers={"origin": "https://evil.example"}, json={"email": "a@example.com", "password": "not-a-password"}).status_code == 403
    assert client.post("/api/v1/auth/register", json={"email": "x@example.com", "password": "Strong-password-123", "name": "X", "organization": "X", "is_super_admin": True}).status_code == 422


def test_duplicate_email_and_generic_login_error(client):
    register(client)
    assert client.post("/api/v1/auth/register", json={"email": "OWNER@example.com", "password": "Strong-password-123", "name": "X", "organization": "X"}).status_code == 409
    assert client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": "Strong-password-123"}).status_code == 401


def test_tenant_isolation_and_revision(client):
    first = register(client)
    org = first["organization_id"]
    item = client.post(f"/api/v1/organizations/{org}/presentations", json={"title": "Intro"}).json()
    assert client.patch(f"/api/v1/organizations/{org}/presentations/{item['id']}", json={"title": "New", "revision": 1}).status_code == 200
    assert client.patch(f"/api/v1/organizations/{org}/presentations/{item['id']}", json={"title": "Stale", "revision": 1}).status_code == 409
    register(client, "second@example.com")
    assert client.get(f"/api/v1/organizations/{org}/presentations").status_code == 404
    assert client.patch(f"/api/v1/organizations/{org}/presentations/{item['id']}", json={"title": "Attack", "revision": 2}).status_code == 404


def test_cross_tenant_department_reference_rejected(client):
    first = register(client)
    dept = client.post(f"/api/v1/organizations/{first['organization_id']}/departments", json={"name": "Physics"}).json()
    second = register(client, "second@example.com")
    assert client.post(f"/api/v1/organizations/{second['organization_id']}/presentations", json={"title": "Attack", "department_id": dept["id"]}).status_code == 404


def test_role_revocation_effective_without_new_token(client, store):
    data = register(client)
    org = data["organization_id"]
    with store() as db:
        m = db.scalar(select(Membership).where(Membership.user_id == uuid.UUID(data["id"])))
        m.role = "faculty_lite"
        db.commit()
    assert client.post(f"/api/v1/organizations/{org}/departments", json={"name": "No"}).status_code == 403
    assert client.post(f"/api/v1/organizations/{org}/presentations", json={"title": "No"}).status_code == 403


def test_department_admin_sees_only_assigned_presentations(client, store):
    from app.models import DepartmentAssignment
    data = register(client)
    org = data["organization_id"]
    allowed = client.post(f"/api/v1/organizations/{org}/departments", json={"name": "Physics"}).json()
    denied = client.post(f"/api/v1/organizations/{org}/departments", json={"name": "Chemistry"}).json()
    for dept in [allowed, denied]:
        client.post(f"/api/v1/organizations/{org}/presentations", json={"title": dept["name"], "department_id": dept["id"]})
    with store() as db:
        m = db.scalar(select(Membership).where(Membership.user_id == uuid.UUID(data["id"])))
        m.role = "department_admin"
        db.add(DepartmentAssignment(organization_id=m.organization_id, membership_id=m.id, department_id=uuid.UUID(allowed["id"])))
        db.commit()
    rows = client.get(f"/api/v1/organizations/{org}/presentations").json()
    assert [x["title"] for x in rows] == ["Physics"]
    assert client.get(f"/api/v1/organizations/{org}/members").status_code == 403
    assert client.post(f"/api/v1/organizations/{org}/presentations", json={"title": "No", "department_id": denied["id"]}).status_code == 403


def test_tampered_token_rejected(client):
    register(client)
    client.cookies.clear()
    client.cookies.set("quizeee_access", "forged.invalid.token")
    assert client.get("/api/v1/auth/me").status_code == 401
