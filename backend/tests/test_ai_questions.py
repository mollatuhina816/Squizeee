import asyncio
import json
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from openai import APIStatusError, APITimeoutError
from PIL import Image
from pydantic import SecretStr, ValidationError

from app import ai_question_generator, ai_routes
from app.ai_question_generator import (
    AIGenerationError,
    GeneratedQuestion,
    GenerationOptions,
    _to_platform_questions,
)
from conftest import register


QUESTION = {
    "kind": "mcq",
    "title": "Which chamber pumps oxygenated blood to the body?",
    "body": "",
    "options": ["Left ventricle", "Right atrium", "Right ventricle", "Left atrium"],
    "correct_answers": ["Left ventricle"],
    "explanation": "The left ventricle pumps oxygenated blood into the aorta.",
    "difficulty": "medium",
}


def options(**overrides):
    values = {"question_count": 1, "question_type": "mcq", "difficulty": "medium"}
    values.update(overrides)
    return GenerationOptions(**values)


def configure_generation(monkeypatch, fake_generate=None):
    monkeypatch.setattr(ai_routes, "settings", lambda: SimpleNamespace(
        ai_provider="openai", openai_api_key=SecretStr("test-key"), openai_question_model="test-model",
        ai_max_questions_per_request=20, ai_max_text_length=20000,
        ai_max_image_size_mb=10,
    ))
    monkeypatch.setattr(ai_routes, "reserve_generation", lambda *args: None)
    async def default_generate(*args, **kwargs):
        return [{"question": {key: value for key, value in QUESTION.items() if key != "difficulty"}, "difficulty": "medium"}]
    monkeypatch.setattr(ai_routes, "generate_questions", fake_generate or default_generate)


def test_generated_mcq_converts_to_canonical_question():
    raw = json.dumps({"questions": [QUESTION]})
    result = _to_platform_questions(raw, options())
    assert result[0]["question"]["correct_answers"] == ["Left ventricle"]
    assert result[0]["question"]["duration_seconds"] == 30
    assert result[0]["difficulty"] == "medium"


def test_invalid_model_question_is_rejected():
    invalid = {**QUESTION, "correct_answers": ["not an option"]}
    with pytest.raises(ValidationError):
        GeneratedQuestion.model_validate(invalid)
    with pytest.raises(AIGenerationError, match="No usable educational content"):
        _to_platform_questions('{"questions": []}', options())


def test_generation_count_is_bounded():
    with pytest.raises(ValidationError):
        options(question_count=0)
    with pytest.raises(ValidationError):
        options(question_count=21)


def test_redis_quota_uses_role_limits_and_returns_retry_after(monkeypatch):
    monkeypatch.setattr(ai_routes, "settings", lambda: SimpleNamespace(
        ai_daily_limit_admin=100, ai_daily_limit_faculty=50,
        ai_daily_limit_faculty_lite=10, ai_requests_per_minute=5,
    ))
    calls = []
    monkeypatch.setattr(ai_routes.cache, "eval", lambda *args: calls.append(args) or 2)
    user = SimpleNamespace(id=uuid4())
    with pytest.raises(HTTPException) as error:
        ai_routes.reserve_generation(uuid4(), user, "faculty_lite")
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "60"
    assert calls[0][4:6] == (10, 5)


def test_openai_structured_output_retries_invalid_response(monkeypatch):
    valid_output = json.dumps({"questions": [QUESTION]})
    calls = []

    class FakeClient:
        def __init__(self):
            self.responses = self

        async def create(self, **kwargs):
            calls.append(kwargs)
            output_text = "not json" if len(calls) == 1 else valid_output
            return SimpleNamespace(output_text=output_text)

        async def close(self):
            return None

    client = FakeClient()
    monkeypatch.setattr(ai_question_generator, "settings", lambda: SimpleNamespace(
        ai_provider="openai", openai_api_key=SecretStr("test-key"), openai_question_model="test-model",
        ai_request_timeout_seconds=10, ai_max_output_tokens=1000,
    ))
    monkeypatch.setattr(ai_question_generator, "AsyncOpenAI", lambda **kwargs: client)
    generated = asyncio.run(ai_question_generator.generate_questions(
        options(), source_type="topic", content="Human heart",
    ))
    assert len(calls) == 2
    assert calls[0]["text"]["format"]["strict"] is True
    assert generated[0]["question"]["title"] == QUESTION["title"]


def test_openai_timeout_is_sanitized(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.responses = self

        async def create(self, **kwargs):
            raise APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))

        async def close(self):
            return None

    monkeypatch.setattr(ai_question_generator, "settings", lambda: SimpleNamespace(
        ai_provider="openai", openai_api_key=SecretStr("not-for-logs"), openai_question_model="test-model",
        ai_request_timeout_seconds=1, ai_max_output_tokens=1000,
    ))
    monkeypatch.setattr(ai_question_generator, "AsyncOpenAI", lambda **kwargs: FakeClient())
    with pytest.raises(AIGenerationError, match="timed out") as error:
        asyncio.run(ai_question_generator.generate_questions(options(), source_type="topic", content="Heart"))
    assert "not-for-logs" not in str(error.value)


@pytest.mark.parametrize("status,provider_code,expected", [
    (401, "invalid_api_key", "authentication"),
    (403, None, "permission"),
    (429, "insufficient_quota", "quota"),
    (429, "credit_balance_exhausted", "quota"),
    (429, "project_spend_limit_exceeded", "quota"),
    (429, "rate_limit_exceeded", "rate_limit"),
    (404, "model_not_found", "model_unavailable"),
    (400, None, "provider_request"),
    (500, None, "unavailable"),
])
def test_provider_errors_explain_recovery_without_leaking_secrets(status, provider_code, expected):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    error = APIStatusError("secret-provider-message", response=response,
                           body={"error": {"code": provider_code, "message": "secret-provider-message"}})
    failure = ai_question_generator._provider_error(error)
    assert failure.code == expected
    assert "secret-provider-message" not in failure.detail


def test_generation_requires_authentication(client):
    account = register(client)
    client.cookies.clear()
    response = client.post(
        f"/api/v1/organizations/{account['organization_id']}/ai/generate-questions",
        json={"source_type": "topic", "content": "Human heart", **options().model_dump()},
    )
    assert response.status_code == 401


def test_generation_preview_saves_via_question_bank_batch(client, monkeypatch):
    account = register(client)
    configure_generation(monkeypatch)
    org = account["organization_id"]
    response = client.post(f"/api/v1/organizations/{org}/ai/generate-questions", json={
        "source_type": "text",
        "content": "The left ventricle pumps oxygenated blood into the aorta.",
        **options().model_dump(),
    })
    assert response.status_code == 200, response.text
    generated = response.json()["questions"]
    assert generated[0]["question"]["title"] == QUESTION["title"]

    saved = client.post(f"/api/v1/organizations/{org}/bank/questions/bulk", json={"items": [{
        "question": generated[0]["question"], "subject": "Biology", "topic": "Human heart", "difficulty": generated[0]["difficulty"],
    }]})
    assert saved.status_code == 201, saved.text
    bank = client.get(f"/api/v1/organizations/{org}/bank/questions").json()
    assert any(item["question"]["title"] == QUESTION["title"] for item in bank)


def test_generation_limit_is_returned_before_model_call(client, monkeypatch):
    account = register(client)
    calls = []
    async def fake_generate(*args, **kwargs):
        calls.append(True)
        return []
    configure_generation(monkeypatch, fake_generate)
    monkeypatch.setattr(ai_routes, "reserve_generation", lambda *args: (_ for _ in ()).throw(HTTPException(429, "limit reached")))
    response = client.post(f"/api/v1/organizations/{account['organization_id']}/ai/generate-questions", json={
        "source_type": "topic", "content": "Human heart", **options().model_dump(),
    })
    assert response.status_code == 429
    assert calls == []


def test_image_upload_checks_actual_signature(client, monkeypatch):
    account = register(client)
    configure_generation(monkeypatch)
    response = client.post(
        f"/api/v1/organizations/{account['organization_id']}/ai/generate-questions/image",
        data={"options_json": json.dumps(options().model_dump())},
        files={"image": ("page.png", b"not really a png", "image/png")},
    )
    assert response.status_code == 415
    assert response.json()["detail"] == "The uploaded file does not match its image type."


def test_valid_image_upload_returns_preview(client, monkeypatch):
    account = register(client)
    captured = {}
    async def fake_generate(settings, **kwargs):
        captured.update(kwargs)
        return [{"question": {key: value for key, value in QUESTION.items() if key != "difficulty"}, "difficulty": "medium"}]
    configure_generation(monkeypatch, fake_generate)
    image_buffer = BytesIO()
    Image.new("RGB", (1, 1), "white").save(image_buffer, format="PNG")
    png = image_buffer.getvalue()
    response = client.post(
        f"/api/v1/organizations/{account['organization_id']}/ai/generate-questions/image",
        data={"options_json": json.dumps(options().model_dump())},
        files={"image": ("page.png", png, "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["generated_count"] == 1
    assert captured["mime_type"] == "image/png"
    assert captured["image"] == png


@pytest.mark.parametrize("extension", ["txt", "pdf", "pptx"])
def test_topic_document_generates_from_lesson_without_answer_key(client, monkeypatch, extension):
    account = register(client)
    captured = {}
    lesson = "The left ventricle pumps oxygenated blood into the aorta."
    async def fake_generate(settings, **kwargs):
        captured.update(kwargs)
        return [{"question": {key: value for key, value in QUESTION.items() if key != "difficulty"}, "difficulty": "medium"}]
    configure_generation(monkeypatch, fake_generate)
    buffer = BytesIO()
    if extension == "pdf":
        from reportlab.pdfgen.canvas import Canvas
        canvas = Canvas(buffer)
        canvas.drawString(40, 700, lesson)
        canvas.save()
        raw = buffer.getvalue()
    elif extension == "pptx":
        from pptx import Presentation
        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.shapes.title.text = "Human heart"
        slide.placeholders[1].text = lesson
        deck.save(buffer)
        raw = buffer.getvalue()
    else:
        raw = lesson.encode("utf-8")
    response = client.post(
        f"/api/v1/organizations/{account['organization_id']}/ai/generate-questions/document",
        data={"options_json": json.dumps(options().model_dump())},
        files={"document": (f"lesson.{extension}", raw, "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["generated_count"] == 1
    assert captured["source_type"] == "text"
    assert lesson in captured["content"]


@pytest.mark.parametrize("filename,raw,status", [
    ("lesson.txt", b"   ", 422),
    ("lesson.pdf", b"not a pdf", 422),
    ("lesson.pptx", b"not a zip", 422),
    ("lesson.txt", b"\xff", 422),
    ("lesson.txt", b"a" * 20001, 422),
    ("lesson.txt", b"a" * 2000001, 413),
    ("lesson.doc", b"lesson", 415),
], ids=["empty", "invalid-pdf", "invalid-pptx", "invalid-encoding", "text-limit", "file-limit", "unsupported"])
def test_invalid_topic_document_never_calls_ai(client, monkeypatch, filename, raw, status):
    account = register(client)
    async def unexpected_generation(*args, **kwargs):
        pytest.fail("Invalid documents must not call AI")
    configure_generation(monkeypatch, unexpected_generation)
    response = client.post(
        f"/api/v1/organizations/{account['organization_id']}/ai/generate-questions/document",
        data={"options_json": json.dumps(options().model_dump())},
        files={"document": (filename, raw, "application/octet-stream")},
    )
    assert response.status_code == status, response.text
