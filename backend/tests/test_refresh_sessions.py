"""Exercise HTTPS cookie transport and persisted token-family invalidation."""
from datetime import datetime, timedelta, timezone
import hashlib
import uuid

import jwt
import pytest

from app.config import settings
from app.models import AuthSession, RefreshToken, User
from conftest import register


@pytest.fixture
def browser(client):
    client.base_url = "https://testserver"
    register(client)
    client.post("/api/auth/logout")
    return client


def login(browser, remember=False, prefix="/api/auth"):
    response = browser.post(f"{prefix}/login", json={
        "email": "owner@example.com", "password": "Strong-password-123", "remember_me": remember})
    assert response.status_code == 200, response.text
    return response


def claims(token):
    return jwt.decode(token, settings().jwt_secret, algorithms=["HS256"],
                      audience="quizeee-web", issuer="quizeee")


def set_refresh(browser, token):
    browser.cookies.clear()
    browser.cookies.set("refresh_token", token, domain="testserver.local", path="/")


@pytest.mark.parametrize("remember", [False, True])
def test_login_lifetimes_cookie_flags_and_hash_storage(browser, store, remember):
    response = login(browser, remember)
    payload = response.json()
    token = claims(payload["access_token"])
    assert token["exp"] - token["iat"] == 86400
    assert payload["expires_in"] == 86400 and payload["token_type"] == "bearer"
    cookie = next(c for c in response.headers.get_list("set-cookie") if c.startswith("refresh_token="))
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert ("Max-Age=" in cookie) is remember
    assert "refresh_token" not in payload
    raw = browser.cookies.get("refresh_token")
    with store() as db:
        record = db.get(RefreshToken, hashlib.sha256(raw.encode()).hexdigest())
        session = db.get(AuthSession, record.session_id)
        assert session.remember_me is remember
        assert session.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(days=29)
    browser.cookies.clear()
    assert browser.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"}).status_code == 200


@pytest.mark.parametrize("prefix", ["/api/auth", "/api/v1/auth"])
def test_rotation_replay_revokes_entire_family_but_not_other_login(browser, store, prefix):
    first = login(browser, prefix=prefix).json()["access_token"]
    stolen = browser.cookies.get("refresh_token")
    rotated = browser.post(f"{prefix}/refresh")
    assert rotated.status_code == 200
    current = browser.cookies.get("refresh_token")
    assert current != stolen
    assert rotated.json()["access_token"] != first
    other = login(browser).json()["access_token"]
    set_refresh(browser, stolen)
    assert browser.post(f"{prefix}/refresh").status_code == 401
    set_refresh(browser, current)
    assert browser.post(f"{prefix}/refresh").status_code == 401
    for token in (first, rotated.json()["access_token"]):
        assert browser.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert browser.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {other}"}).status_code == 200


@pytest.mark.parametrize("remember", [False, True])
def test_refresh_preserves_persistence_and_absolute_expiry(browser, store, remember):
    token = claims(login(browser, remember).json()["access_token"])
    with store() as db:
        session = db.get(AuthSession, uuid.UUID(token["sid"]))
        expiry = datetime.now(timezone.utc) + timedelta(seconds=120)
        session.expires_at = expiry
        db.commit()
    browser.cookies.delete("quizeee_access")
    response = browser.post("/api/auth/refresh")
    assert response.status_code == 200
    assert 0 < response.json()["expires_in"] <= 120
    cookie = next(c for c in response.headers.get_list("set-cookie") if c.startswith("refresh_token="))
    assert ("Max-Age=" in cookie) is remember
    with store() as db:
        assert db.get(AuthSession, uuid.UUID(token["sid"])).expires_at == expiry.replace(tzinfo=None)


def test_logout_with_only_refresh_revokes_access_and_is_idempotent(browser):
    token = login(browser).json()["access_token"]
    raw = browser.cookies.get("refresh_token")
    browser.cookies.delete("quizeee_access")
    response = browser.post("/api/auth/logout")
    assert response.status_code == 200
    assert not browser.cookies.get("refresh_token")
    assert browser.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    set_refresh(browser, raw)
    assert browser.post("/api/auth/refresh").status_code == 401
    assert browser.post("/api/auth/logout").status_code == 200


@pytest.mark.parametrize("failure", ["expired", "disabled", "revoked"])
def test_refresh_checks_server_state(browser, store, failure):
    token = claims(login(browser).json()["access_token"])
    with store() as db:
        session = db.get(AuthSession, uuid.UUID(token["sid"]))
        if failure == "expired":
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif failure == "revoked":
            session.revoked = True
        else:
            db.get(User, session.user_id).active = False
        db.commit()
    assert browser.post("/api/auth/refresh").status_code == 401
    assert not browser.cookies.get("refresh_token")


def test_forged_refresh_does_not_revoke_valid_session(browser):
    token = login(browser).json()["access_token"]
    set_refresh(browser, "forged")
    assert browser.post("/api/auth/refresh").status_code == 401
    assert browser.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


@pytest.mark.parametrize("endpoint", ["login", "refresh", "logout"])
def test_untrusted_origin_cannot_change_session(browser, endpoint):
    login(browser)
    assert browser.post(f"/api/auth/{endpoint}", headers={"origin": "https://evil.example"}, json={}).status_code == 403
    assert browser.post("/api/auth/refresh").status_code == 200


def test_missing_refresh_and_strict_boolean(browser):
    browser.cookies.clear()
    assert browser.post("/api/auth/refresh").status_code == 401
    assert browser.post("/api/auth/login", json={"email":"owner@example.com",
        "password":"Strong-password-123", "remember_me":"false"}).status_code == 422


def test_teacher_refresh_also_issues_24_hour_token(browser):
    login(browser)
    response = browser.post('/api/auth/refresh')
    assert response.status_code == 200
    token = claims(response.json()['access_token'])
    assert token['exp'] - token['iat'] == 86400
    cookie = next(c for c in response.headers.get_list('set-cookie') if c.startswith('quizeee_access='))
    assert 'Max-Age=86400' in cookie


def test_student_access_remains_short_lived(browser):
    response = browser.post('/api/v1/auth/register', json={
        'email':'student-token@example.com','password':'Strong-password-123',
        'name':'Student','profession':'student'})
    assert response.status_code == 201
    token = claims(response.json()['access_token'])
    assert token['exp'] - token['iat'] == 900
