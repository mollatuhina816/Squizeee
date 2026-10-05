import base64
import binascii
import csv
import io
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from .builder_routes import BankInput
from .db import database
from .models import AuditEvent, BankQuestion, ImportBatch, User, Slide
from .security import identity, origin_check

router = APIRouter(prefix="/api/v1/organizations/{org_id}/imports", tags=["question imports"])


class Upload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["csv", "xlsx", "pdf", "pptx"]
    content_base64: str = Field(max_length=2800000)


def parse_upload(data: bytes, format: str):
    if len(data) > 2_000_000:
        raise ValueError("Maximum upload size is 2 MB")
    if format in {'pdf','pptx'}:
        from .document_import import extract_document
        return extract_document(data, format)
    if format == "csv":
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    else:
        from openpyxl import load_workbook
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 200 or sum(x.file_size for x in entries) > 10_000_000:
                raise ValueError("Workbook expands beyond the permitted size")
            if any("vbaproject" in x.filename.lower() or "externallinks" in x.filename.lower() for x in entries):
                raise ValueError("Macros and external links are not supported")
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            sheet = workbook.active
            if sheet.max_row > 501 or sheet.max_column > 20:
                raise ValueError("Maximum 500 question rows and 20 columns")
            rows = []
            for cells in sheet.iter_rows():
                if any(c.data_type == "f" for c in cells):
                    raise ValueError("Formula cells are not supported")
                rows.append([str(c.value) if c.value is not None else "" for c in cells])
                if len(rows) > 501:
                    raise ValueError("Maximum 500 question rows")
        finally:
            workbook.close()
    if not rows or len(rows) > 501:
        raise ValueError("Include a header and at most 500 questions")
    headers = [str(x).strip().lower() for x in rows[0]]
    allowed = {"kind", "title", "options", "correct_answers", "subject", "chapter", "topic", "difficulty", "marks", "explanation", "tags"}
    if len(set(headers)) != len(headers) or not {"kind", "title"}.issubset(headers) or not set(headers).issubset(allowed):
        raise ValueError("Use unique supported headers including kind and title")
    valid, errors = [], []
    for number, row in enumerate(rows[1:], 2):
        if not any(row):
            continue
        if len(row) > len(headers) or any(len(str(x)) > 5000 for x in row):
            errors.append({"row": number, "message": "Too many columns or oversized cell"}); continue
        cells = dict(zip(headers, row))
        try:
            item = BankInput(question={"kind": cells.get("kind"), "title": cells.get("title"),
                "options": [x.strip() for x in cells.get("options", "").split("|") if x.strip()],
                "correct_answers": [x.strip() for x in cells.get("correct_answers", "").split("|") if x.strip()],
                "marks": cells.get("marks") or "1", "explanation": cells.get("explanation", "")},
                subject=cells.get("subject", ""), chapter=cells.get("chapter", ""), topic=cells.get("topic", ""),
                difficulty=cells.get("difficulty") or "medium", tags=[x.strip() for x in cells.get("tags", "").split("|") if x.strip()])
            valid.append(item.model_dump(mode="json"))
        except ValidationError as e:
            errors.append({"row": number, "message": "; ".join(x["msg"] for x in e.errors())})
    if not valid and not errors:
        raise ValueError("No question rows found")
    return valid, errors


def authorize(db, user, org_id):
    from .main import principal, require
    require(principal(db, user, org_id), "bank.write", owner_id=user.id)


@router.post("/preview", dependencies=[Depends(origin_check)])
def preview(org_id: uuid.UUID, data: Upload, user: User = Depends(identity), db: Session = Depends(database)):
    authorize(db, user, org_id)
    try:
        raw = base64.b64decode(data.content_base64, validate=True)
        rows, errors = parse_upload(raw, data.format)
    except (ValueError, binascii.Error, UnicodeError, zipfile.BadZipFile, KeyError) as e:
        raise HTTPException(422, str(e))
    batch = ImportBatch(organization_id=org_id, owner_id=user.id, rows=rows, errors=errors)
    db.add(batch); db.commit()
    return {"id": batch.id, "rows": rows, "errors": errors, "can_commit": bool(rows) and not errors}


@router.post("/{batch_id}/commit", dependencies=[Depends(origin_check)])
def commit(org_id: uuid.UUID, batch_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    authorize(db, user, org_id)
    batch = db.scalar(select(ImportBatch).where(ImportBatch.id == batch_id, ImportBatch.organization_id == org_id,
                                              ImportBatch.owner_id == user.id).with_for_update())
    if not batch:
        raise HTTPException(404, "Import not found")
    if batch.committed:
        return {"imported": len(batch.rows), "already_committed": True}
    created = batch.created_at if batch.created_at.tzinfo else batch.created_at.replace(tzinfo=timezone.utc)
    if created < datetime.now(timezone.utc) - timedelta(hours=24):
        raise HTTPException(410, "Import preview expired")
    if batch.errors or not batch.rows:
        raise HTTPException(422, "Fix all validation errors before importing")
    for row in batch.rows:
        db.add(BankQuestion(organization_id=org_id, owner_id=user.id, **BankInput.model_validate(row).model_dump(mode="json")))
    batch.committed = True
    db.add(AuditEvent(organization_id=org_id, actor_id=user.id, action="bank.import_committed", resource_id=str(batch.id)))
    db.commit()
    return {"imported": len(batch.rows), "already_committed": False}


class ImportIntoPresentation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)


@router.post('/{batch_id}/presentation/{presentation_id}', dependencies=[Depends(origin_check)])
def import_into_presentation(org_id: uuid.UUID, batch_id: uuid.UUID, presentation_id: uuid.UUID,
                             data: ImportIntoPresentation, user: User = Depends(identity), db: Session = Depends(database)):
    from .builder_routes import access, get_slides
    authorize(db,user,org_id)
    presentation=access(db,user,org_id,presentation_id,write=True)
    batch=db.scalar(select(ImportBatch).where(ImportBatch.id==batch_id,ImportBatch.organization_id==org_id,
                                            ImportBatch.owner_id==user.id).with_for_update())
    if not batch:raise HTTPException(404,'Import not found')
    if batch.committed:raise HTTPException(409,'This import has already been saved')
    created=batch.created_at if batch.created_at.tzinfo else batch.created_at.replace(tzinfo=timezone.utc)
    if created<datetime.now(timezone.utc)-timedelta(hours=24):raise HTTPException(410,'Import preview expired')
    if batch.errors or not batch.rows:raise HTTPException(422,'Fix all validation errors before importing')
    if presentation.revision!=data.revision:raise HTTPException(409,'Presentation changed; reload before importing')
    slides=list(db.scalars(select(Slide).where(Slide.presentation_id==presentation_id).order_by(Slide.ordinal)))
    if len(slides)+len(batch.rows)>100:raise HTTPException(422,'A presentation supports at most 100 questions')
    start=max((s.ordinal for s in slides),default=-1)+1
    for offset,row in enumerate(batch.rows):
        item=BankInput.model_validate(row)
        db.add(Slide(presentation_id=presentation_id,ordinal=start+offset,question=item.question.model_dump(mode='json')))
    batch.committed=True;presentation.revision+=1
    db.add(AuditEvent(organization_id=org_id,actor_id=user.id,action='presentation.import_committed',resource_id=str(batch.id)))
    db.commit()
    return get_slides(org_id,presentation_id,user,db)
