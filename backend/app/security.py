import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, Request, Response
from pwdlib import PasswordHash
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .db import database
from .models import AuditEvent, AuthSession, RefreshToken, User

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash("timing-equalizer-not-an-account-password")
cache = Redis.from_url(settings().redis_url, decode_responses=True)
RATE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


def rate_limit(key: str, limit: int = 15, seconds: int = 60):
    digest = hashlib.sha256(key.encode()).hexdigest()
    try:
        count = cache.eval(RATE_SCRIPT, 1, f"rate:{digest}", seconds)
    except RedisError:
        raise HTTPException(503, "Authentication temporarily unavailable")
    if count > limit:
        raise HTTPException(429, "Too many attempts; try again later", headers={"Retry-After": str(seconds)})


def origin_check(request: Request):
    if request.headers.get("origin") != settings().app_origin:
        raise HTTPException(403, "Untrusted request origin")


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def access_token(session: AuthSession, response: Response, user: User):
    now = datetime.now(timezone.utc)
    lifetime = (timedelta(hours=settings().teacher_access_hours) if user.profession == 'teacher'
                else timedelta(minutes=settings().access_minutes))
    expires = min(now + lifetime, utc(session.expires_at))
    token = jwt.encode({"sub": str(session.user_id), "sid": str(session.id), "iat": now, "exp": expires,
                        "jti": str(uuid.uuid4()),
                        "iss": "quizeee", "aud": "quizeee-web", "type": "access"}, settings().jwt_secret, algorithm="HS256")
    response.delete_cookie("quizeee_profile", path="/", samesite="strict", secure=settings().environment == "production")
    response.set_cookie("quizeee_access", token, httponly=True, secure=settings().environment == "production",
                        samesite="strict", max_age=max(0, int((expires - now).total_seconds())), path="/")
    return {"access_token": token, "token_type": "bearer", "expires_in": max(0, int((expires - now).total_seconds()))}


def issue_refresh(db: Session, session: AuthSession, response: Response):
    # A random bearer secret is never stored in plaintext or exposed in JSON.
    token = secrets.token_urlsafe(32)
    db.add(RefreshToken(token_hash=hashlib.sha256(token.encode()).hexdigest(), session_id=session.id))
    remaining = max(0, int((utc(session.expires_at) - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie("refresh_token", token, httponly=True, secure=True, samesite="lax", path="/",
                        max_age=remaining if session.remember_me else None)


def issue_session(db: Session, user: User, response: Response, remember_me: bool = False):
    session = AuthSession(user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                          remember_me=remember_me)
    db.add(session)
    db.flush()
    issue_refresh(db, session, response)
    return access_token(session, response, user)


def refresh_session(db: Session, token: str | None):
    if not token or len(token) > 128:
        return None, None
    record = db.get(RefreshToken, hashlib.sha256(token.encode()).hexdigest())
    if not record:
        return None, None
    # Serialize rotation and logout across every worker using this token family.
    session = db.scalar(select(AuthSession).where(AuthSession.id == record.session_id).with_for_update())
    if session:
        db.refresh(record)
    return session, record


def rotate_session(db: Session, request: Request, response: Response):
    session, record = refresh_session(db, request.cookies.get("refresh_token"))
    if not session or session.revoked or utc(session.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(401, "Please sign in")
    user = db.get(User, session.user_id)
    if record.consumed or not user or not user.active:
        session.revoked = True
        db.add(AuditEvent(actor_id=session.user_id, action="auth.refresh_reuse" if record.consumed else "auth.disabled",
                          resource_id=str(session.id)))
        # Commit even though the request fails; a rollback would undo revocation.
        db.commit()
        raise HTTPException(401, "Session invalidated; please sign in")
    record.consumed = True
    issue_refresh(db, session, response)
    result = access_token(session, response, user)
    db.commit()
    return result


def clear_auth_cookies(response: Response):
    response.delete_cookie("refresh_token", path="/", httponly=True, samesite="lax", secure=True)
    for name in ("quizeee_access", "quizeee_profile"):
        response.delete_cookie(name, path="/", samesite="strict", secure=settings().environment == "production")


def revoke_session(db: Session, request: Request):
    session, _ = refresh_session(db, request.cookies.get("refresh_token"))
    if not session:
        try:
            identity(request, db)
        except HTTPException as error:
            if error.status_code != 401:
                raise
        else:
            # Use the family lock even for cookie-only legacy sessions.
            session = db.scalar(select(AuthSession).where(
                AuthSession.id == request.state.auth_session.id).with_for_update())
    if session:
        session.revoked = True
        db.add(AuditEvent(actor_id=session.user_id, action="auth.logout", resource_id=str(session.id)))
    db.commit()


def identity(request: Request, db: Session = Depends(database)) -> User:
    authorization = request.headers.get("authorization")
    token = (authorization[7:] if authorization and authorization.lower().startswith("bearer ")
             else request.cookies.get("quizeee_access"))
    try:
        claims = jwt.decode(token or "", settings().jwt_secret, algorithms=["HS256"], audience="quizeee-web",
                            issuer="quizeee", options={"require": ["sub", "sid", "exp", "iat", "type"]})
        if (claims["type"] != "access" or not isinstance(claims["sid"], str)
                or not isinstance(claims["sub"], str)):
            raise ValueError()
        session = db.get(AuthSession, uuid.UUID(claims["sid"]))
        uid = uuid.UUID(claims["sub"])
        if not session or session.revoked or session.user_id != uid:
            raise ValueError()
        expiry = session.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            raise ValueError()
        user = db.get(User, uid)
        if not user or not user.active:
            raise ValueError()
        request.state.auth_session = session
        return user
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(401, "Please sign in")
