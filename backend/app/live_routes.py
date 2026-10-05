"""Durable live-session core with Redis invalidation and single-use socket tickets."""
import asyncio
import hashlib
import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, EmailStr, AliasChoices, field_validator
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .builder_routes import access
from .config import settings
from .db import database
from .models import Answer, AuditEvent, LiveSession, Participant, ParticipantProfile, Slide, User
from .questions import Question, evaluate
from .results import review_question
from .security import cache, identity, origin_check, rate_limit

router = APIRouter(prefix="/api/v1", tags=["live sessions"])
log = logging.getLogger(__name__)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def notify(session, db):
    # Same public projection as REST: no answers, explanations or contact details.
    try:
        payload = json.dumps(jsonable_encoder({"type": "snapshot.changed", "session_id": str(session.id),
                                              "revision": session.revision, "snapshot": snapshot(db, session)}))
        cache.setex(f"live:{session.id}:state", 86400, payload)
        cache.publish(f"live:{session.id}", payload)
    except RedisError:
        log.warning("Live notification unavailable; clients recover via periodic snapshot")


def host_session(db, user, session_id, lock=False):
    query = select(LiveSession).where(LiveSession.id == session_id)
    if lock:
        query = query.with_for_update()
    session = db.scalar(query)
    if not session:
        raise HTTPException(404, "Session not found")
    from .main import principal, require
    presentation = access(db, user, session.organization_id, session.presentation_id)
    p = principal(db, user, session.organization_id)
    require(p, "session.control", owner_id=presentation.owner_id, department_id=presentation.department_id)
    return session


def student(db, token, session_id):
    if not token or len(token) > 200:
        raise HTTPException(401, "Participant credential required")
    participant = db.scalar(select(Participant).where(Participant.session_id == session_id,
                           Participant.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if not participant:
        raise HTTPException(401, "Participant credential invalid")
    return participant


class Join(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(min_length=6, max_length=36, validation_alias=AliasChoices("code", "quiz_id"))
    name: str | None = Field(default=None, min_length=1, max_length=60, validation_alias=AliasChoices('name', 'nickname'))
    email: EmailStr
    phone: str | None = Field(default=None, min_length=7, max_length=25, pattern=r"^\+?[0-9 ()-]+$")

    @field_validator('phone')
    @classmethod
    def normalize_phone(cls, value):
        if value is None:
            return None
        digits = ''.join(c for c in value if c.isdigit())
        if not 7 <= len(digits) <= 15:
            raise ValueError('Enter a phone number with 7–15 digits')
        return ('+' if value.startswith('+') else '') + digits


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["open", "close", "next", "end"]
    revision: int = Field(ge=1)


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_index: int = Field(ge=0, le=99)
    answer: Any


@router.post("/organizations/{org_id}/presentations/{presentation_id}/sessions", status_code=201, dependencies=[Depends(origin_check)])
def create_session(org_id: uuid.UUID, presentation_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    from .main import principal, require
    presentation = access(db, user, org_id, presentation_id, write=True)
    require(principal(db, user, org_id), "session.control", owner_id=presentation.owner_id, department_id=presentation.department_id)
    questions = list(db.scalars(select(Slide).where(Slide.presentation_id == presentation_id).order_by(Slide.ordinal)))
    if not questions:
        raise HTTPException(422, "Add at least one question before presenting")
    if any(x.question["kind"] in {"form", "qa", "survey"} for x in questions):
        raise HTTPException(422, "Forms, moderated Q&A and self-paced surveys are not live-enabled yet")
    for _ in range(10):
        session = LiveSession(organization_id=org_id, presentation_id=presentation_id, owner_id=user.id,
                              join_code=f"{secrets.randbelow(1000000):06d}", questions=[x.question for x in questions])
        try:
            with db.begin_nested():
                db.add(session); db.flush()
            break
        except IntegrityError:
            continue
    else:
        raise HTTPException(503, "Unable to allocate join code; try again")
    db.add(AuditEvent(organization_id=org_id, actor_id=user.id, action="session.created", resource_id=str(session.id)))
    db.commit(); notify(session, db)
    return {"id": session.id, "join_code": session.join_code}


@router.post("/sessions/join", status_code=201)
def join(data: Join, request: Request, response: Response, x_participant_token: str = Header(default=""), db: Session = Depends(database)):
    rate_limit(f"join:{request.client.host}", 20, 60)
    if data.code.isdigit() and len(data.code) == 6:
        condition = LiveSession.join_code == data.code
    else:
        try:
            condition = LiveSession.id == uuid.UUID(data.code)
        except ValueError:
            raise HTTPException(422, 'Enter a valid Quiz ID or 6-digit quiz code')
    session = db.scalar(select(LiveSession).where(condition).with_for_update())
    if not session or session.state == "ended":
        raise HTTPException(404, "Session code is unavailable")
    email = str(data.email).casefold()
    profile = db.scalar(select(ParticipantProfile).where(ParticipantProfile.email == email))
    created_profile = False
    account = db.scalar(select(User).where(User.email == email))
    if account and not account.active:
        raise HTTPException(403, 'This account is inactive')
    if not profile:
        # Account credentials remain in users; the reusable participation profile
        # is unique by email and is not another login or enrollment record.
        name = account.name[:60] if account and account.profession == 'student' else data.name
        phone = data.phone or ('' if account and account.profession == 'student' else None)
        if not name or phone is None:
            return {'registration_required': True, 'email': email}

        try:
            with db.begin_nested():
                profile = ParticipantProfile(name=name, email=email, phone=phone)
                db.add(profile); db.flush()
                created_profile = True
        except IntegrityError:
            profile = db.scalar(select(ParticipantProfile).where(ParticipantProfile.email == str(data.email).casefold()))
    participant = db.scalar(select(Participant).where(Participant.session_id == session.id, Participant.profile_id == profile.id))
    if participant:
        # Contact details are not proof of identity. Never return an old credential.
        if not x_participant_token or not secrets.compare_digest(participant.token_hash, hashlib.sha256(x_participant_token.encode()).hexdigest()):
            raise HTTPException(409, 'Already joined. Resume in your original browser tab to keep your answers.')
        return {'session_id': session.id, 'participant_id': participant.id, 'token': x_participant_token}
    token = secrets.token_urlsafe(32)
    participant = Participant(session_id=session.id, profile_id=profile.id, nickname=profile.name, token_hash=hashlib.sha256(token.encode()).hexdigest())
    db.add(participant); db.commit(); notify(session, db)
    if created_profile and not account:
        from .student_routes import issue_profile_cookie
        issue_profile_cookie(response, profile)
    return {"session_id": session.id, "participant_id": participant.id, "token": token}


@router.post("/sessions/{session_id}/control", dependencies=[Depends(origin_check)])
def control(session_id: uuid.UUID, data: Control, user: User = Depends(identity), db: Session = Depends(database)):
    session = host_session(db, user, session_id, lock=True)
    if session.revision != data.revision:
        raise HTTPException(409, "Session changed; refresh your controls")
    if session.state == "ended":
        raise HTTPException(409, "Session has ended")
    if data.action == "open":
        if session.state != "waiting":
            raise HTTPException(409, "This question has already been opened")
        session.state = "open"; session.opened_at = datetime.now(timezone.utc)
    elif data.action == "close":
        if session.state != "open":
            raise HTTPException(409, "No question is open")
        session.state = "closed"
    elif data.action == "next":
        raise HTTPException(409, "Students advance automatically after submitting each answer")
    elif data.action == "end":
        session.state = "ended"; session.join_code = None
    session.revision += 1
    db.add(AuditEvent(organization_id=session.organization_id, actor_id=user.id, action=f"session.{data.action}", resource_id=str(session.id)))
    db.commit(); notify(session, db)
    return {"revision": session.revision, "state": session.state}


def snapshot(db, session):
    q = Question.model_validate(session.questions[session.active_index])
    return {"id": session.id, "state": session.state, "revision": session.revision,
            "active_index": session.active_index, "question_count": len(session.questions),
            "opened_at": utc(session.opened_at), "server_time": datetime.now(timezone.utc),
            "question": q.public() if session.state in {"open", "closed"} else None,
            "participant_count": db.scalar(select(func.count()).select_from(Participant).where(Participant.session_id == session.id)),
            "leaderboard": leaderboard(db, session.id)}


def leaderboard(db, session_id):
    rows = {str(p.id): {"id": str(p.id), "nickname": p.nickname, "score": 0, "correct": 0, "elapsed_ms": 0}
            for p in db.scalars(select(Participant).where(Participant.session_id == session_id))}
    for answer in db.scalars(select(Answer).where(Answer.session_id == session_id)):
        row = rows[str(answer.participant_id)]
        row['score'] += answer.score
        row['correct'] += int(answer.correct is True)
        row['elapsed_ms'] += answer.elapsed_ms
    return sorted(rows.values(), key=lambda x: (-x['score'], -x['correct'], x['elapsed_ms'], x['id']))


@router.get("/sessions/{session_id}/host")
def host_snapshot(session_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    session = host_session(db, user, session_id)
    data = snapshot(db, session)
    data["join_code"] = session.join_code
    answers = db.execute(select(Answer, Participant.nickname).join(Participant, Participant.id == Answer.participant_id)
                         .where(Answer.session_id == session_id).order_by(Answer.created_at))
    current = []
    for answer, nickname in answers:
        if answer.question_index == session.active_index:
            current.append({"answer": answer.value["answer"], "correct": answer.correct})
    data["responses"] = current
    counts = list(db.scalars(select(func.count(Answer.id)).where(Answer.session_id == session_id).group_by(Answer.participant_id)))
    data['total_responses'] = sum(counts)
    data['completed_count'] = sum(count >= len(session.questions) for count in counts)
    return data


@router.get("/sessions/{session_id}/participant")
def participant_snapshot(session_id: uuid.UUID, x_participant_token: str = Header(default=""), db: Session = Depends(database)):
    participant = student(db, x_participant_token, session_id)
    session = db.get(LiveSession, session_id)
    return individual_snapshot(db, session, participant)


def progress(db, session, participant):
    answers = list(db.scalars(select(Answer).where(Answer.session_id == session.id, Answer.participant_id == participant.id)))
    answered = {a.question_index for a in answers}
    index = next((i for i in range(len(session.questions)) if i not in answered), len(session.questions))
    started = max([utc(participant.created_at), utc(session.opened_at) or utc(participant.created_at)] +
                  [utc(a.created_at) for a in answers])
    return index, started, answers


def individual_snapshot(db, session, participant):
    data = snapshot(db, session)
    index, started, answers = progress(db, session, participant)
    complete = index == len(session.questions)
    data.update(active_index=min(index, len(session.questions)-1), answered=False, completed=complete,
                score=sum(a.score for a in answers), opened_at=started)
    if complete or session.state == 'ended':
        data.update(state='ended', question=None, answered=True)
    elif session.state in {'open', 'closed'}:
        data['question'] = Question.model_validate(session.questions[index]).public()
    return data


@router.post("/sessions/{session_id}/responses", status_code=201)
def respond(session_id: uuid.UUID, data: Submission, x_participant_token: str = Header(default=""), db: Session = Depends(database)):
    participant = student(db, x_participant_token, session_id)
    rate_limit(f"response:{participant.id}", 30, 60)
    session = db.scalar(select(LiveSession).where(LiveSession.id == session_id).with_for_update())
    index, started, previous = progress(db, session, participant)
    if session.state != "open" or data.question_index != index or index >= len(session.questions):
        raise HTTPException(409, "This question is not accepting answers")
    question = Question.model_validate(session.questions[index])
    elapsed = max(0, int((datetime.now(timezone.utc) - started).total_seconds() * 1000))
    skipped = data.answer is None and (elapsed >= question.duration_seconds * 1000 or question.kind == 'content')
    if elapsed > question.duration_seconds * 1000 and not skipped:
        raise HTTPException(409, "Time is up")
    try:
        correct, score = (None, 0) if skipped else evaluate(question, {"answer": data.answer}, elapsed)
    except ValueError as e:
        raise HTTPException(422, str(e))
    answer = Answer(session_id=session.id, participant_id=participant.id, question_index=index,
                    value={"answer": data.answer}, correct=correct, score=score, elapsed_ms=elapsed)
    try:
        db.add(answer); db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Your answer was already accepted")
    notify(session, db)
    return {"accepted": True, "snapshot": individual_snapshot(db, session, participant)}


@router.get('/sessions/{session_id}/results')
def participant_results(session_id: uuid.UUID, x_participant_token: str = Header(default=''), db: Session = Depends(database)):
    participant = student(db, x_participant_token, session_id)
    session = db.get(LiveSession, session_id)
    index, _, _ = progress(db, session, participant)
    if session.state != 'ended' and index < len(session.questions):
        raise HTTPException(409, 'Complete the quiz before previewing answers')
    answers = {a.question_index: a for a in db.scalars(select(Answer).where(
        Answer.session_id == session_id, Answer.participant_id == participant.id))}
    questions = []
    for index, raw in enumerate(session.questions):
        answer = answers.get(index)
        questions.append(review_question(index, raw, answer.value['answer'] if answer else None,
                                         answer.correct if answer else None, answer.score if answer else 0))
    return {'title': 'Your quiz results', 'score': sum(a.score for a in answers.values()), 'questions': questions}


def ticket(session_id):
    token = secrets.token_urlsafe(32)
    try:
        cache.setex(f"ws-ticket:{hashlib.sha256(token.encode()).hexdigest()}", 30, str(session_id))
    except RedisError:
        raise HTTPException(503, "Live connection temporarily unavailable")
    return {"ticket": token}


@router.post("/sessions/{session_id}/host-ticket", dependencies=[Depends(origin_check)])
def host_ticket(session_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    host_session(db, user, session_id)
    return ticket(session_id)


@router.post("/sessions/{session_id}/participant-ticket")
def participant_ticket(session_id: uuid.UUID, x_participant_token: str = Header(default=""), db: Session = Depends(database)):
    student(db, x_participant_token, session_id)
    return ticket(session_id)


@router.websocket("/live/ws")
async def socket(websocket: WebSocket):
    if websocket.headers.get("origin") != settings().app_origin:
        await websocket.close(code=1008); return
    await websocket.accept()
    redis = AsyncRedis.from_url(settings().redis_url, decode_responses=True)
    try:
        # Token arrives in the first frame, never in the URL or access log.
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        if len(raw) > 200:
            await websocket.close(code=1008); return
        session_id = await redis.getdel(f"ws-ticket:{hashlib.sha256(raw.encode()).hexdigest()}")
        if not session_id:
            await websocket.close(code=1008); return
        async with redis.pubsub() as pubsub:
            await pubsub.subscribe(f"live:{session_id}")
            # Wait for Redis subscription acknowledgement before requesting recovery.
            while True:
                subscribed = await pubsub.get_message(timeout=5)
                if subscribed and subscribed['type'] == 'subscribe':
                    break
                if not subscribed:
                    raise asyncio.TimeoutError()
            await websocket.send_json({"type": "ready"})
            # Connection lifetime is bounded; reconnect requires fresh authorization.
            deadline = asyncio.get_running_loop().time() + 60
            while asyncio.get_running_loop().time() < deadline:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5)
                if message:
                    await websocket.send_text(message["data"])
                else:
                    await websocket.send_json({"type": "heartbeat"})
            await websocket.close(code=1000)
    except (WebSocketDisconnect, asyncio.TimeoutError, RedisError):
        pass
    finally:
        await redis.aclose()
