"""Opt-in real PostgreSQL locking checks, isolated in a disposable schema."""
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import uuid

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db import Base
from app.models import AuthSession, RefreshToken, User
from app.security import issue_session, refresh_session, revoke_session, rotate_session


@pytest.fixture
def postgres_store():
    url = os.environ.get("QUIZEEE_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set QUIZEEE_TEST_POSTGRES_URL for PostgreSQL concurrency checks")
    engine = create_engine(url)
    schema = "auth_test_" + uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    scoped = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(scoped)
        yield sessionmaker(scoped, expire_on_commit=False)
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def request(token):
    return Request({"type":"http", "headers":[(b"cookie", f"refresh_token={token}".encode())]})


def session_token(factory):
    with factory() as db:
        user = User(name="Concurrency test", email="race@example.com", password_hash="unused")
        db.add(user)
        db.flush()
        response = Response()
        issue_session(db, user, response, True)
        db.commit()
        cookie = next(value for value in response.headers.getlist("set-cookie") if value.startswith("refresh_token="))
        token = cookie.split(";", 1)[0].split("=", 1)[1]
        return token, db.scalar(select(AuthSession.id))


def test_simultaneous_refresh_reuse_revokes_winning_token(postgres_store):
    raw, sid = session_token(postgres_store)
    barrier = threading.Barrier(2)

    def refresh():
        with postgres_store() as db:
            barrier.wait(timeout=10)
            try:
                return rotate_session(db, request(raw), Response())
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: refresh(), range(2)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert 401 in results
    with postgres_store() as db:
        assert db.get(AuthSession, sid).revoked
        assert len(list(db.scalars(select(RefreshToken)))) == 2


def test_logout_waits_for_rotation_then_revokes_family(postgres_store):
    raw, sid = session_token(postgres_store)
    started = threading.Event()

    def logout():
        with postgres_store() as db:
            started.set()
            revoke_session(db, request(raw))

    with postgres_store() as db, ThreadPoolExecutor(max_workers=1) as pool:
        # Hold the family lock before logout arrives; commit a rotation, then
        # verify logout invalidates the replacement rather than losing the race.
        refresh_session(db, raw)
        pending = pool.submit(logout)
        assert started.wait(10)
        rotate_session(db, request(raw), Response())
        pending.result(timeout=10)
    with postgres_store() as db:
        assert db.get(AuthSession, sid).revoked
