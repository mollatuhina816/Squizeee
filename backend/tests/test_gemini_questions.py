import asyncio
import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app import ai_question_generator as generator
from app.ai_question_generator import AIGenerationError, GenerationOptions
from test_ai_questions import QUESTION


def setup_gemini(monkeypatch, handler, key="gemini-test-secret"):
    monkeypatch.setattr(generator, "settings", lambda: SimpleNamespace(
        ai_provider="gemini", gemini_api_key=SecretStr(key),
        gemini_question_model="gemini-2.5-flash-lite",
        ai_request_timeout_seconds=10, ai_max_output_tokens=1000,
    ))
    client_class = httpx.AsyncClient
    monkeypatch.setattr(generator.httpx, "AsyncClient",
                        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(generator, "AsyncOpenAI", lambda **kwargs: pytest.fail("Gemini must never fall back to OpenAI"))


def generate(**source):
    return asyncio.run(generator.generate_questions(
        GenerationOptions(question_count=1, question_type="mcq", difficulty="medium"),
        **source,
    ))


def test_gemini_retries_invalid_json_and_returns_canonical_question(monkeypatch):
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        assert request.headers["x-goog-api-key"] == "gemini-test-secret"
        assert "key=" not in str(request.url)
        output = "not json" if len(calls) == 1 else json.dumps({"questions": [QUESTION]})
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": output}]}}]})
    setup_gemini(monkeypatch, handler)
    result = generate(source_type="topic", content="Human heart")
    assert result[0]["question"]["correct_answers"] == ["Left ventricle"]
    assert result[0]["question"]["duration_seconds"] == 30
    assert len(calls) == 2
    assert calls[0]["generationConfig"]["responseJsonSchema"] == generator.OUTPUT_SCHEMA
    assert "previous result failed" in calls[1]["systemInstruction"]["parts"][0]["text"]


def test_gemini_image_uses_inline_data(monkeypatch):
    def handler(request):
        parts = json.loads(request.content)["contents"][0]["parts"]
        assert parts[1]["inlineData"] == {"mimeType": "image/png", "data": base64.b64encode(b"image-bytes").decode()}
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps({"questions": [QUESTION]})}]}}]})
    setup_gemini(monkeypatch, handler)
    assert len(generate(source_type="image", image=b"image-bytes", mime_type="image/png")) == 1


@pytest.mark.parametrize("status,reason,expected", [
    (400, "API_KEY_INVALID", "authentication"),
    (401, None, "authentication"),
    (403, None, "permission"),
    (429, None, "rate_limit"),
    (404, None, "model_unavailable"),
    (400, None, "provider_request"),
    (503, None, "unavailable"),
])
def test_gemini_errors_are_actionable_and_hide_provider_messages(monkeypatch, status, reason, expected):
    calls = []
    def handler(request):
        calls.append(True)
        return httpx.Response(status, json={"error": {"message": "gemini-test-secret", "details": [{"reason": reason}]}})
    setup_gemini(monkeypatch, handler)
    with pytest.raises(AIGenerationError) as error:
        generate(source_type="topic", content="Human heart")
    assert error.value.code == expected
    assert "gemini-test-secret" not in str(error.value)
    assert len(calls) == 1


def test_gemini_missing_key_never_calls_provider(monkeypatch):
    setup_gemini(monkeypatch, lambda request: pytest.fail("Must not send requests"), key="")
    with pytest.raises(AIGenerationError, match="GEMINI_API_KEY"):
        generate(source_type="topic", content="Human heart")


def test_gemini_timeout_is_sanitized(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("gemini-test-secret", request=request)
    setup_gemini(monkeypatch, handler)
    with pytest.raises(AIGenerationError) as error:
        generate(source_type="topic", content="Human heart")
    assert error.value.code == "timeout"
    assert "gemini-test-secret" not in str(error.value)


@pytest.mark.parametrize("payload,expected", [
    ({"candidates": []}, "no_content"),
    ({"candidates": [{"finishReason": "SAFETY"}]}, "no_content"),
    ({"candidates": [{"content": {"parts": [{"text": "invalid"}]}}]}, "invalid_response"),
])
def test_gemini_empty_blocked_or_invalid_output(monkeypatch, payload, expected):
    setup_gemini(monkeypatch, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(AIGenerationError) as error:
        generate(source_type="topic", content="Human heart")
    assert error.value.code == expected
