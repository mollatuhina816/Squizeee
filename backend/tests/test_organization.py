import uuid
from sqlalchemy import select
from app.models import DepartmentAssignment, Membership, User
from app.security import passwords
from conftest import register


def add_member(store, org, role="faculty", departments=()):
    with store() as db:
        user = User(name="Faculty", email=f"{uuid.uuid4()}@example.com", password_hash=passwords.hash("Strong-password-123"))
        db.add(user); db.flush()
        membership = Membership(organization_id=uuid.UUID(org), user_id=user.id, role=role)
        db.add(membership); db.flush()
        for dep in departments:
            db.add(DepartmentAssignment(organization_id=uuid.UUID(org), membership_id=membership.id, department_id=uuid.UUID(dep)))
        db.commit()
        return str(membership.id)


def test_owner_updates_lite_policy_and_rejects_admin_grants(client):
    org = register(client)["organization_id"]
    path = f"/api/v1/organizations/{org}/settings"
    assert client.patch(path, json={"name": "New name", "faculty_lite_permissions": ["presentation.read", "presentation.write"]}).status_code == 200
    assert client.patch(path, json={"name": "New name", "faculty_lite_permissions": ["billing.manage"]}).status_code == 422


def test_owner_can_assign_admin_but_cannot_demote_self(client, store):
    data = register(client); org = data["organization_id"]
    target = add_member(store, org)
    assert client.patch(f"/api/v1/organizations/{org}/members/{target}", json={"role": "admin"}).status_code == 200
    with store() as db:
        own = db.scalar(select(Membership).where(Membership.user_id == uuid.UUID(data["id"])))
        own_id = own.id
    assert client.patch(f"/api/v1/organizations/{org}/members/{own_id}", json={"role": "faculty"}).status_code == 403


def test_department_admin_cannot_manage_multi_department_faculty(client, store):
    data = register(client); org = data["organization_id"]
    a = client.post(f"/api/v1/organizations/{org}/departments", json={"name": "A"}).json()["id"]
    b = client.post(f"/api/v1/organizations/{org}/departments", json={"name": "B"}).json()["id"]
    target = add_member(store, org, departments=[a, b])
    with store() as db:
        own = db.scalar(select(Membership).where(Membership.user_id == uuid.UUID(data["id"])))
        own.role = "department_admin"
        db.add(DepartmentAssignment(organization_id=own.organization_id, membership_id=own.id, department_id=uuid.UUID(a)))
        db.commit()
    assert client.patch(f"/api/v1/organizations/{org}/members/{target}", json={"role": "faculty_lite", "department_ids": [a]}).status_code == 403
    assert client.get(f"/api/v1/organizations/{org}/departments/{b}/members").status_code == 403


def test_admin_cannot_promote_to_admin(client, store):
    data = register(client); org = data["organization_id"]
    target = add_member(store, org)
    with store() as db:
        own = db.scalar(select(Membership).where(Membership.user_id == uuid.UUID(data["id"])))
        own.role = "admin"; db.commit()
    assert client.patch(f"/api/v1/organizations/{org}/members/{target}", json={"role": "admin"}).status_code == 403


def test_cross_tenant_membership_update_returns_not_found(client, store):
    a = register(client)["organization_id"]
    member = add_member(store, a)
    b = register(client, "other@example.com")["organization_id"]
    assert client.patch(f"/api/v1/organizations/{b}/members/{member}", json={"role": "faculty_lite"}).status_code == 404
