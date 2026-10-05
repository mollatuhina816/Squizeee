import os
os.environ["JWT_SECRET"] = "test-only-" + "x" * 48
os.environ["DATABASE_URL"] = "sqlite://"
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, database
from app.main import app


@pytest.fixture
def store():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def client(store, monkeypatch):
    def override():
        with store() as db:
            yield db
    app.dependency_overrides[database] = override
    monkeypatch.setattr("app.main.rate_limit", lambda *args, **kwargs: None)
    with TestClient(app, headers={"origin": "http://localhost:3000"}) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, email="owner@example.com"):
    result = client.post("/api/v1/auth/register", json={"email": email, "password": "Strong-password-123", "name": "Test Owner", "organization": "Test College"})
    assert result.status_code == 201, result.text
    return result.json()
