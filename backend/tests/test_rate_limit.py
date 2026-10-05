import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError
from app.security import rate_limit


def test_rate_limit_rejects_threshold(monkeypatch):
    monkeypatch.setattr("app.security.cache.eval", lambda *args: 16)
    with pytest.raises(HTTPException) as e:
        rate_limit("login")
    assert e.value.status_code == 429


def test_rate_limit_fails_closed(monkeypatch):
    def unavailable(*args):
        raise ConnectionError()
    monkeypatch.setattr("app.security.cache.eval", unavailable)
    with pytest.raises(HTTPException) as e:
        rate_limit("login")
    assert e.value.status_code == 503
