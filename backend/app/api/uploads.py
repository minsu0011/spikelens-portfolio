import hashlib
import re
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import require_user
from app.db.session import get_db
from app.models import AuditLog, Upload, User
from app.schemas.jobs import UploadOutput
from app.services.csv_validation import parse_csv
from app.services.storage import LocalUploadStorage

router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.post("", response_model=UploadOutput, status_code=201)
def upload(
    file: UploadFile = File(...), user: User = Depends(require_user), db: Session = Depends(get_db)
):
    filename = file.filename or ""
    if (
        len(filename) > 255
        or not re.fullmatch(r"[^/\\\x00-\x1f:]{1,251}\.csv", filename, re.IGNORECASE)
        or filename.startswith(".")
    ):
        raise AppError(400, "UNSAFE_FILENAME", "Please upload a CSV with a simple filename")
    if file.content_type not in {
        "text/csv",
        "application/csv",
        "application/octet-stream",
        "application/vnd.ms-excel",
    }:
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", "Only CSV files are accepted")
    data = file.file.read(get_settings().max_upload_bytes + 1)
    if len(data) > get_settings().max_upload_bytes:
        raise AppError(413, "UPLOAD_TOO_LARGE", "File exceeds the configured size limit")
    sha = hashlib.sha256(data).hexdigest()
    prior = db.scalar(select(Upload).where(Upload.owner_id == user.id, Upload.sha256 == sha))
    if prior:
        return prior
    _, errors, rows = parse_csv(data, get_settings().max_upload_rows)
    key = f"{uuid.uuid4().hex}.csv"
    storage = LocalUploadStorage()
    try:
        storage.write(key, data)
    except OSError as exc:
        raise AppError(
            503, "STORAGE_UNAVAILABLE", "Upload storage is temporarily unavailable"
        ) from exc
    record = Upload(
        owner_id=user.id,
        original_filename=filename,
        storage_key=key,
        sha256=sha,
        size_bytes=len(data),
        row_count=rows,
        status="INVALID" if errors else "VALIDATED",
        validation_errors=errors,
    )
    try:
        db.add(record)
        db.flush()
        db.add(
            AuditLog(
                user_id=user.id,
                action="upload_created",
                resource_id=str(record.id),
                details={"rows": rows, "status": record.status},
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        storage.delete(key)
        prior = db.scalar(select(Upload).where(Upload.owner_id == user.id, Upload.sha256 == sha))
        if not prior:
            raise
        return prior
    except BaseException:
        db.rollback()
        storage.delete(key)
        raise
    return record


@router.get("")
def index(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    total = (
        db.scalar(select(func.count()).select_from(Upload).where(Upload.owner_id == user.id)) or 0
    )
    items = db.scalars(
        select(Upload)
        .where(Upload.owner_id == user.id)
        .order_by(Upload.created_at.desc(), Upload.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return {
        "items": [UploadOutput.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/{upload_id}", response_model=UploadOutput)
def detail(upload_id: uuid.UUID, user: User = Depends(require_user), db: Session = Depends(get_db)):
    record = db.scalar(select(Upload).where(Upload.id == upload_id, Upload.owner_id == user.id))
    if not record:
        raise AppError(404, "UPLOAD_NOT_FOUND", "Upload was not found")
    return record
