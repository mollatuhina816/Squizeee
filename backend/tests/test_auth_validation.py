from datetime import datetime, timedelta, timezone
import uuid

import jwt
import pytest

from app.config import settings
from app.models import AuthSession, User
from conftest import register


def claims_for(client):
    return jwt.decode(client.cookies.get("quizeee_access"), settings().jwt_secret,
                      algorithms=["HS256"], audience="quizeee-web", issuer="quizeee")


def set_token(client, claims, key=None):
    client.cookies.clear()
    client.cookies.set("quizeee_access", jwt.encode(claims, key or settings().jwt_secret, algorithm="HS256"))


def test_login_cookie_and_logout(client):
    account = register(client)
    client.post("/api/v1/auth/logout")
    response = client.post("/api/v1/auth/login", json={
        "email": "OWNER@example.com", "password": "Strong-password-123"})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert client.get("/api/v1/auth/me").json()["id"] == account["id"]
    claims = claims_for(client)
    assert client.post("/api/v1/auth/logout").status_code == 200
    set_token(client, claims)
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("field,value", [
    ("exp", 1), ("iat", 9999999999), ("iss", "other"), ("aud", "other"),
    ("type", "refresh"), ("sid", "invalid"), ("sid", 123), ("sid", []),
    ("sub", "invalid"), ("sub", str(uuid.uuid4())), ("sid", str(uuid.uuid4())),
])
def test_invalid_claims_rejected(client, field, value):
    register(client)
    claims = claims_for(client)
    claims[field] = value
    set_token(client, claims)
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("field", ["sub", "sid", "exp", "iat", "type", "iss", "aud"])
def test_missing_claims_rejected(client, field):
    register(client)
    claims = claims_for(client)
    del claims[field]
    set_token(client, claims)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_wrong_signature_and_missing_cookie(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    register(client)
    set_token(client, claims_for(client), "incorrect-signing-key-" + "x" * 32)
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("change", ["expired_session", "disabled_user"])
def test_server_side_validation(client, store, change):
    account = register(client)
    claims = claims_for(client)
    with store() as db:
        if change == "expired_session":
            db.get(AuthSession, uuid.UUID(claims["sid"])).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        else:
            db.get(User, uuid.UUID(account["id"])).active = False
        db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_wrong_password_and_disabled_login(client, store):
    account = register(client)
    client.cookies.clear()
    response = client.post("/api/v1/auth/login", json={
        "email": "owner@example.com", "password": "Wrong-password-123"})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    with store() as db:
        db.get(User, uuid.UUID(account["id"])).active = False
        db.commit()
    response = client.post("/api/v1/auth/login", json={
        "email": "owner@example.com", "password": "Strong-password-123"})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_registration_accepts_six_character_strong_password(client):
    password = "Ab1!xy"
    response = client.post("/api/v1/auth/register", json={
        "email": "short-strong@example.com", "password": password,
        "name": "Short Password", "organization": "Test College",
    })
    assert response.status_code == 201, response.text
    assert client.post("/api/v1/auth/login", json={
        "email": "short-strong@example.com", "password": password,
    }).status_code == 200


@pytest.mark.parametrize("password", ["Ab1!x", "abcdef", "Abcdef!", "ABCDEF1!", "Abcdef1"])
def test_registration_rejects_short_or_weak_passwords(client, password):
    response = client.post("/api/v1/auth/register", json={
        "email": "weak-password@example.com", "password": password,
        "name": "Weak Password", "organization": "Test College",
    })
    assert response.status_code == 422
