import uuid
import asyncio
import logging
from contextlib import suppress
from typing import Literal
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import settings
from .db import database
from .models import AuditEvent, Department, DepartmentAssignment, Membership, Organization, Presentation, User
from .permissions import Principal, permits
from .security import (DUMMY_HASH, cache, clear_auth_cookies, identity, issue_session,
                       origin_check, passwords, rate_limit, revoke_session, rotate_session)

@asynccontextmanager
async def lifespan(app):
    async def expire_quizzes():
        from .db import SessionLocal
        from .scheduled_routes import expire_due_attempts
        def sweep():
            with SessionLocal() as db:
                expire_due_attempts(db)
        while True:
            try:
                if database not in app.dependency_overrides:
                    await asyncio.to_thread(sweep)
            except Exception:
                logging.getLogger(__name__).exception('Quiz expiry sweep failed; retrying')
            await asyncio.sleep(1)
    task = asyncio.create_task(expire_quizzes())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Quizeee API", version="0.1.0", docs_url="/docs", lifespan=lifespan)
from .middleware import BodyLimitMiddleware
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=[settings().app_origin], allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "Authorization"])


@app.middleware("http")
async def headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    return response


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    remember_me: bool = Field(default=False, strict=True)


class Register(Login):
    name: str = Field(min_length=1, max_length=120)
    profession: Literal["teacher", "student"] = "teacher"
    organization: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def teacher_workspace(self):
        if not (any(char.islower() for char in self.password)
                and any(char.isupper() for char in self.password)
                and any(char.isdigit() for char in self.password)
                and any(not char.isalnum() for char in self.password)):
            raise ValueError("Password must include lowercase and uppercase letters, a number, and a symbol")
        if self.profession == "teacher" and not (self.organization and self.organization.strip()):
            raise ValueError("Teachers must enter an organization name")
        return self


class Named(Input):
    name: str = Field(min_length=1, max_length=120)


class PresentationInput(Input):
    title: str = Field(min_length=1, max_length=160)
    department_id: uuid.UUID | None = None


class Rename(Input):
    title: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)


def audit(db, user, org, action, resource):
    db.add(AuditEvent(actor_id=user.id, organization_id=org, action=action, resource_id=str(resource)))


def principal(db, user, org_id):
    membership = db.scalar(select(Membership).where(Membership.organization_id == org_id, Membership.user_id == user.id))
    if not membership:
        raise HTTPException(404, "Organization not found")
    org = db.get(Organization, org_id)
    departments = frozenset(db.scalars(select(DepartmentAssignment.department_id).where(
        DepartmentAssignment.organization_id == org_id, DepartmentAssignment.membership_id == membership.id)))
    return Principal(user.id, org_id, membership.role, departments, frozenset(org.faculty_lite_permissions))


def require(p, permission, **scope):
    if not permits(p, permission, organization_id=p.organization_id, **scope):
        raise HTTPException(403, "Permission denied")


def presentation_scope(query, p):
    query = query.where(Presentation.organization_id == p.organization_id)
    if p.role == "department_admin":
        query = query.where(Presentation.department_id.in_(p.departments))
    elif p.role not in {"owner", "admin"}:
        query = query.where(Presentation.owner_id == p.user_id)
    return query


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: Session = Depends(database)):
    try:
        db.execute(text("SELECT 1"))
        cache.ping()
    except Exception:
        raise HTTPException(503, "Dependencies unavailable")
    return {"status": "ready"}


@app.post("/api/v1/auth/register", status_code=201, dependencies=[Depends(origin_check)])
def register(data: Register, request: Request, response: Response, db: Session = Depends(database)):
    rate_limit(f"register:{request.client.host}", 5, 3600)
    email = str(data.email).casefold()
    user = User(email=email, name=data.name, profession=data.profession, password_hash=passwords.hash(data.password))
    org = Organization(name=data.organization.strip()) if data.profession == "teacher" else None
    try:
        db.add(user)
        if org:
            db.add(org)
        db.flush()
        if org:
            db.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))
            audit(db, user, org.id, "organization.created", org.id)
        else:
            audit(db, user, None, "student.registered", user.id)
        tokens = issue_session(db, user, response, data.remember_me)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Unable to register these account details")
    return {"id": user.id, "name": user.name, "profession": user.profession,
            "organization_id": org.id if org else None, **tokens}


@app.post("/api/auth/login", dependencies=[Depends(origin_check)])
@app.post("/api/v1/auth/login", dependencies=[Depends(origin_check)])
def login(data: Login, request: Request, response: Response, db: Session = Depends(database)):
    email = str(data.email).casefold()
    rate_limit(f"login-ip:{request.client.host}", 30, 60)
    rate_limit(f"login-email:{email}", 10, 60)
    user = db.scalar(select(User).where(User.email == email))
    valid = passwords.verify(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        raise HTTPException(401, "Invalid email or password")
    tokens = issue_session(db, user, response, data.remember_me)
    audit(db, user, None, "auth.login", user.id)
    db.commit()
    return {"id": user.id, "name": user.name, "profession": user.profession, **tokens}


@app.post("/api/auth/refresh", dependencies=[Depends(origin_check)])
@app.post("/api/v1/auth/refresh", dependencies=[Depends(origin_check)])
def refresh(request: Request, response: Response, db: Session = Depends(database)):
    rate_limit(f"refresh-ip:{request.client.host}", 60, 60)
    try:
        return rotate_session(db, request, response)
    except HTTPException as error:
        if error.status_code != 401:
            raise
        denied = JSONResponse({"detail": error.detail}, status_code=401)
        clear_auth_cookies(denied)
        return denied


@app.post("/api/auth/logout", dependencies=[Depends(origin_check)])
@app.post("/api/v1/auth/logout", dependencies=[Depends(origin_check)])
def logout(request: Request, response: Response, db: Session = Depends(database)):
    revoke_session(db, request)
    clear_auth_cookies(response)
    return {"ok": True}


@app.get("/api/v1/auth/me")
def me(user: User = Depends(identity)):
    return {"id": user.id, "name": user.name, "email": user.email,
            "profession": user.profession, "is_super_admin": user.is_super_admin}


@app.get("/api/v1/organizations")
def organizations(user: User = Depends(identity), db: Session = Depends(database)):
    rows = db.execute(select(Organization, Membership.role).join(Membership, Membership.organization_id == Organization.id)
                      .where(Membership.user_id == user.id).order_by(Organization.name).limit(100))
    return [{"id": org.id, "name": org.name, "role": role} for org, role in rows]


@app.get("/api/v1/organizations/{org_id}/members")
def members(org_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    p = principal(db, user, org_id)
    require(p, "members.manage")  # Department member administration gets its own scoped route later.
    rows = db.execute(select(User, Membership).join(Membership, Membership.user_id == User.id)
                      .where(Membership.organization_id == org_id).order_by(User.name).limit(100))
    return [{"id": m.id, "name": u.name, "email": u.email, "role": m.role} for u, m in rows]


@app.get("/api/v1/organizations/{org_id}/departments")
def departments(org_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    p = principal(db, user, org_id)
    query = select(Department).where(Department.organization_id == org_id)
    if p.role not in {"owner", "admin"}:
        query = query.where(Department.id.in_(p.departments))
    return [{"id": d.id, "name": d.name} for d in db.scalars(query.order_by(Department.name).limit(100))]


@app.post("/api/v1/organizations/{org_id}/departments", status_code=201, dependencies=[Depends(origin_check)])
def create_department(org_id: uuid.UUID, data: Named, user: User = Depends(identity), db: Session = Depends(database)):
    p = principal(db, user, org_id)
    require(p, "departments.manage")
    department = Department(organization_id=org_id, name=data.name)
    db.add(department)
    try:
        db.flush()
        audit(db, user, org_id, "department.created", department.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Department already exists")
    return {"id": department.id, "name": department.name}


@app.get("/api/v1/organizations/{org_id}/presentations")
def presentations(org_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    p = principal(db, user, org_id)
    if p.role == "faculty_lite" and "presentation.read" not in p.lite_permissions:
        raise HTTPException(403, "Permission denied")
    query = presentation_scope(select(Presentation), p).order_by(Presentation.created_at.desc()).limit(100)
    return [{"id": x.id, "title": x.title, "revision": x.revision, "status": x.status} for x in db.scalars(query)]


@app.post("/api/v1/organizations/{org_id}/presentations", status_code=201, dependencies=[Depends(origin_check)])
def create_presentation(org_id: uuid.UUID, data: PresentationInput, user: User = Depends(identity), db: Session = Depends(database)):
    p = principal(db, user, org_id)
    require(p, "presentation.write", owner_id=user.id, department_id=data.department_id)
    if data.department_id:
        dept = db.scalar(select(Department).where(Department.id == data.department_id, Department.organization_id == org_id))
        if not dept or (p.role not in {"owner", "admin"} and dept.id not in p.departments):
            raise HTTPException(404, "Department not found")
    item = Presentation(organization_id=org_id, owner_id=user.id, **data.model_dump())
    db.add(item)
    db.flush()
    audit(db, user, org_id, "presentation.created", item.id)
    db.commit()
    return {"id": item.id, "title": item.title, "revision": item.revision, "status": item.status}


@app.patch("/api/v1/organizations/{org_id}/presentations/{presentation_id}", dependencies=[Depends(origin_check)])
def rename_presentation(org_id: uuid.UUID, presentation_id: uuid.UUID, data: Rename,
                        user: User = Depends(identity), db: Session = Depends(database)):
    p = principal(db, user, org_id)
    item = db.scalar(presentation_scope(select(Presentation).where(Presentation.id == presentation_id), p).with_for_update())
    if not item:
        raise HTTPException(404, "Presentation not found")
    require(p, "presentation.write", owner_id=item.owner_id, department_id=item.department_id)
    if item.revision != data.revision:
        raise HTTPException(409, "Presentation changed; reload before editing")
    item.title = data.title
    item.revision += 1
    audit(db, user, org_id, "presentation.renamed", item.id)
    db.commit()
    return {"id": item.id, "title": item.title, "revision": item.revision, "status": item.status}


from .organization_routes import router as organization_router
app.include_router(organization_router)
from .builder_routes import router as builder_router
app.include_router(builder_router)
from .live_routes import router as live_router
app.include_router(live_router)
from .analytics_routes import router as analytics_router
app.include_router(analytics_router)
from .import_routes import router as import_router
app.include_router(import_router)
from .scheduled_routes import router as scheduled_router
app.include_router(scheduled_router)
from .admin_routes import router as admin_router
app.include_router(admin_router)
from .student_routes import router as student_router
app.include_router(student_router)
from .ai_routes import router as ai_router
app.include_router(ai_router)
