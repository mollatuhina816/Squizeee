import logging
import uuid
import zipfile
from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .ai_question_generator import (
    AIGenerationError,
    GenerationOptions,
    GenerationRequest,
    generate_questions,
    provider_configuration,
)
from .config import settings
from .db import database
from .models import User
from .security import cache, identity, origin_check

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/organizations/{org_id}/ai", tags=["AI question generator"])

LIMIT_SCRIPT = """
local daily = tonumber(redis.call('GET', KEYS[1]) or '0')
if daily >= tonumber(ARGV[1]) then return 1 end
local minute = tonumber(redis.call('GET', KEYS[2]) or '0')
if minute >= tonumber(ARGV[2]) then return 2 end
if redis.call('INCR', KEYS[1]) == 1 then redis.call('EXPIRE', KEYS[1], ARGV[3]) end
if redis.call('INCR', KEYS[2]) == 1 then redis.call('EXPIRE', KEYS[2], ARGV[4]) end
return 0
"""

IMAGE_TYPES = {
    "image/jpeg": ({"jpg", "jpeg"}, "JPEG", lambda data: data.startswith(b"\xff\xd8\xff")),
    "image/png": ({"png"}, "PNG", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/webp": ({"webp"}, "WEBP", lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"),
}


def authorize_generation(db: Session, user: User, org_id: uuid.UUID):
    from .main import principal, require
    principal_row = principal(db, user, org_id)
    require(principal_row, "bank.write", owner_id=user.id)
    return principal_row


def _daily_limit(role: str) -> int:
    config = settings()
    if role in {"owner", "admin"}:
        return config.ai_daily_limit_admin
    if role == "faculty_lite":
        return config.ai_daily_limit_faculty_lite
    return config.ai_daily_limit_faculty


def reserve_generation(org_id: uuid.UUID, user: User, role: str):
    now = datetime.now(timezone.utc)
    daily_key = f"ai_usage:{org_id}:{user.id}:{now:%Y-%m-%d}"
    minute_key = f"ai_rate:{org_id}:{user.id}:{now:%Y%m%d%H%M}"
    config = settings()
    try:
        result = cache.eval(LIMIT_SCRIPT, 2, daily_key, minute_key,
                            _daily_limit(role), config.ai_requests_per_minute, 172800, 120)
    except RedisError:
        raise HTTPException(503, "AI usage controls are temporarily unavailable. Please try again.") from None
    if result == 1:
        raise HTTPException(429, "Your daily AI question generation limit has been reached.")
    if result == 2:
        raise HTTPException(429, "Too many AI generation requests. Wait a minute and try again.", headers={"Retry-After": "60"})


def _validate_options(options: GenerationOptions):
    config = settings()
    if options.question_count > config.ai_max_questions_per_request:
        raise HTTPException(422, f"Generate no more than {config.ai_max_questions_per_request} questions at a time.")
    for value in (options.grade_level, options.subject, options.exam_style):
        if len(value) > 120:
            raise HTTPException(422, "Grade, subject, and exam style must be 120 characters or fewer.")
    if any(not question.strip() or len(question) > 500 for question in options.avoid_questions):
        raise HTTPException(422, "Existing question references must contain 1 to 500 characters.")


def _raise_generation_error(error: AIGenerationError):
    status = {
        "no_content": 422,
        "no_new_questions": 422,
        "not_configured": 503,
        "timeout": 504,
        "invalid_response": 502,
        "unavailable": 503,
        "authentication": 503,
        "permission": 503,
        "quota": 503,
        "rate_limit": 429,
        "model_unavailable": 503,
        "provider_request": 502,
    }.get(error.code, 502)
    raise HTTPException(status, error.detail) from None


async def _generate(org_id: uuid.UUID, user: User, role: str, options: GenerationOptions,
                    source_type: str, content: str | None = None,
                    image: bytes | None = None, mime_type: str | None = None):
    config = settings()
    api_key, model, key_name = provider_configuration(config)
    if not api_key:
        raise HTTPException(503, f"AI question generation is not configured. Add {key_name} to the backend environment.")
    _validate_options(options)
    reserve_generation(org_id, user, role)
    try:
        questions = await generate_questions(options, source_type=source_type, content=content,
                                             image=image, mime_type=mime_type)
    except AIGenerationError as error:
        logger.warning("AI question generation failed org_id=%s user_id=%s source=%s code=%s",
                       org_id, user.id, source_type, error.code)
        _raise_generation_error(error)
    logger.info("AI question generation completed org_id=%s user_id=%s source=%s requested=%d generated=%d model=%s",
                org_id, user.id, source_type, options.question_count, len(questions), model)
    return {"questions": questions, "generated_count": len(questions)}


@router.post("/generate-questions", dependencies=[Depends(origin_check)])
async def generate_from_text(org_id: uuid.UUID, data: GenerationRequest,
                             user: User = Depends(identity), db: Session = Depends(database)):
    principal_row = authorize_generation(db, user, org_id)
    config = settings()
    if len(data.content) > config.ai_max_text_length:
        raise HTTPException(422, f"Source text must be {config.ai_max_text_length} characters or fewer.")
    db.rollback()
    return await _generate(org_id, user, principal_row.role, data, data.source_type, data.content)


def _document_content(raw: bytes, extension: str) -> str:
    from .document_import import extract_document_sections

    try:
        if extension == "txt":
            content = raw.decode("utf-8-sig")
            if "\x00" in content:
                raise ValueError("Upload a UTF-8 text file.")
        else:
            if extension == "pdf" and not raw.startswith(b"%PDF-"):
                raise ValueError("Upload a valid PDF file.")
            sections = extract_document_sections(raw, extension)
            content = "\n\n".join(text.strip() for _, text in sections if text.strip())
    except UnicodeDecodeError:
        raise HTTPException(422, "Save the text file with UTF-8 encoding and try again.") from None
    except (ValueError, zipfile.BadZipFile, KeyError, OSError):
        raise HTTPException(422, "Unable to read this document. Upload an unprotected text-based PDF, PPTX, or UTF-8 TXT file (up to 100 pages/slides).") from None
    if not content.strip():
        raise HTTPException(422, "No readable text was found. For scanned pages, use Upload image instead.")
    if len(content) > settings().ai_max_text_length:
        raise HTTPException(422, f"Document text must be {settings().ai_max_text_length} characters or fewer. Upload a shorter lesson or excerpt.")
    return content.strip()


@router.post("/generate-questions/document", dependencies=[Depends(origin_check)])
async def generate_from_document(org_id: uuid.UUID, options_json: str = Form(...),
                                 document: UploadFile = File(...), user: User = Depends(identity),
                                 db: Session = Depends(database)):
    principal_row = authorize_generation(db, user, org_id)
    role = principal_row.role
    try:
        options = GenerationOptions.model_validate_json(options_json)
    except ValidationError:
        raise HTTPException(422, "Invalid document-generation settings.") from None
    _validate_options(options)
    extension = (document.filename or "").rsplit(".", 1)[-1].lower()
    if extension not in {"txt", "pdf", "pptx"}:
        raise HTTPException(415, "Upload a PDF, PPTX, or TXT topic document.")
    raw = await document.read(2_000_001)
    if len(raw) > 2_000_000:
        raise HTTPException(413, "Topic documents must be 2 MB or smaller.")
    db.rollback()
    content = await run_in_threadpool(_document_content, raw, extension)
    return await _generate(org_id, user, role, options, "text", content)


@router.post("/generate-questions/image", dependencies=[Depends(origin_check)])
async def generate_from_image(org_id: uuid.UUID, options_json: str = Form(...),
                              image: UploadFile = File(...), user: User = Depends(identity),
                              db: Session = Depends(database)):
    principal_row = authorize_generation(db, user, org_id)
    try:
        options = GenerationOptions.model_validate_json(options_json)
    except ValidationError:
        raise HTTPException(422, "Invalid image-generation settings.") from None

    content_type = (image.content_type or "").lower()
    image_type = IMAGE_TYPES.get(content_type)
    if not image_type:
        raise HTTPException(415, "Unsupported image. Upload a JPG, PNG, or WEBP file.")
    extension = (image.filename or "").rsplit(".", 1)[-1].lower()
    if extension not in image_type[0]:
        raise HTTPException(415, "The image file extension does not match its MIME type.")
    config = settings()
    raw = await image.read(config.ai_max_image_size_mb * 1024 * 1024 + 1)
    if len(raw) > config.ai_max_image_size_mb * 1024 * 1024:
        raise HTTPException(413, f"Image must be {config.ai_max_image_size_mb} MB or smaller.")
    if not image_type[2](raw):
        raise HTTPException(415, "The uploaded file does not match its image type.")
    try:
        with Image.open(BytesIO(raw)) as decoded:
            if decoded.format != image_type[1]:
                raise HTTPException(415, "The uploaded file does not match its image type.")
            decoded.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(415, "The uploaded image is not readable.") from None

    db.rollback()
    return await _generate(org_id, user, principal_row.role, options, "image",
                           image=raw, mime_type=content_type)
