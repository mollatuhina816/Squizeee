"""Durable live-session core with Redis invalidation and single-use socket tickets."""
import asyncio
import hashlib
import json
import logging
import secrets
import uuid
import jwt
from datetime import datetime, timezone, timedelta
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
from .models import Answer, AuditEvent, AudienceQuestion, AudienceVote, LiveSession, Participant, ParticipantProfile, Slide, User
from .questions import Question, evaluate
from .live_options import LiveOptions
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
    email: EmailStr | None = None
    guest: bool = False
    join_by_name: bool = False
    phone: str | None = Field(default=None, min_length=7, max_length=25, pattern=r"^\+?[0-9 ()-]+$")
    stream: str | None = Field(default=None, min_length=1, max_length=120)
    semester: str | None = Field(default=None, min_length=1, max_length=60)
    institution_name: str | None = Field(default=None, min_length=1, max_length=200)

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
    action: Literal["open", "show_question", "reveal_options", "next_question", "close", "reopen", "next", "end", "pause", "resume", "reveal"]
    revision: int = Field(ge=1)


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_index: int = Field(ge=0, le=99)
    answer: Any


@router.post("/organizations/{org_id}/presentations/{presentation_id}/sessions", status_code=201, dependencies=[Depends(origin_check)])
def create_session(org_id: uuid.UUID, presentation_id: uuid.UUID, options: LiveOptions | None = None, user: User = Depends(identity), db: Session = Depends(database)):
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
                              join_code=f"{secrets.randbelow(1000000):06d}", questions=[x.question for x in questions],
                              live_settings=(options or LiveOptions.model_validate(presentation.live_settings or {})).model_dump())
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
    if data.join_by_name:
        if not data.name:
            raise HTTPException(422, 'Enter your name')
        profile = None
        # A name is a display label. Only a private browser credential can
        # select a saved profile; never look up another student's name globally.
        if x_participant_token:
            saved = db.scalar(select(Participant).where(Participant.session_id == session.id,
                Participant.token_hash == hashlib.sha256(x_participant_token.encode()).hexdigest()))
            if saved and saved.profile_id:
                profile = db.get(ParticipantProfile, saved.profile_id)
        if not profile:
            try:
                claims = jwt.decode(request.cookies.get('quizeee_profile', ''), settings().jwt_secret,
                    algorithms=['HS256'], audience='quizeee-profile', issuer='quizeee',
                    options={'require': ['sub', 'iat', 'exp', 'type']})
                if claims['type'] == 'profile':
                    profile = db.get(ParticipantProfile, uuid.UUID(claims['sub']))
            except (jwt.InvalidTokenError, ValueError, TypeError):
                pass
        normalize_name = lambda value: ' '.join(value.split()).casefold()
        if profile and (profile.email is not None or normalize_name(profile.name) != normalize_name(data.name)):
            profile = None
        created_profile = False
        if not profile:
            if not data.phone:
                return {'registration_required': True}
            profile = ParticipantProfile(name=data.name, phone=data.phone, email=None)
            db.add(profile); db.flush()
            created_profile = True
        participant = db.scalar(select(Participant).where(Participant.session_id == session.id,
            Participant.profile_id == profile.id))
        if participant:
            if not x_participant_token or not secrets.compare_digest(participant.token_hash,
                    hashlib.sha256(x_participant_token.encode()).hexdigest()):
                raise HTTPException(409, 'Already joined. Reopen this quiz in the browser where you joined to resume your saved answers.')
            if data.stream is not None:
                participant.stream = data.stream
            if data.semester is not None:
                participant.semester = data.semester
            if data.institution_name is not None:
                participant.institution_name = data.institution_name
            if data.stream is not None or data.semester is not None or data.institution_name is not None:
                db.commit()
            return {'session_id': session.id, 'participant_id': participant.id, 'token': x_participant_token}
        token = secrets.token_urlsafe(32)
        participant = Participant(session_id=session.id, profile_id=profile.id, nickname=profile.name,
            stream=data.stream, semester=data.semester, institution_name=data.institution_name,
            token_hash=hashlib.sha256(token.encode()).hexdigest(), team=assign_team(db, session))
        db.add(participant); db.commit(); notify(session, db)
        if created_profile:
            from .student_routes import issue_profile_cookie
            issue_profile_cookie(response, profile)
        return {'session_id': session.id, 'participant_id': participant.id, 'token': token}
    if data.guest:
        if not session.live_settings.get('allow_guests', True):
            raise HTTPException(403, 'Guest participation is disabled')
        if x_participant_token:
            existing = db.scalar(select(Participant).where(Participant.session_id == session.id,
                Participant.token_hash == hashlib.sha256(x_participant_token.encode()).hexdigest()))
            if existing and existing.profile_id is None:
                return {'session_id': session.id, 'participant_id': existing.id, 'token': x_participant_token}
        if not data.name:
            raise HTTPException(422, 'Enter a nickname')
        token = secrets.token_urlsafe(32)
        participant = Participant(session_id=session.id, nickname=data.name,
            stream=data.stream, semester=data.semester, institution_name=data.institution_name,
            token_hash=hashlib.sha256(token.encode()).hexdigest(), team=assign_team(db, session))
        db.add(participant); db.commit(); notify(session, db)
        return {'session_id': session.id, 'participant_id': participant.id, 'token': token}
    if not data.email:
        raise HTTPException(422, 'Email is required for student profile participation')
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
            raise HTTPException(409, 'Already joined. Reopen this quiz in the browser where you joined to resume your saved answers.')
        if data.stream is not None:
            participant.stream = data.stream
        if data.semester is not None:
            participant.semester = data.semester
        if data.institution_name is not None:
            participant.institution_name = data.institution_name
        if data.stream is not None or data.semester is not None or data.institution_name is not None:
            db.commit()
        return {'session_id': session.id, 'participant_id': participant.id, 'token': x_participant_token}
    token = secrets.token_urlsafe(32)
    participant = Participant(session_id=session.id, profile_id=profile.id, nickname=profile.name,
        stream=data.stream, semester=data.semester, institution_name=data.institution_name,
        token_hash=hashlib.sha256(token.encode()).hexdigest(), team=assign_team(db, session))
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
    guided = session.live_settings.get('delivery_mode') == 'guided'
    if data.action in {'show_question', 'reveal_options', 'next_question', 'pause', 'resume', 'reveal', 'next'} and not guided:
        raise HTTPException(409, 'This control requires presenter-paced mode')
    if data.action == 'show_question':
        if session.state != 'waiting':
            raise HTTPException(409, 'This question is already showing')
        session.live_settings = {**session.live_settings, 'staged_options': True}
        session.state = 'question'
        session.opened_at = None
    elif data.action == 'reveal_options':
        if session.state != 'question':
            raise HTTPException(409, 'Show the question before revealing options')
        session.state = 'open'
        session.opened_at = datetime.now(timezone.utc)
    elif data.action == 'pause':
        if session.state != 'open' or session.paused_at:
            raise HTTPException(409, 'Only a running question can be paused')
        session.paused_at = datetime.now(timezone.utc)
    elif data.action == 'resume':
        if not session.paused_at:
            raise HTTPException(409, 'Timer is not paused')
        session.opened_at = utc(session.opened_at) + (datetime.now(timezone.utc) - utc(session.paused_at))
        session.paused_at = None
    elif data.action == 'reveal':
        if session.state != 'closed':
            raise HTTPException(409, 'Close answers before revealing')
        session.revealed = True
    elif data.action == "open":
        if session.state != "waiting":
            raise HTTPException(409, "This question has already been opened")
        session.state = "open"; session.opened_at = datetime.now(timezone.utc)
    elif data.action == "close":
        if session.state != "open":
            raise HTTPException(409, "No question is open")
        session.state = "closed"
    elif data.action == "reopen":
        if session.state != "closed":
            raise HTTPException(409, "Only closed submissions can be reopened")
        # Preserve saved progress and deadlines; reopening does not grant extra time.
        if session.revealed:
            raise HTTPException(409, 'Answers have already been revealed')
        session.state = "open"
    elif data.action in {'next', 'next_question'}:
        staged = data.action == 'next_question' or session.live_settings.get('staged_options', False)
        allowed = {'question', 'open', 'closed'} if staged else {'closed'}
        if session.state not in allowed or session.active_index + 1 >= len(session.questions):
            raise HTTPException(409, 'Close answers first; no next question after the final slide')
        session.active_index += 1
        if staged:
            session.live_settings = {**session.live_settings, 'staged_options': True}
        session.state = 'question' if staged else 'waiting'
        session.opened_at = None; session.paused_at = None; session.revealed = False
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
            "paused_at": utc(session.paused_at), "revealed": session.revealed,
            "delivery_mode": session.live_settings.get('delivery_mode', 'self_paced'),
            "teams": team_scores(db, session),
            "reveal": ({'correct_answers': q.correct_answers, 'explanation': q.explanation,
                        'hotspot_target': q.hotspot_target} if session.revealed else None),
            "question": ({**q.public(), 'options': []} if session.state == 'question' else
                         q.public() if session.state in {"open", "closed"} else None),
            "participant_count": db.scalar(select(func.count()).select_from(Participant).where(Participant.session_id == session.id)),
            "leaderboard": leaderboard(db, session.id)}


def leaderboard(db, session_id):
    session = db.get(LiveSession, session_id)
    last_indices = {}
    rows = {str(p.id): {"id": str(p.id), "nickname": p.nickname, "score": 0, "correct": 0, "elapsed_ms": 0, 'team': p.team, 'streak': 0}
            for p in db.scalars(select(Participant).where(Participant.session_id == session_id))}
    for answer in db.scalars(select(Answer).where(Answer.session_id == session_id).order_by(Answer.question_index)):
        row = rows[str(answer.participant_id)]
        row['score'] += answer.score
        row['correct'] += int(answer.correct is True)
        row['elapsed_ms'] += answer.elapsed_ms
        row['streak'] = (row['streak'] + 1 if last_indices.get(str(answer.participant_id), -1) == answer.question_index - 1 else 1) if answer.correct is True else 0
        last_indices[str(answer.participant_id)] = answer.question_index
    for row in rows.values():
        row['multiplier'] = (2 if row['streak'] >= 5 else 1.5 if row['streak'] >= 3 else 1) if session.live_settings.get('streaks') else 1
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
    data['speaker_notes'] = session.questions[session.active_index].get('speaker_notes', '')
    data['next_question'] = Question.model_validate(session.questions[session.active_index + 1]).public() if session.active_index + 1 < len(session.questions) else None
    data['settings'] = session.live_settings
    return data


@router.get("/sessions/{session_id}/participant")
def participant_snapshot(session_id: uuid.UUID, x_participant_token: str = Header(default=""), db: Session = Depends(database)):
    participant = student(db, x_participant_token, session_id)
    session = db.get(LiveSession, session_id)
    return individual_snapshot(db, session, participant)


def progress(db, session, participant):
    answers = list(db.scalars(select(Answer).where(Answer.session_id == session.id, Answer.participant_id == participant.id)))
    answered = {a.question_index for a in answers}
    if session.live_settings.get('delivery_mode') == 'guided':
        return session.active_index, utc(session.opened_at) or utc(participant.created_at), answers
    index = next((i for i in range(len(session.questions)) if i not in answered), len(session.questions))
    started = max([utc(participant.created_at), utc(session.opened_at) or utc(participant.created_at)] +
                  [utc(a.created_at) for a in answers])
    return index, started, answers


def individual_snapshot(db, session, participant):
    data = snapshot(db, session)
    index, started, answers = progress(db, session, participant)
    guided = session.live_settings.get('delivery_mode') == 'guided'
    complete = len(answers) == len(session.questions)
    data.update(active_index=min(index, len(session.questions)-1), answered=False, completed=complete,
                score=sum(a.score for a in answers), opened_at=started)
    if guided:
        data['answered'] = any(a.question_index == index for a in answers)
    if (complete and not guided) or session.state == 'ended':
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
    if session.paused_at:
        raise HTTPException(409, 'The presenter has paused the timer')
    if any(a.question_index == index for a in previous):
        raise HTTPException(409, 'Your answer was already accepted')
    elapsed = max(0, int((datetime.now(timezone.utc) - started).total_seconds() * 1000))
    guided = session.live_settings.get('delivery_mode') == 'guided'
    skipped = data.answer is None and ((not guided and elapsed >= question.duration_seconds * 1000) or question.kind == 'content')
    if not guided and elapsed > question.duration_seconds * 1000 and not skipped:
        raise HTTPException(409, "Time is up")
    try:
        correct, score = (None, 0) if skipped else evaluate(question, {"answer": data.answer}, elapsed)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if correct is True and session.live_settings.get('streaks'):
        previous_by_index = {a.question_index: a for a in previous}
        streak = 1
        for i in range(index - 1, -1, -1):
            if i not in previous_by_index or previous_by_index[i].correct is not True:
                break
            streak += 1
        score = score * (4 if streak >= 5 else 3 if streak >= 3 else 2) // 2
    answer = Answer(session_id=session.id, participant_id=participant.id, question_index=index,
                    value={"answer": data.answer}, correct=correct, score=score, elapsed_ms=elapsed)
    try:
        db.add(answer); db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Your answer was already accepted")
    notify(session, db)
    return {"accepted": True, "snapshot": individual_snapshot(db, session, participant)}


def assign_team(db, session):
    if not session.live_settings.get('team_mode'):
        return None
    counts = dict(db.execute(select(Participant.team, func.count()).where(Participant.session_id == session.id).group_by(Participant.team)).all())
    return min(range(4), key=lambda t: (counts.get(t, 0), t))


def team_scores(db, session):
    if not session.live_settings.get('team_mode'):
        return []
    # Include zero-scoring members in the average, preventing team-size advantage.
    rows = leaderboard(db, session.id)
    result = []
    for team, (name, color) in enumerate([('Coral', '#e15d67'), ('Ocean', '#4485db'), ('Amber', '#b67c06'), ('Forest', '#259a76')]):
        members = [r for r in rows if r['team'] == team]
        result.append({'id': str(team), 'nickname': name, 'color': color, 'members': len(members),
                       'score': round(sum(r['score'] for r in members) / len(members)) if members else 0})
    return sorted(result, key=lambda r: (-bool(r['members']), -r['score'], r['id']))


def publish_event(session_id, event):
    try:
        cache.publish(f'live:{session_id}', json.dumps(event))
    except RedisError:
        raise HTTPException(503, 'Real-time connection unavailable; try again')


class Reaction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    emoji: Literal['❤️', '👏', '🔥', '😂']


@router.post('/sessions/{session_id}/reactions', status_code=202)
def reaction(session_id: uuid.UUID, data: Reaction, x_participant_token: str = Header(default=''), db: Session = Depends(database)):
    participant = student(db, x_participant_token, session_id)
    if db.get(LiveSession, session_id).state == 'ended':
        raise HTTPException(409, 'Session has ended')
    rate_limit(f'reaction:{participant.id}', 12, 10)
    publish_event(session_id, {'type': 'reaction', 'id': str(uuid.uuid4()), 'emoji': data.emoji})
    return {'accepted': True}


class AudienceSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=500)


class Moderation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['approved', 'hidden', 'answered']


def audience_rows(db, session_id, participant=None, host=False):
    votes = dict(db.execute(select(AudienceVote.question_id, func.count()).join(AudienceQuestion,
        AudienceQuestion.id == AudienceVote.question_id).where(AudienceQuestion.session_id == session_id).group_by(AudienceVote.question_id)).all())
    own_votes = set(db.scalars(select(AudienceVote.question_id).where(AudienceVote.participant_id == participant.id))) if participant else set()
    rows = []
    for q in db.scalars(select(AudienceQuestion).where(AudienceQuestion.session_id == session_id)):
        if not host and q.status not in {'approved', 'answered'} and q.participant_id != participant.id:
            continue
        rows.append({'id': str(q.id), 'text': q.text, 'status': q.status, 'votes': votes.get(q.id, 0),
                     'voted': q.id in own_votes, 'own': bool(participant and participant.id == q.participant_id)})
    return sorted(rows, key=lambda q: (-q['votes'], q['id']))


@router.get('/sessions/{session_id}/audience')
def audience(session_id: uuid.UUID, x_participant_token: str = Header(default=''), db: Session = Depends(database)):
    participant = student(db, x_participant_token, session_id)
    return {'questions': audience_rows(db, session_id, participant)}


@router.get('/sessions/{session_id}/host/audience')
def host_audience(session_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    host_session(db, user, session_id)
    return {'questions': audience_rows(db, session_id, host=True)}


@router.post('/sessions/{session_id}/audience', status_code=201)
def ask_audience(session_id: uuid.UUID, data: AudienceSubmission, x_participant_token: str = Header(default=''), db: Session = Depends(database)):
    participant = student(db, x_participant_token, session_id)
    session = db.scalar(select(LiveSession).where(LiveSession.id == session_id).with_for_update())
    if session.state == 'ended':
        raise HTTPException(409, 'Session has ended')
    rate_limit(f'question:{participant.id}', 5, 60)
    if db.scalar(select(func.count()).select_from(AudienceQuestion).where(AudienceQuestion.session_id == session_id)) >= 500:
        raise HTTPException(409, 'This session has reached its question limit')
    q = AudienceQuestion(session_id=session_id, participant_id=participant.id, text=data.text)
    db.add(q); db.commit(); notify(session, db)
    return {'id': q.id, 'status': q.status}


@router.post('/sessions/{session_id}/audience/{question_id}/vote')
def upvote_audience(session_id: uuid.UUID, question_id: uuid.UUID, x_participant_token: str = Header(default=''), db: Session = Depends(database)):
    participant = student(db, x_participant_token, session_id)
    session = db.scalar(select(LiveSession).where(LiveSession.id == session_id).with_for_update())
    if session.state == 'ended':
        raise HTTPException(409, 'Session has ended')
    rate_limit(f'vote:{participant.id}', 60, 60)
    question = db.get(AudienceQuestion, question_id)
    if not question or question.session_id != session_id or question.status != 'approved':
        raise HTTPException(404, 'Question is unavailable for voting')
    if question.participant_id == participant.id:
        raise HTTPException(409, 'You cannot upvote your own question')
    if not db.get(AudienceVote, (question_id, participant.id)):
        db.add(AudienceVote(question_id=question_id, participant_id=participant.id))
        db.commit(); notify(session, db)
    return {'voted': True}


@router.post('/sessions/{session_id}/audience/{question_id}/moderate', dependencies=[Depends(origin_check)])
def moderate_audience(session_id: uuid.UUID, question_id: uuid.UUID, data: Moderation, user: User = Depends(identity), db: Session = Depends(database)):
    session = host_session(db, user, session_id, lock=True)
    question = db.get(AudienceQuestion, question_id)
    if not question or question.session_id != session_id:
        raise HTTPException(404, 'Question not found')
    question.status = data.status
    db.commit(); notify(session, db)
    return {'status': question.status}


@router.post('/sessions/{session_id}/picker', dependencies=[Depends(origin_check)])
def pick_participant(session_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    host_session(db, user, session_id)
    rate_limit(f'picker:{session_id}', 10, 60)
    participants = list(db.scalars(select(Participant).where(Participant.session_id == session_id)))
    if not participants:
        raise HTTPException(409, 'Wait for participants to join')
    picked = secrets.choice(participants)
    event = {'type': 'picker', 'id': str(uuid.uuid4()), 'participant_id': str(picked.id), 'nickname': picked.nickname}
    publish_event(session_id, event)
    return event


@router.get('/sessions/{session_id}/results')
def participant_results(session_id: uuid.UUID, x_participant_token: str = Header(default=''), db: Session = Depends(database)):
    participant = student(db, x_participant_token, session_id)
    session = db.get(LiveSession, session_id)
    index, _, _ = progress(db, session, participant)
    if session.state != 'ended' and (session.live_settings.get('delivery_mode') == 'guided' or index < len(session.questions)):
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
