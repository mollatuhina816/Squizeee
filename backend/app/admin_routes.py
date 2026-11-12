import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .db import database
from .models import Answer, AuthSession, LiveSession, Membership, Participant, ParticipantProfile, Presentation, User, Organization
from .security import identity

router = APIRouter(prefix="/api/v1/admin", tags=["super admin"])


def require_super_admin(user: User = Depends(identity)) -> User:
    if not user.is_super_admin:
        raise HTTPException(403, "Super admin access required")
    return user


def search_term(value: str) -> str | None:
    value = value.strip()
    return f"%{value}%" if value else None


@router.get('/summary')
def summary(_admin: User = Depends(require_super_admin), db: Session = Depends(database)):
    counts = dict(db.execute(select(User.profession, func.count()).group_by(User.profession)).all())
    return {'teachers': counts.get('teacher', 0), 'students': counts.get('student', 0),
            'organizations': db.scalar(select(func.count()).select_from(Organization)),
            'participants': db.scalar(select(func.count()).select_from(ParticipantProfile)),
            'active_accounts': db.scalar(select(func.count()).select_from(User).where(User.active.is_(True)))}


@router.get("/users")
def users(
    q: str = Query(default="", max_length=100),
    profession: Literal['teacher', 'student'] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_super_admin),
    db: Session = Depends(database),
):
    query = select(User)
    if profession:
        query = query.where(User.profession == profession)
    term = search_term(q)
    if term:
        query = query.where(or_(User.name.ilike(term), User.email.ilike(term)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    account_rows = list(db.scalars(query.order_by(User.created_at.desc(), User.id).limit(limit).offset(offset)))
    if not account_rows:
        return {"items": [], "total": total, "limit": limit, "offset": offset}

    user_ids = [account.id for account in account_rows]
    organizations: dict[uuid.UUID, list[dict[str, str]]] = {user_id: [] for user_id in user_ids}
    rows = db.execute(
        select(Membership.user_id, Organization.name, Membership.role)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id.in_(user_ids))
        .order_by(Organization.name)
    )
    for user_id, organization_name, role in rows:
        organizations[user_id].append({"name": organization_name, "role": role})

    last_logins = dict(db.execute(
        select(AuthSession.user_id, func.max(AuthSession.created_at))
        .where(AuthSession.user_id.in_(user_ids))
        .group_by(AuthSession.user_id)
    ).all())
    return {
        "items": [{
            "id": account.id,
            "name": account.name,
            "email": account.email,
            "profession": account.profession,
            "active": account.active,
            "is_super_admin": account.is_super_admin,
            "created_at": account.created_at,
            "last_login_at": last_logins.get(account.id),
            "organizations": organizations[account.id],
        } for account in account_rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/participants")
def participants(
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_super_admin),
    db: Session = Depends(database),
):
    query = (
        select(Participant, ParticipantProfile, LiveSession, Presentation)
        .outerjoin(ParticipantProfile, ParticipantProfile.id == Participant.profile_id)
        .join(LiveSession, LiveSession.id == Participant.session_id)
        .join(Presentation, Presentation.id == LiveSession.presentation_id)
    )
    count_query = (
        select(func.count(Participant.id))
        .select_from(Participant)
        .outerjoin(ParticipantProfile, ParticipantProfile.id == Participant.profile_id)
        .join(LiveSession, LiveSession.id == Participant.session_id)
        .join(Presentation, Presentation.id == LiveSession.presentation_id)
    )
    term = search_term(q)
    if term:
        matches = or_(
            Participant.nickname.ilike(term),
            ParticipantProfile.name.ilike(term),
            ParticipantProfile.email.ilike(term),
            ParticipantProfile.phone.ilike(term),
            Participant.stream.ilike(term),
            Participant.semester.ilike(term),
            Participant.institution_name.ilike(term),
            Presentation.title.ilike(term),
        )
        query = query.where(matches)
        count_query = count_query.where(matches)

    total = db.scalar(count_query) or 0
    rows = db.execute(query.order_by(Participant.created_at.desc(), Participant.id).limit(limit).offset(offset)).all()
    participant_ids = [participant.id for participant, _, _, _ in rows]
    scores = {}
    if participant_ids:
        scores = dict(db.execute(
            select(Answer.participant_id, func.coalesce(func.sum(Answer.score), 0))
            .where(Answer.participant_id.in_(participant_ids))
            .group_by(Answer.participant_id)
        ).all())
    return {
        "items": [{
            "id": participant.id,
            "name": profile.name if profile else participant.nickname,
            "nickname": participant.nickname,
            "email": profile.email if profile else None,
            "phone": profile.phone if profile else None,
            "stream": participant.stream,
            "semester": participant.semester,
            "institution_name": participant.institution_name,
            "session_id": live_session.id,
            "presentation": presentation.title,
            "joined_at": participant.created_at,
            "score": scores.get(participant.id, 0),
        } for participant, profile, live_session, presentation in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
