from uuid import uuid4
import pytest
from app.permissions import Principal, permits


@pytest.mark.parametrize("role", ["owner", "admin", "department_admin", "faculty", "faculty_lite", "co_presenter", "unknown"])
def test_every_role_denied_cross_tenant(role):
    user, org, other = uuid4(), uuid4(), uuid4()
    assert not permits(Principal(user, org, role), "presentation.write", organization_id=other, owner_id=user)


def test_department_admin_is_not_org_admin():
    user, org, assigned, other = [uuid4() for _ in range(4)]
    p = Principal(user, org, "department_admin", frozenset([assigned]))
    assert permits(p, "presentation.write", organization_id=org, department_id=assigned)
    assert not permits(p, "presentation.write", organization_id=org, department_id=other)
    assert not permits(p, "members.manage", organization_id=org)
    assert not permits(p, "billing.manage", organization_id=org, department_id=assigned)


def test_faculty_only_owns_own_resources():
    user, org = uuid4(), uuid4()
    p = Principal(user, org, "faculty")
    assert permits(p, "presentation.write", organization_id=org, owner_id=user)
    assert not permits(p, "presentation.write", organization_id=org, owner_id=uuid4())


def test_lite_configuration_cannot_grant_admin():
    user, org = uuid4(), uuid4()
    p = Principal(user, org, "faculty_lite", lite_permissions=frozenset(["presentation.write", "billing.manage"]))
    assert permits(p, "presentation.write", organization_id=org, owner_id=user)
    assert not permits(p, "billing.manage", organization_id=org, owner_id=user)
