"""Organization administration: explicit role ceilings and immutable tenant scope."""
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from .db import database
from .models import AuditEvent, Department, DepartmentAssignment, Membership, Organization, User
from .permissions import FACULTY
from .security import identity, origin_check

router = APIRouter(prefix="/api/v1/organizations", tags=["organization administration"])


class RoleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["admin", "department_admin", "faculty", "faculty_lite"]
    department_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class OrgSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    faculty_lite_permissions: list[str] = Field(max_length=20)


def member_for(db, user, org_id):
    item = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.organization_id == org_id))
    if not item:
        raise HTTPException(404, "Organization not found")
    return item


def event(db, user, org_id, action, resource):
    db.add(AuditEvent(actor_id=user.id, organization_id=org_id, action=action, resource_id=str(resource)))


@router.get("/{org_id}/settings")
def get_settings(org_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    member = member_for(db, user, org_id)
    if member.role not in {"owner", "admin"}:
        raise HTTPException(403, "Permission denied")
    org = db.get(Organization, org_id)
    return {"name": org.name, "faculty_lite_permissions": org.faculty_lite_permissions}


@router.patch("/{org_id}/settings", dependencies=[Depends(origin_check)])
def update_settings(org_id: uuid.UUID, data: OrgSettings, user: User = Depends(identity), db: Session = Depends(database)):
    member = member_for(db, user, org_id)
    if member.role != "owner":
        raise HTTPException(403, "Only the owner can change organization permissions")
    if not set(data.faculty_lite_permissions).issubset(FACULTY):
        raise HTTPException(422, "Faculty Lite permissions must be a subset of faculty permissions")
    org = db.get(Organization, org_id)
    org.name = data.name
    org.faculty_lite_permissions = sorted(set(data.faculty_lite_permissions))
    event(db, user, org_id, "organization.settings_changed", org.id)
    db.commit()
    return {"name": org.name, "faculty_lite_permissions": org.faculty_lite_permissions}


@router.patch("/{org_id}/members/{membership_id}", dependencies=[Depends(origin_check)])
def change_role(org_id: uuid.UUID, membership_id: uuid.UUID, data: RoleChange,
                user: User = Depends(identity), db: Session = Depends(database)):
    # Serialize organization role mutations before resolving current privileges.
    org = db.scalar(select(Organization).where(Organization.id == org_id).with_for_update())
    actor = member_for(db, user, org_id)
    target = db.scalar(select(Membership).where(Membership.id == membership_id, Membership.organization_id == org_id))
    if not target:
        raise HTTPException(404, "Member not found")
    if target.role == "owner" or target.user_id == user.id:
        raise HTTPException(403, "Owner or self role changes require a separate ownership workflow")
    if actor.role not in {"owner", "admin", "department_admin"}:
        raise HTTPException(403, "Permission denied")
    if actor.role == "admin" and (target.role == "admin" or data.role == "admin"):
        raise HTTPException(403, "Only the owner can manage organization admins")
    requested = set(data.department_ids)
    found = set(db.scalars(select(Department.id).where(Department.organization_id == org_id, Department.id.in_(requested))))
    if found != requested:
        raise HTTPException(422, "Unknown department")
    if data.role == "department_admin" and not requested:
        raise HTTPException(422, "A department admin requires at least one assigned department")
    if actor.role == "department_admin":
        allowed = set(db.scalars(select(DepartmentAssignment.department_id).where(DepartmentAssignment.membership_id == actor.id)))
        existing = set(db.scalars(select(DepartmentAssignment.department_id).where(DepartmentAssignment.membership_id == target.id)))
        if target.role not in {"faculty", "faculty_lite"} or data.role not in {"faculty", "faculty_lite"}:
            raise HTTPException(403, "Department admins can manage faculty roles only")
        if not existing or not existing.issubset(allowed) or not requested or not requested.issubset(allowed):
            raise HTTPException(403, "Member is outside your department scope")
    target.role = data.role
    db.execute(delete(DepartmentAssignment).where(DepartmentAssignment.membership_id == target.id))
    for department_id in requested:
        db.add(DepartmentAssignment(organization_id=org_id, membership_id=target.id, department_id=department_id))
    event(db, user, org_id, "membership.role_changed", target.id)
    db.commit()
    return {"id": target.id, "role": target.role, "department_ids": sorted(str(x) for x in requested)}


@router.get("/{org_id}/departments/{department_id}/members")
def department_members(org_id: uuid.UUID, department_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    actor = member_for(db, user, org_id)
    dept = db.scalar(select(Department).where(Department.id == department_id, Department.organization_id == org_id))
    if not dept:
        raise HTTPException(404, "Department not found")
    if actor.role not in {"owner", "admin"}:
        assignment = db.get(DepartmentAssignment, (org_id, actor.id, department_id))
        if actor.role != "department_admin" or not assignment:
            raise HTTPException(403, "Permission denied")
    rows = db.execute(select(User, Membership).join(Membership, Membership.user_id == User.id)
                      .join(DepartmentAssignment, DepartmentAssignment.membership_id == Membership.id)
                      .where(Membership.organization_id == org_id, DepartmentAssignment.department_id == department_id).limit(100))
    return [{"id": m.id, "name": u.name, "email": u.email, "role": m.role} for u, m in rows]


@router.get("/{org_id}/audit")
def audit_log(org_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    actor = member_for(db, user, org_id)
    if actor.role not in {"owner", "admin"}:
        raise HTTPException(403, "Permission denied")
    rows = db.scalars(select(AuditEvent).where(AuditEvent.organization_id == org_id).order_by(AuditEvent.created_at.desc()).limit(100))
    return [{"id": e.id, "actor_id": e.actor_id, "action": e.action, "resource_id": e.resource_id, "created_at": e.created_at} for e in rows]
