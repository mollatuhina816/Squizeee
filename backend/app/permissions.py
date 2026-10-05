"""Pure policy: role capabilities AND resource scope are both required."""
from dataclasses import dataclass
from uuid import UUID

FACULTY = frozenset({"presentation.read", "presentation.write", "session.control", "analytics.read", "bank.write"})
ROLE_PERMISSIONS = {
    "owner": FACULTY | {"organization.manage", "billing.manage", "members.manage", "departments.manage", "audit.read"},
    "admin": FACULTY | {"organization.manage", "members.manage", "departments.manage", "audit.read"},
    "department_admin": FACULTY | {"members.manage"},
    "faculty": FACULTY,
    "faculty_lite": frozenset(),
}


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    organization_id: UUID
    role: str
    departments: frozenset[UUID] = frozenset()
    lite_permissions: frozenset[str] = frozenset()


def permits(principal: Principal, permission: str, *, organization_id: UUID,
            owner_id: UUID | None = None, department_id: UUID | None = None) -> bool:
    if organization_id != principal.organization_id:
        return False
    grants = (principal.lite_permissions & FACULTY) if principal.role == "faculty_lite" else ROLE_PERMISSIONS.get(principal.role, frozenset())
    if permission not in grants:
        return False
    if principal.role in {"owner", "admin"}:
        return True
    if principal.role == "department_admin":
        return department_id is not None and department_id in principal.departments
    return owner_id == principal.user_id
