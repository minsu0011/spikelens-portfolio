import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UploadOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    original_filename: str
    sha256: str
    size_bytes: int
    row_count: int
    status: str
    validation_errors: list[dict]
    created_at: datetime


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: uuid.UUID


class JobOutput(BaseModel):
    id: uuid.UUID
    upload_id: uuid.UUID
    status: str
    progress: float
    processed_rows: int
    total_rows: int
    attempts: int
    max_attempts: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    retryable: bool
    pending_dispatch: bool


def job_output(job):
    return JobOutput(
        id=job.id,
        upload_id=job.upload_id,
        status=job.status,
        progress=round(job.processed_rows * 100 / max(job.total_rows, 1), 2),
        processed_rows=job.processed_rows,
        total_rows=job.total_rows,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        retryable=job.status == "FAILED" and job.attempts < job.max_attempts,
        pending_dispatch=job.pending_dispatch,
    )
