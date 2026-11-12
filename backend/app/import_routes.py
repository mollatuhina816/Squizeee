import base64
import binascii
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from .builder_routes import BankInput
from .db import database
from .models import AuditEvent, BankQuestion, ImportBatch, User, Slide
from .security import identity, origin_check
from .import_schema import CanonicalDocument, CanonicalQuestion, preview_row, question_adapter, to_bank
from .import_pipeline import prepare_preview

router = APIRouter(prefix="/api/v1/organizations/{org_id}/imports", tags=["question imports"])
MAX_UPLOAD_BYTES = 40_000_000


class Upload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["csv", "xlsx", "pdf", "pptx", "docx", "txt", "json"]
    filename: str = Field(default="", max_length=255)
    content_base64: str = Field(max_length=56000000)


def parse_upload(data: bytes, format: str):
    """Synchronous deterministic preview, also used by parser regression tests."""
    from .import_pipeline import deterministic_preview
    from .document_structure import detect_format
    if len(data)>MAX_UPLOAD_BYTES: raise ValueError('Maximum upload size is 40 MB')
    detected=detect_format(data,expected=format)
    if detected=='legacy':raise ValueError('Legacy documents require conversion to DOCX, PPTX, XLSX or PDF')
    rows,errors,_=deterministic_preview(data,detected,'upload.'+detected)
    return rows,errors


def authorize(db, user, org_id):
    from .main import principal, require
    require(principal(db, user, org_id), "bank.write", owner_id=user.id)


def preview_payload(batch, detected_format=None):
    result={'id':batch.id,'rows':batch.rows,'errors':batch.errors,
            'review_count':sum(bool(row.get('requires_review')) for row in batch.rows),
            'can_commit':bool(batch.rows) and not batch.errors and not any(row.get('requires_review') for row in batch.rows),
            'document':{'schema_version':'1.0','questions':[row['canonical'] for row in batch.rows if 'canonical' in row]}}
    if detected_format:result['detected_format']=detected_format
    return result


def save_preview(org_id, user, db, rows, errors, detected_format=None):
    batch=ImportBatch(organization_id=org_id,owner_id=user.id,rows=rows,errors=errors)
    db.add(batch);db.commit()
    return preview_payload(batch,detected_format)


def ai_reservation(org_id,user,db):
    from .main import principal
    from .ai_routes import reserve_generation
    role=principal(db,user,org_id).role
    return lambda:reserve_generation(org_id,user,role)


@router.post('/preview', dependencies=[Depends(origin_check)])
async def preview(org_id: uuid.UUID, data: Upload, user: User = Depends(identity), db: Session = Depends(database)):
    authorize(db,user,org_id)
    reserve=ai_reservation(org_id,user,db)
    db.rollback()
    try:
        raw=base64.b64decode(data.content_base64,validate=True)
        rows,errors,format=await prepare_preview(raw,data.filename or 'upload.'+data.format,data.format,reserve)
    except (ValueError, binascii.Error, UnicodeError, zipfile.BadZipFile, KeyError, ValidationError) as e:
        raise HTTPException(422,str(e)[:1000]) from None
    return save_preview(org_id,user,db,rows,errors,format)


@router.post('/preview/file', dependencies=[Depends(origin_check)])
async def preview_file(org_id: uuid.UUID, file: UploadFile = File(...), user: User = Depends(identity), db: Session = Depends(database)):
    authorize(db,user,org_id)
    raw=await file.read(MAX_UPLOAD_BYTES+1)
    if len(raw)>MAX_UPLOAD_BYTES:raise HTTPException(413,'Maximum upload size is 40 MB')
    filename=(file.filename or 'upload').replace('\\','/').rsplit('/',1)[-1][:255]
    from .document_structure import detect_format
    try:detected=detect_format(raw,filename)
    except (ValueError,UnicodeError,zipfile.BadZipFile) as exc:raise HTTPException(422,str(exc)[:1000]) from None
    from .config import settings
    if detected=='legacy' and not settings().document_conversion_url:
        raise HTTPException(415,'Conversion required: save .doc as DOCX, .ppt as PPTX, .xls as XLSX, or export as PDF. No safe conversion service is configured.')
    reserve=ai_reservation(org_id,user,db)
    db.rollback()
    try:rows,errors,format=await prepare_preview(raw,filename,reserve_ai=reserve)
    except (ValueError,binascii.Error,UnicodeError,zipfile.BadZipFile,KeyError,ValidationError) as exc:
        raise HTTPException(422,str(exc)[:1000]) from None
    return save_preview(org_id,user,db,rows,errors,format)


def editable_batch(db,org_id,user,batch_id,lock=True):
    query=select(ImportBatch).where(ImportBatch.id==batch_id,ImportBatch.organization_id==org_id,ImportBatch.owner_id==user.id)
    batch=db.scalar(query.with_for_update() if lock else query)
    if not batch:raise HTTPException(404,'Import not found')
    if batch.committed:raise HTTPException(409,'This import has already been saved')
    created=batch.created_at if batch.created_at.tzinfo else batch.created_at.replace(tzinfo=timezone.utc)
    if created<datetime.now(timezone.utc)-timedelta(hours=24):raise HTTPException(410,'Import preview expired')
    return batch


class FacultyReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    document: CanonicalDocument
    acknowledge_unresolved: bool = False


@router.post('/{batch_id}/review', dependencies=[Depends(origin_check)])
def review_import(org_id: uuid.UUID,batch_id: uuid.UUID,data: FacultyReview,user: User = Depends(identity),db: Session = Depends(database)):
    authorize(db,user,org_id);batch=editable_batch(db,org_id,user,batch_id)
    if batch.errors and not data.acknowledge_unresolved:raise HTTPException(422,'Review the source and explicitly acknowledge unresolved extraction content before approving')
    if not data.document.questions:raise HTTPException(422,'Include at least one reviewed question')
    rows=[]
    for index,item in enumerate(data.document.questions,1):
        item.requires_review=False
        item.answer_origin='faculty' if getattr(item,'correct_answers',[]) or getattr(item,'accepted_answers',[]) or getattr(item,'model_answer','') else 'missing'
        try:to_bank(item)
        except ValidationError as exc:raise HTTPException(422,f'Question {index}: '+ '; '.join(e['msg'] for e in exc.errors())) from None
        rows.append(preview_row(item))
    batch.rows=rows;batch.errors=[]
    db.add(AuditEvent(organization_id=org_id,actor_id=user.id,action='import.faculty_reviewed',resource_id=str(batch.id)))
    db.commit();return preview_payload(batch)


class SuggestionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question: CanonicalQuestion


@router.post('/{batch_id}/questions/{question_index}/suggest-answer', dependencies=[Depends(origin_check)])
async def suggest_import_answer(org_id: uuid.UUID,batch_id: uuid.UUID,question_index: int,data: SuggestionInput | None = Body(default=None),user: User = Depends(identity),db: Session = Depends(database)):
    from .document_ai import suggest_answer
    from .ai_question_generator import AIGenerationError
    from .ai_routes import _raise_generation_error
    authorize(db,user,org_id);batch=editable_batch(db,org_id,user,batch_id,lock=False)
    if question_index<0 or question_index>=len(batch.rows):raise HTTPException(404,'Question not found')
    row=batch.rows[question_index]
    item=data.question if data else question_adapter.validate_python(row['canonical'])
    if item.type not in {'mcq','quiz','multiple_select','true_false','short_answer'}:raise HTTPException(422,'This question does not use a correct answer')
    reserve=ai_reservation(org_id,user,db);db.rollback();reserve()
    try:return await suggest_answer(item)
    except AIGenerationError as exc:_raise_generation_error(exc)
    except (ValueError,ValidationError):raise HTTPException(502,'AI suggestion could not be validated') from None


def validated_bank_rows(batch):
    if batch.errors or not batch.rows:raise HTTPException(422,'Fix all validation errors before importing')
    result=[]
    for row in batch.rows:
        if row.get('requires_review'):raise HTTPException(422,'Approve every question requiring faculty review before importing')
        if 'canonical' in row:
            item=question_adapter.validate_python(row['canonical'])
            if item.requires_review or item.answer_origin=='ai_suggested':raise HTTPException(422,'AI suggestions and incomplete questions need faculty review')
            result.append(to_bank(item))
        else:result.append(BankInput.model_validate(row).model_dump(mode='json'))
    return result


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
    rows=validated_bank_rows(batch)
    for row in rows:
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
    rows=validated_bank_rows(batch)
    if presentation.revision!=data.revision:raise HTTPException(409,'Presentation changed; reload before importing')
    slides=list(db.scalars(select(Slide).where(Slide.presentation_id==presentation_id).order_by(Slide.ordinal)))
    if len(slides)+len(batch.rows)>100:raise HTTPException(422,'A presentation supports at most 100 questions')
    start=max((s.ordinal for s in slides),default=-1)+1
    for offset,row in enumerate(rows):
        item=BankInput.model_validate(row)
        db.add(Slide(presentation_id=presentation_id,ordinal=start+offset,question=item.question.model_dump(mode='json')))
    batch.committed=True;presentation.revision+=1
    db.add(AuditEvent(organization_id=org_id,actor_id=user.id,action='presentation.import_committed',resource_id=str(batch.id)))
    db.commit()
    return get_slides(org_id,presentation_id,user,db)
