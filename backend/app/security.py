import hashlib
import uuid
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, Request, Response
from pwdlib import PasswordHash
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session
from .config import settings
from .db import database
from .models import AuthSession, User

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


def issue_session(db: Session, user: User, response: Response):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings().access_minutes)
    session = AuthSession(user_id=user.id, expires_at=expires)
    db.add(session)
    db.flush()
    token = jwt.encode({"sub": str(user.id), "sid": str(session.id), "iat": now, "exp": expires,
                        "iss": "quizeee", "aud": "quizeee-web", "type": "access"}, settings().jwt_secret, algorithm="HS256")
    response.set_cookie("quizeee_access", token, httponly=True, secure=settings().environment == "production",
                        samesite="strict", max_age=settings().access_minutes * 60, path="/")


def identity(request: Request, db: Session = Depends(database)) -> User:
    token = request.cookies.get("quizeee_access")
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
