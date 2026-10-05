"""Email-addressed, time-windowed quizzes with immutable question snapshots."""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field, AwareDatetime, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .builder_routes import access
from .db import database
from .models import ScheduledQuiz, QuizAssignment, Slide, User, AuditEvent
from .questions import Question, evaluate
from .security import identity, origin_check
from .results import review_question

router = APIRouter(prefix="/api/v1", tags=["scheduled quizzes"])
SUPPORTED = {"mcq", "multiple_select", "true_false", "short_answer", "quiz"}


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class Schedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    students: list[EmailStr] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def window(self):
        if self.ends_at <= self.starts_at or self.ends_at <= datetime.now(timezone.utc):
            raise ValueError("End time must be after the start time and in the future")
        return self


@router.post('/organizations/{org_id}/presentations/{presentation_id}/schedule', status_code=201, dependencies=[Depends(origin_check)])
def schedule(org_id: uuid.UUID, presentation_id: uuid.UUID, data: Schedule, user: User = Depends(identity), db: Session = Depends(database)):
    presentation = access(db, user, org_id, presentation_id, write=True)
    if user.profession != 'teacher':
        raise HTTPException(403, 'Only teachers can schedule quizzes')
    if presentation.revision != data.revision:
        raise HTTPException(409, 'Presentation changed; reload before scheduling')
    questions = list(db.scalars(select(Slide).where(Slide.presentation_id == presentation_id).order_by(Slide.ordinal)))
    if not questions:
        raise HTTPException(422, 'Save at least one question before scheduling')
    if any(q.question['kind'] not in SUPPORTED for q in questions):
        raise HTTPException(422, 'Scheduled quizzes support MCQ, multiple select, true/false, short answer and quiz questions')
    # Independent quizzes use marks/negative marks; no live-response speed bonus.
    snapshot = [dict(q.question, speed_bonus='0') for q in questions]
    quiz = ScheduledQuiz(presentation_id=presentation.id, owner_id=user.id, title=presentation.title,
                         starts_at=data.starts_at, ends_at=data.ends_at, questions=snapshot, duration_minutes=presentation.duration_minutes)
    db.add(quiz); db.flush()
    for email in {str(email).casefold() for email in data.students}:
        db.add(QuizAssignment(quiz_id=quiz.id, email=email))
    db.add(AuditEvent(actor_id=user.id, organization_id=org_id, action='quiz.scheduled', resource_id=str(quiz.id)))
    db.commit()
    return {'id': quiz.id, 'title': quiz.title}


def assigned(db, user, quiz_id, lock=False):
    if user.profession != 'student':
        raise HTTPException(403, 'Student account required')
    query = select(QuizAssignment).where(QuizAssignment.quiz_id == quiz_id, QuizAssignment.email == user.email)
    assignment = db.scalar(query.with_for_update() if lock else query)
    if not assignment:
        raise HTTPException(404, 'Quiz not found')
    quiz = db.get(ScheduledQuiz, quiz_id)
    if lock and expire_attempt(quiz, assignment):
        db.commit()
    return quiz, assignment


def summary(quiz, assignment):
    now = datetime.now(timezone.utc)
    status = 'submitted' if assignment.submitted_at else 'upcoming' if now < utc(quiz.starts_at) else 'closed' if now >= utc(quiz.ends_at) else 'open'
    return {'id': quiz.id, 'title': quiz.title, 'starts_at': utc(quiz.starts_at), 'ends_at': utc(quiz.ends_at),
            'status': status, 'score': assignment.score, 'question_count': len(quiz.questions),
            'duration_minutes': quiz.duration_minutes, 'started_at': utc(assignment.started_at) if assignment.started_at else None,
            'deadline_at': utc(assignment.deadline_at) if assignment.deadline_at else None, 'server_now': now}


@router.get('/student/quizzes')
def student_quizzes(user: User = Depends(identity), db: Session = Depends(database)):
    if user.profession != 'student':
        raise HTTPException(403, 'Student account required')
    rows = db.execute(select(ScheduledQuiz, QuizAssignment).join(QuizAssignment).where(
        QuizAssignment.email == user.email).order_by(ScheduledQuiz.starts_at.desc()).limit(200))
    return [summary(q, a) for q, a in rows]


@router.get('/student/quizzes/{quiz_id}')
def get_quiz(quiz_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    quiz, assignment = assigned(db, user, quiz_id, lock=True)
    return attempt_detail(quiz, assignment)


def attempt_detail(quiz, assignment):
    result = summary(quiz, assignment)
    if result['status'] == 'open' and assignment.started_at:
        result['questions'] = [Question(**q).public() for q in quiz.questions]
        result['answers'] = assignment.draft_answers or [None] * len(quiz.questions)
    return result


class Submit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list[Any] = Field(max_length=100)


@router.get('/student/quizzes/{quiz_id}/results')
def results(quiz_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    quiz, assignment = assigned(db, user, quiz_id, lock=True)
    if not assignment.submitted_at:
        raise HTTPException(409, 'Submit the quiz before previewing answers')
    questions = []
    for index, (raw, answer) in enumerate(zip(quiz.questions, assignment.answers)):
        correct, score = (None, 0) if answer is None else evaluate(Question(**raw), {'answer': answer}, 0)
        questions.append(review_question(index, raw, answer, correct, score))
    return {'title': quiz.title, 'score': assignment.score, 'questions': questions}


@router.post('/student/quizzes/{quiz_id}/submit', dependencies=[Depends(origin_check)])
def submit(quiz_id: uuid.UUID, data: Submit, user: User = Depends(identity), db: Session = Depends(database)):
    quiz, assignment = assigned(db, user, quiz_id, lock=True)
    if assignment.submitted_at:
        # A timed-out attempt always returns its immutable result on retries.
        if assignment.deadline_at and utc(assignment.submitted_at) >= utc(assignment.deadline_at):
            return summary(quiz, assignment)
        raise HTTPException(409, 'Quiz has already been submitted')
    if summary(quiz, assignment)['status'] != 'open' or not assignment.started_at:
        raise HTTPException(409, 'Start the quiz before submitting')
    answers = validate_answers(quiz, data.answers)
    finalize(quiz, assignment, answers, datetime.now(timezone.utc))
    db.commit()
    return summary(quiz, assignment)


def validate_answers(quiz, answers):
    if len(answers) != len(quiz.questions):
        raise HTTPException(422, 'Include an answer or null for each question')
    cleaned=[]
    for index, (raw, answer) in enumerate(zip(quiz.questions, answers)):
        if answer is None or answer == '' or answer == []:
            cleaned.append(None)
            continue
        try:
            evaluate(Question(**raw), {'answer': answer}, 0)
        except ValueError as exc:
            raise HTTPException(422, f'Question {index + 1}: {exc}')
        cleaned.append(answer)
    return cleaned


def finalize(quiz, assignment, answers, submitted_at):
    assignment.answers = answers
    assignment.score = sum(evaluate(Question(**raw), {'answer': answer}, 0)[1]
                           for raw, answer in zip(quiz.questions, answers) if answer is not None)
    assignment.submitted_at = submitted_at


def expire_attempt(quiz, assignment):
    if not assignment.submitted_at and assignment.deadline_at and datetime.now(timezone.utc) >= utc(assignment.deadline_at):
        finalize(quiz, assignment, assignment.draft_answers or [None] * len(quiz.questions), utc(assignment.deadline_at))
        return True
    return False


def expire_due_attempts(db):
    assignments = db.scalars(select(QuizAssignment).where(QuizAssignment.submitted_at.is_(None),
        QuizAssignment.deadline_at <= datetime.now(timezone.utc)).with_for_update(skip_locked=True).limit(200))
    for assignment in assignments:
        expire_attempt(db.get(ScheduledQuiz, assignment.quiz_id), assignment)
    db.commit()


@router.post('/student/quizzes/{quiz_id}/start', dependencies=[Depends(origin_check)])
def start(quiz_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    quiz, assignment = assigned(db, user, quiz_id, lock=True)
    if assignment.submitted_at:
        return attempt_detail(quiz, assignment)
    if summary(quiz, assignment)['status'] != 'open':
        raise HTTPException(409, 'Quiz is not open')
    if not assignment.started_at:
        from .student_routes import ensure_profile
        ensure_profile(db, user)
        now = datetime.now(timezone.utc)
        assignment.started_at = now
        assignment.deadline_at = min(now + timedelta(minutes=quiz.duration_minutes), utc(quiz.ends_at))
        assignment.draft_answers = [None] * len(quiz.questions)
        db.commit()
    return attempt_detail(quiz, assignment)


@router.put('/student/quizzes/{quiz_id}/draft', dependencies=[Depends(origin_check)])
def save_draft(quiz_id: uuid.UUID, data: Submit, user: User = Depends(identity), db: Session = Depends(database)):
    quiz, assignment = assigned(db, user, quiz_id, lock=True)
    if assignment.submitted_at:
        return summary(quiz, assignment)
    if not assignment.started_at or summary(quiz, assignment)['status'] != 'open':
        raise HTTPException(409, 'Start the quiz before answering')
    assignment.draft_answers = validate_answers(quiz, data.answers)
    db.commit()
    return summary(quiz, assignment)



@router.get('/organizations/{org_id}/presentations/{presentation_id}/schedules')
def schedules(org_id: uuid.UUID, presentation_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    access(db, user, org_id, presentation_id, write=True)
    quizzes = db.scalars(select(ScheduledQuiz).where(ScheduledQuiz.presentation_id == presentation_id).order_by(ScheduledQuiz.starts_at.desc()))
    return [{'id': q.id, 'title': q.title, 'starts_at': q.starts_at, 'ends_at': q.ends_at, 'duration_minutes': q.duration_minutes,
             'students': [{'email': a.email, 'submitted_at': a.submitted_at, 'score': a.score} for a in db.scalars(select(QuizAssignment).where(QuizAssignment.quiz_id == q.id))]} for q in quizzes]
