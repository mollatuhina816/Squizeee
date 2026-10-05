import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now():
    return datetime.now(timezone.utc)


class Identity:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Identity, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("profession IN ('teacher','student')", name="user_profession"),)
    profession: Mapped[str] = mapped_column(String(20), default="teacher", server_default="teacher")
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Organization(Identity, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(120))
    faculty_lite_permissions: Mapped[list] = mapped_column(JSON, default=lambda: ["presentation.read"])


class Membership(Identity, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("role IN ('owner','admin','department_admin','faculty','faculty_lite')", name="membership_role"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(30))


class Department(Identity, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("organization_id", "name"), UniqueConstraint("organization_id", "id"))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))


class DepartmentAssignment(Base):
    __tablename__ = "department_assignments"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "membership_id"], ["memberships.organization_id", "memberships.id"]),
        ForeignKeyConstraint(["organization_id", "department_id"], ["departments.organization_id", "departments.id"]),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    department_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)


class AuthSession(Identity, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str] = mapped_column(String(100))


class Presentation(Identity, Base):
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    __tablename__ = "presentations"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "department_id"], ["departments.organization_id", "departments.id"]),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")


class Slide(Identity, Base):
    __tablename__ = "slides"
    __table_args__ = (UniqueConstraint("presentation_id", "ordinal"),)
    presentation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("presentations.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    question: Mapped[dict] = mapped_column(JSON)


class BankQuestion(Identity, Base):
    __tablename__ = "bank_questions"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    subject: Mapped[str] = mapped_column(String(120), default="")
    chapter: Mapped[str] = mapped_column(String(120), default="")
    topic: Mapped[str] = mapped_column(String(120), default="")
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    question: Mapped[dict] = mapped_column(JSON)


class LiveSession(Identity, Base):
    __tablename__ = "live_sessions"
    presentation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("presentations.id"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    join_code: Mapped[str | None] = mapped_column(String(6), unique=True, nullable=True)
    state: Mapped[str] = mapped_column(String(20), default="waiting")
    active_index: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    questions: Mapped[list] = mapped_column(JSON)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ParticipantProfile(Identity, Base):
    __tablename__ = "participant_profiles"
    name: Mapped[str] = mapped_column(String(60))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    phone: Mapped[str] = mapped_column(String(25))


class AchievementSettings(Base):
    __tablename__ = "achievement_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="achievement_singleton"),
        CheckConstraint("gold >= 1 AND platinum > gold AND diamond > platinum", name="achievement_order"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    gold: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    platinum: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    diamond: Mapped[int] = mapped_column(Integer, default=100, server_default="100")


class Participant(Identity, Base):
    """Session participant: credentials and scores are isolated to one session."""
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("session_id", "profile_id", name="session_participant_profile"),)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("participant_profiles.id"), nullable=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("live_sessions.id"), index=True)
    nickname: Mapped[str] = mapped_column(String(60))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)


class Answer(Identity, Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("session_id", "participant_id", "question_index"),)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("live_sessions.id"), index=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("participants.id"))
    question_index: Mapped[int] = mapped_column(Integer)
    value: Mapped[dict] = mapped_column(JSON)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0)  # thousandths of a mark
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)


class ImportBatch(Identity, Base):
    __tablename__ = "import_batches"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    rows: Mapped[list] = mapped_column(JSON)
    errors: Mapped[list] = mapped_column(JSON)
    committed: Mapped[bool] = mapped_column(Boolean, default=False)


class ScheduledQuiz(Identity, Base):
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    __tablename__ = "scheduled_quizzes"
    presentation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("presentations.id"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(160))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    questions: Mapped[list] = mapped_column(JSON)


class QuizAssignment(Identity, Base):
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    draft_answers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    __tablename__ = "quiz_assignments"
    __table_args__ = (UniqueConstraint("quiz_id", "email"),)
    quiz_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scheduled_quizzes.id"))
    email: Mapped[str] = mapped_column(String(320), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
