"""Private student history, derived from durable results without duplicate awards."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .admin_routes import require_super_admin
from .config import settings
from .db import database
from .models import (AchievementSettings, Answer, AuditEvent, LiveSession, Participant,
                     ParticipantProfile, Presentation, QuizAssignment, ScheduledQuiz, User)
from .questions import Question
from .security import identity, origin_check

router = APIRouter(prefix='/api/v1', tags=['student profile'])
SCORED_KINDS = {'mcq', 'quiz', 'true_false', 'multiple_select', 'short_answer'}


def ensure_profile(db, user):
    email = user.email.casefold()
    profile = db.scalar(select(ParticipantProfile).where(ParticipantProfile.email == email))
    if not profile:
        try:
            with db.begin_nested():
                profile = ParticipantProfile(name=user.name[:60], email=email, phone='')
                db.add(profile)
                db.flush()
        except IntegrityError:
            profile = db.scalar(select(ParticipantProfile).where(ParticipantProfile.email == email))
    return profile


def issue_profile_cookie(response, profile):
    """Only issued on first guest registration, never on email-only repeat joins."""
    now = datetime.now(timezone.utc)
    token = jwt.encode({'sub': str(profile.id), 'iat': now, 'exp': now + timedelta(days=30),
                        'iss': 'quizeee', 'aud': 'quizeee-profile', 'type': 'profile'},
                       settings().jwt_secret, algorithm='HS256')
    response.set_cookie('quizeee_profile', token, httponly=True, samesite='strict',
                        secure=settings().environment == 'production', max_age=30*86400, path='/')


def profile_identity(request, db):
    if request.cookies.get('quizeee_access'):
        try:
            user = identity(request, db)
        except HTTPException:
            user = None
        else:
            if user.profession == 'student':
                profile = ensure_profile(db, user)
                db.commit()
                return profile, user
    try:
        claims = jwt.decode(request.cookies.get('quizeee_profile', ''), settings().jwt_secret,
                            algorithms=['HS256'], audience='quizeee-profile', issuer='quizeee',
                            options={'require': ['sub', 'iat', 'exp', 'type']})
        if claims['type'] != 'profile':
            raise ValueError()
        profile = db.get(ParticipantProfile, uuid.UUID(claims['sub']))
        if not profile:
            raise ValueError()
        # Once an account exists, its login is required for private history.
        if db.scalar(select(User.id).where(User.email == profile.email)):
            raise ValueError()
        return profile, None
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(401, 'Sign in with your student account to view your profile. New guest profiles are available in the browser where you registered.')


class Thresholds(BaseModel):
    model_config = ConfigDict(extra='forbid')
    gold: int = Field(default=10, ge=1, le=100000, strict=True)
    platinum: int = Field(default=50, ge=1, le=100000, strict=True)
    diamond: int = Field(default=100, ge=1, le=100000, strict=True)

    @model_validator(mode='after')
    def ordered(self):
        if not self.gold < self.platinum < self.diamond:
            raise ValueError('Use increasing thresholds: Gold < Platinum < Diamond')
        return self


def thresholds(db):
    row = db.get(AchievementSettings, 1)
    return {name: getattr(row, name) for name in ('gold', 'platinum', 'diamond')} if row else Thresholds().model_dump()


@router.get('/admin/achievement-settings')
def get_settings(_admin: User = Depends(require_super_admin), db: Session = Depends(database)):
    return thresholds(db)


@router.put('/admin/achievement-settings', dependencies=[Depends(origin_check)])
def update_settings(data: Thresholds, admin: User = Depends(require_super_admin), db: Session = Depends(database)):
    row = db.scalar(select(AchievementSettings).where(AchievementSettings.id == 1).with_for_update())
    if not row:
        row = AchievementSettings(id=1)
        db.add(row)
    for name, value in data.model_dump().items():
        setattr(row, name, value)
    db.add(AuditEvent(actor_id=admin.id, action='achievement.settings.updated', resource_id='1'))
    db.commit()
    return thresholds(db)


def maximum_score(questions):
    return sum(int((q.marks + q.speed_bonus) * 1000)
               for q in map(Question.model_validate, questions) if q.kind in SCORED_KINDS)


def history_row(source, attempt_id, title, date, score, maximum, completed):
    percentage = round(score * 100 / maximum, 2) if maximum else None
    # 80% earns 80 points. Negative scores earn zero; ungraded quizzes earn zero.
    points = int((Decimal(max(0, min(score, maximum))) * 100 / maximum).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP)) if completed and maximum else 0
    return {'id': str(attempt_id), 'source': source, 'title': title, 'date': date,
            'score': score / 1000, 'total_marks': maximum / 1000, 'percentage': percentage,
            'status': 'Completed' if completed else 'In progress', 'points': points}


@router.get('/student/profile')
def student_profile(request: Request, db: Session = Depends(database)):
    profile, user = profile_identity(request, db)
    from .scheduled_routes import expire_attempt, utc
    history = []
    if user:
        rows = db.execute(select(ScheduledQuiz, QuizAssignment).join(QuizAssignment).where(
            QuizAssignment.email == user.email,
            (QuizAssignment.started_at.is_not(None) | QuizAssignment.submitted_at.is_not(None)))
            .with_for_update(of=QuizAssignment)).all()
        for quiz, assignment in rows:
            expire_attempt(quiz, assignment)
            row = history_row('scheduled', assignment.id, quiz.title,
                              utc(assignment.submitted_at or assignment.started_at), assignment.score or 0,
                              maximum_score(quiz.questions), assignment.submitted_at is not None)
            row['quiz_id'] = str(quiz.id)
            history.append(row)
        db.commit()

    scores = select(Answer.participant_id.label('participant_id'), func.sum(Answer.score).label('score'),
                    func.count(Answer.id).label('count'), func.max(Answer.created_at).label('last_answer'))\
        .join(Participant, Participant.id == Answer.participant_id).where(Participant.profile_id == profile.id)\
        .group_by(Answer.participant_id).subquery()
    rows = db.execute(select(Participant, LiveSession, Presentation.title, scores.c.score,
                             scores.c.count, scores.c.last_answer)
                      .join(LiveSession, LiveSession.id == Participant.session_id)
                      .join(Presentation, Presentation.id == LiveSession.presentation_id)
                      .outerjoin(scores, scores.c.participant_id == Participant.id)
                      .where(Participant.profile_id == profile.id))
    for participant, session, title, score, count, last_answer in rows:
        completed = session.state == 'ended' or (count or 0) >= len(session.questions)
        history.append(history_row('live', participant.id, title,
                                   utc(last_answer or participant.created_at), score or 0,
                                   maximum_score(session.questions), completed))
    history.sort(key=lambda row: (row['date'], row['id']), reverse=True)
    completed = [row for row in history if row['status'] == 'Completed']
    percentages = [row['percentage'] for row in completed if row['percentage'] is not None]
    average = round(sum(percentages) / len(percentages), 2) if percentages else None
    levels = thresholds(db)
    current = None
    next_level = None
    for level, threshold in levels.items():
        if len(completed) >= threshold:
            current = level.title()
        elif next_level is None:
            next_level = {'name': level.title(), 'threshold': threshold,
                          'remaining': threshold - len(completed)}
    return {'id': profile.id, 'name': user.name if user else profile.name, 'email': profile.email,
            'account': user is not None, 'total_attempted': len(history), 'completed_quizzes': len(completed),
            'total_points': sum(row['points'] for row in completed),
            'average_score': average, 'highest_score': max(percentages) if percentages else None,
            'lowest_score': min(percentages) if percentages else None,
            'performance': 'No scored quizzes yet' if average is None else 'Excellent' if average >= 80
                           else 'Good progress' if average >= 60 else 'Keep practicing',
            'achievement': current, 'next_achievement': next_level, 'thresholds': levels, 'history': history}
