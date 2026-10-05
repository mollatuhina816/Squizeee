from datetime import datetime, timedelta, timezone
import uuid
import json
from app.models import LiveSession
from app.questions import Question, evaluate
from app.live_routes import notify as broadcast_snapshot
from app.security import cache
from conftest import register
import pytest

QUESTION = {"kind": "mcq", "title": "Which is prime?", "options": ["2", "4"], "correct_answers": ["2"], "marks": "2", "negative_marks": "0.5", "speed_bonus": "1", "duration_seconds": 30}


def test_scoring_and_public_projection():
    q = Question(**QUESTION)
    assert evaluate(q, {"answer": "2"}, 15000) == (True, 2500)
    assert evaluate(q, {"answer": "4"}, 1000) == (False, -500)
    assert "correct_answers" not in q.public()
    assert "explanation" not in q.public()
    with pytest.raises(ValueError):
        evaluate(q, {"answer": "9"}, 0)


def test_exact_set_and_no_client_score():
    q = Question(kind="multiple_select", title="Select both", options=["A", "B", "C"], correct_answers=["A", "B"])
    assert evaluate(q, {"answer": ["B", "A"]}, 0)[0] is True
    assert evaluate(q, {"answer": ["A"]}, 0)[0] is False
    with pytest.raises(ValueError):
        evaluate(q, {"answer": ["A", "B"], "score": 999}, 0)
    with pytest.raises(ValueError):
        evaluate(q, {"answer": ["A", "A"]}, 0)


def setup_session(client, monkeypatch):
    monkeypatch.setattr("app.live_routes.notify", lambda *args: None)
    monkeypatch.setattr("app.live_routes.rate_limit", lambda *args: None)
    account = register(client)
    base = f"/api/v1/organizations/{account['organization_id']}/presentations"
    p = client.post(base, json={"title": "Math"}).json()
    saved = client.put(f"{base}/{p['id']}/slides", json={"revision": 1, "questions": [QUESTION]})
    assert saved.status_code == 200, saved.text
    session = client.post(f"{base}/{p['id']}/sessions").json()
    return session, base, p


def test_live_flow_snapshot_duplicate_and_ended_code(client, monkeypatch):
    session, base, p = setup_session(client, monkeypatch)
    sid = session["id"]
    joined = client.post("/api/v1/sessions/join", json={"code": session["join_code"], "name": "Student", "phone": "+919000000001", "email": "student@example.com"})
    assert joined.status_code == 201, joined.text
    token = {"X-Participant-Token": joined.json()["token"]}
    assert client.post(f"/api/v1/sessions/{sid}/responses", headers=token, json={"question_index": 0, "answer": "2"}).status_code == 409
    assert client.post(f"/api/v1/sessions/{sid}/control", json={"action": "open", "revision": 1}).status_code == 200
    snapshot = client.get(f"/api/v1/sessions/{sid}/participant", headers=token).json()
    assert snapshot["question"]["title"] == QUESTION["title"]
    assert "correct_answers" not in snapshot["question"]
    assert snapshot["leaderboard"][0]["nickname"] == "Student"
    answer = {"question_index": 0, "answer": "2"}
    assert client.post(f"/api/v1/sessions/{sid}/responses", headers=token, json=answer).status_code == 201
    assert client.post(f"/api/v1/sessions/{sid}/responses", headers=token, json=answer).status_code == 409
    host = client.get(f"/api/v1/sessions/{sid}/host").json()
    assert host["participant_count"] == 1
    assert host["leaderboard"][0]["score"] >= 2000
    assert client.post(f"/api/v1/sessions/{sid}/control", json={"action": "end", "revision": 2}).status_code == 200
    assert client.post("/api/v1/sessions/join", json={"code": session["join_code"], "name": "Late", "phone": "+919000000002", "email": "late@example.com"}).status_code == 404


def test_start_broadcasts_and_manual_next_is_disabled(client, monkeypatch, store):
    session, _, _ = setup_session(client, monkeypatch)
    sid = session["id"]
    with store() as db:
        live = db.get(LiveSession, uuid.UUID(sid))
        live.questions = [QUESTION, {**QUESTION, "title": "Second question"}]
        db.commit()

    published = []
    monkeypatch.setattr("app.live_routes.notify", broadcast_snapshot)
    monkeypatch.setattr(cache, "setex", lambda *args: None)
    monkeypatch.setattr(cache, "publish", lambda channel, payload: published.append((channel, payload)))

    opened = client.post(f"/api/v1/sessions/{sid}/control", json={"action": "open", "revision": 1})
    assert opened.status_code == 200
    advanced = client.post(f"/api/v1/sessions/{sid}/control", json={"action": "next", "revision": 2})
    assert advanced.status_code == 409

    channel, raw_payload = published[0]
    event = json.loads(raw_payload)
    assert channel == f"live:{sid}"
    assert event["type"] == "snapshot.changed"
    assert event["snapshot"]["active_index"] == 0
    assert event["snapshot"]["question"]["title"] == QUESTION["title"]
    assert "correct_answers" not in event["snapshot"]["question"]


def test_late_response_and_editor_changes_dont_mutate_session(client, monkeypatch, store):
    session, base, p = setup_session(client, monkeypatch)
    sid = session["id"]
    altered = {**QUESTION, "title": "New title"}
    assert client.put(f"{base}/{p['id']}/slides", json={"revision": 2, "questions": [altered]}).status_code == 200
    token = client.post("/api/v1/sessions/join", json={"code": session["join_code"], "name": "S", "phone": "+919000000001", "email": "student@example.com"}).json()["token"]
    client.post(f"/api/v1/sessions/{sid}/control", json={"action": "open", "revision": 1})
    with store() as db:
        live = db.get(LiveSession, uuid.UUID(sid))
        assert live.questions[0]["title"] == QUESTION["title"]
        live.opened_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        from app.models import Participant
        from sqlalchemy import select
        participant = db.scalar(select(Participant).where(Participant.session_id == live.id))
        participant.created_at = live.opened_at
        db.commit()
    assert client.post(f"/api/v1/sessions/{sid}/responses", headers={"X-Participant-Token": token}, json={"question_index": 0, "answer": "2"}).status_code == 409


def test_participant_cannot_control_and_other_tenant_cannot_observe(client, monkeypatch):
    session, _, _ = setup_session(client, monkeypatch)
    sid = session["id"]
    client.cookies.clear()
    assert client.post(f"/api/v1/sessions/{sid}/control", json={"action": "open", "revision": 1}).status_code == 401
    register(client, "outsider@example.com")
    assert client.get(f"/api/v1/sessions/{sid}/host").status_code == 404
    assert client.get(f"/api/v1/sessions/{sid}/participant", headers={"X-Participant-Token": "forged"}).status_code == 401
