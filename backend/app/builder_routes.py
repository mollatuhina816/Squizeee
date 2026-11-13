import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from .db import database
from .models import AuditEvent, BankQuestion, Presentation, Slide, User
from .questions import Question
from .live_options import LiveOptions
from .security import identity, origin_check

router = APIRouter(prefix="/api/v1/organizations/{org_id}", tags=["quiz builder"])


def access(db, user, org_id, presentation_id, write=False):
    from .main import principal, presentation_scope, require
    p = principal(db, user, org_id)
    query = presentation_scope(select(Presentation).where(Presentation.id == presentation_id), p)
    if write:
        query = query.with_for_update()
    item = db.scalar(query)
    if not item:
        raise HTTPException(404, "Presentation not found")
    require(p, "presentation.write" if write else "presentation.read", owner_id=item.owner_id, department_id=item.department_id)
    return item


Duration = Literal[10, 15, 20, 30, 45, 60, 90, 120]


class SlideSet(BaseModel):
    live_settings: LiveOptions | None = None
    duration_minutes: Duration | None = None
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    questions: list[Question] = Field(max_length=100)


class BankInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: Question
    subject: str = Field(default="", max_length=120)
    chapter: str = Field(default="", max_length=120)
    topic: str = Field(default="", max_length=120)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    tags: list[str] = Field(default_factory=list, max_length=20)


class BankBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[BankInput] = Field(min_length=1, max_length=20)


def create_bank_question(db, user, org_id, data):
    item = BankQuestion(organization_id=org_id, owner_id=user.id, **data.model_dump(mode="json"))
    db.add(item)
    db.flush()
    db.add(AuditEvent(organization_id=org_id, actor_id=user.id,
                      action="bank.question_created", resource_id=str(item.id)))
    return item


@router.get("/presentations/{presentation_id}/slides")
def get_slides(org_id: uuid.UUID, presentation_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    presentation = access(db, user, org_id, presentation_id)
    slides = db.scalars(select(Slide).where(Slide.presentation_id == presentation_id).order_by(Slide.ordinal))
    return {"title": presentation.title, "duration_minutes": presentation.duration_minutes,
            "live_settings": presentation.live_settings, "revision": presentation.revision, "questions": [x.question for x in slides]}


@router.put("/presentations/{presentation_id}/slides", dependencies=[Depends(origin_check)])
def save_slides(org_id: uuid.UUID, presentation_id: uuid.UUID, data: SlideSet, user: User = Depends(identity), db: Session = Depends(database)):
    presentation = access(db, user, org_id, presentation_id, write=True)
    if presentation.revision != data.revision:
        raise HTTPException(409, "Presentation changed; reload before saving")
    db.execute(delete(Slide).where(Slide.presentation_id == presentation_id))
    for ordinal, question in enumerate(data.questions):
        db.add(Slide(presentation_id=presentation_id, ordinal=ordinal, question=question.model_dump(mode="json")))
    if data.duration_minutes is not None:
        presentation.duration_minutes = data.duration_minutes
    if data.live_settings is not None:
        presentation.live_settings = data.live_settings.model_dump()
    presentation.revision += 1
    db.add(AuditEvent(organization_id=org_id, actor_id=user.id, action="presentation.slides_saved", resource_id=str(presentation.id)))
    db.commit()
    return {"revision": presentation.revision}


@router.delete("/presentations/{presentation_id}", dependencies=[Depends(origin_check)])
def delete_presentation(org_id: uuid.UUID, presentation_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    from .models import Answer, AudienceQuestion, AudienceVote, LiveSession, Participant, QuizAssignment, ScheduledQuiz
    presentation = access(db, user, org_id, presentation_id, write=True)
    session_ids = select(LiveSession.id).where(LiveSession.presentation_id == presentation_id)
    participant_ids = select(Participant.id).where(Participant.session_id.in_(session_ids))
    question_ids = select(AudienceQuestion.id).where(AudienceQuestion.session_id.in_(session_ids))
    db.execute(delete(AudienceVote).where(AudienceVote.question_id.in_(question_ids) | AudienceVote.participant_id.in_(participant_ids)))
    db.execute(delete(AudienceQuestion).where(AudienceQuestion.session_id.in_(session_ids)))
    db.execute(delete(Answer).where(Answer.session_id.in_(session_ids)))
    db.execute(delete(Participant).where(Participant.session_id.in_(session_ids)))
    db.execute(delete(LiveSession).where(LiveSession.presentation_id == presentation_id))
    quiz_ids = select(ScheduledQuiz.id).where(ScheduledQuiz.presentation_id == presentation_id)
    db.execute(delete(QuizAssignment).where(QuizAssignment.quiz_id.in_(quiz_ids)))
    db.execute(delete(ScheduledQuiz).where(ScheduledQuiz.presentation_id == presentation_id))
    db.execute(delete(Slide).where(Slide.presentation_id == presentation_id))
    db.add(AuditEvent(organization_id=org_id, actor_id=user.id, action="presentation.deleted", resource_id=str(presentation.id)))
    db.delete(presentation)
    db.commit()
    return {"ok": True, "id": presentation_id}


@router.get("/bank/questions")
def list_bank(org_id: uuid.UUID, subject: str = "", user: User = Depends(identity), db: Session = Depends(database)):
    from .main import principal, require
    p = principal(db, user, org_id)
    require(p, "bank.write", owner_id=user.id)
    query = select(BankQuestion).where(BankQuestion.organization_id == org_id)
    if p.role not in {"owner", "admin"}:
        query = query.where(BankQuestion.owner_id == user.id)
    if subject:
        query = query.where(BankQuestion.subject == subject)
    return [{"id": x.id, "question": x.question, "subject": x.subject, "chapter": x.chapter, "topic": x.topic,
             "difficulty": x.difficulty, "tags": x.tags} for x in db.scalars(query.order_by(BankQuestion.created_at.desc()).limit(100))]


@router.post("/bank/questions", status_code=201, dependencies=[Depends(origin_check)])
def save_bank(org_id: uuid.UUID, data: BankInput, user: User = Depends(identity), db: Session = Depends(database)):
    from .main import principal, require
    p = principal(db, user, org_id)
    require(p, "bank.write", owner_id=user.id)
    item = create_bank_question(db, user, org_id, data)
    db.commit()
    return {"id": item.id}


@router.post("/bank/questions/bulk", status_code=201, dependencies=[Depends(origin_check)])
def save_bank_bulk(org_id: uuid.UUID, data: BankBatch, user: User = Depends(identity), db: Session = Depends(database)):
    from .main import principal, require
    p = principal(db, user, org_id)
    require(p, "bank.write", owner_id=user.id)
    items = [create_bank_question(db, user, org_id, item) for item in data.items]
    db.commit()
    return {"ids": [item.id for item in items]}
