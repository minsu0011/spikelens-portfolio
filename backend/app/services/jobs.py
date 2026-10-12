import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import AnalysisJob, AuditLog, JobAttempt, Upload
from app.providers.demo import PROVIDER_VERSION

logger = logging.getLogger("spikelens")
ALLOWED_TRANSITIONS = {
    "QUEUED": {"RUNNING", "FAILED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "QUEUED"},
    "FAILED": {"QUEUED"},
    "SUCCEEDED": set(),
}


def transition(job, status: str):
    if status not in ALLOWED_TRANSITIONS.get(job.status, set()):
        raise ValueError(f"Invalid job transition {job.status} -> {status}")
    job.status = status


def create_job(db: Session, owner_id: uuid.UUID, upload_id: uuid.UUID, key: str):
    upload = db.scalar(select(Upload).where(Upload.id == upload_id, Upload.owner_id == owner_id))
    if not upload:
        raise AppError(404, "UPLOAD_NOT_FOUND", "Upload was not found")
    if upload.status != "VALIDATED":
        raise AppError(
            422, "INVALID_UPLOAD", "Fix CSV validation errors before requesting analysis"
        )
    prior = db.scalar(
        select(AnalysisJob).where(
            AnalysisJob.owner_id == owner_id, AnalysisJob.idempotency_key == key
        )
    )
    if prior:
        if prior.upload_id != upload_id or prior.model_version != PROVIDER_VERSION:
            raise AppError(
                409, "IDEMPOTENCY_CONFLICT", "This idempotency key belongs to a different request"
            )
        return prior
    record = AnalysisJob(
        owner_id=owner_id,
        upload_id=upload.id,
        idempotency_key=key,
        model_version=PROVIDER_VERSION,
        total_rows=upload.row_count,
        max_attempts=get_settings().max_job_attempts,
        status="QUEUED",
    )
    try:
        db.add(record)
        db.flush()
        db.add(AuditLog(user_id=owner_id, action="analysis_queued", resource_id=str(record.id)))
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = db.scalar(
            select(AnalysisJob).where(
                AnalysisJob.owner_id == owner_id, AnalysisJob.idempotency_key == key
            )
        )
        if prior and prior.upload_id != upload_id:
            raise AppError(
                409, "IDEMPOTENCY_CONFLICT", "This idempotency key belongs to a different request"
            ) from None
        if not prior:
            prior = db.scalar(
                select(AnalysisJob).where(
                    AnalysisJob.upload_id == upload_id,
                    AnalysisJob.model_version == PROVIDER_VERSION,
                    AnalysisJob.owner_id == owner_id,
                )
            )
        if not prior:
            raise
        return prior
    return record


def dispatch_one(job_id):
    """Persist-before-publish outbox. Duplicate deliveries are safe via row-lock claim."""
    from app.tasks.celery_app import celery_app

    with SessionLocal() as db, db.begin():
        job = db.scalar(
            select(AnalysisJob)
            .where(AnalysisJob.id == uuid.UUID(str(job_id)))
            .with_for_update(skip_locked=True)
        )
        current = datetime.now(UTC)
        if (
            not job
            or job.status != "QUEUED"
            or not job.pending_dispatch
            or job.next_dispatch_at > current
        ):
            return False
        task_id = str(uuid.uuid4())
        try:
            # retry=False only limits publish retries; it does not bound Kombu's
            # initial connection or Celery's default Redis result subscription.
            # Scope the bound to this producer so Worker startup can still reconnect.
            transport = {
                **celery_app.conf.broker_transport_options,
                "socket_connect_timeout": 2,
                "socket_timeout": 2,
                "retry_on_timeout": False,
                "max_retries": 0,
                "connect_retries_timeout": 2,
            }
            with celery_app.connection_for_write(
                connect_timeout=2, transport_options=transport
            ) as connection:
                connection.ensure_connection(max_retries=0, timeout=2)
                producer = celery_app.amqp.Producer(connection, auto_declare=False)
                celery_app.send_task(
                    "spikelens.analyze",
                    args=[str(job.id)],
                    task_id=task_id,
                    queue="spikelens",
                    producer=producer,
                    retry=False,
                    retry_policy={"max_retries": 0},
                    timeout=2,
                    ignore_result=True,
                )
        except Exception as exc:
            # Keep DB job durable if publication fails. Never expose broker credentials/exception text.
            job.dispatch_attempts += 1
            job.next_dispatch_at = current + timedelta(seconds=min(300, 2**job.dispatch_attempts))
            job.error_code = "QUEUE_UNAVAILABLE"
            job.error_message = (
                "Analysis queue is temporarily unavailable; dispatch will be retried"
            )
            if job.dispatch_attempts >= 5:
                transition(job, "FAILED")
                job.completed_at = current
                job.pending_dispatch = False
                job.error_message = "Queue dispatch limit reached; retry when service is healthy"
            logger.warning(
                "queue_publish_failed job_id=%s error_type=%s", job.id, type(exc).__name__
            )
            return False
        job.pending_dispatch = False
        job.dispatched_at = current
        job.celery_task_id = task_id
        job.error_code = None
        job.error_message = None
        return True


def claim_job(job_id, celery_task_id=None):
    with SessionLocal() as db, db.begin():
        job = db.scalar(
            select(AnalysisJob).where(AnalysisJob.id == uuid.UUID(str(job_id))).with_for_update()
        )
        if (
            not job
            or job.status != "QUEUED"
            or job.attempts >= job.max_attempts
            or job.next_dispatch_at > datetime.now(UTC)
        ):
            return None
        token = secrets.token_hex(24)
        transition(job, "RUNNING")
        job.attempts += 1
        job.started_at = datetime.now(UTC)
        job.completed_at = None
        job.pending_dispatch = False
        job.error_code = None
        job.error_message = None
        job.lease_token = token
        job.lease_until = datetime.now(UTC) + timedelta(seconds=get_settings().job_lease_seconds)
        if celery_task_id:
            job.celery_task_id = celery_task_id
        db.add(JobAttempt(job_id=job.id, attempt=job.attempts, lease_token=token))
        db.add(
            AuditLog(
                user_id=job.owner_id,
                action="analysis_running",
                resource_id=str(job.id),
                details={"attempt": job.attempts},
            )
        )
        return {
            "id": job.id,
            "owner_id": job.owner_id,
            "upload_id": job.upload_id,
            "lease_token": token,
            "attempt": job.attempts,
        }


def fenced_job(db: Session, job_id, token):
    job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update())
    if not job or job.status != "RUNNING" or job.lease_token != token:
        raise LostLease("Worker no longer owns this job")
    # An expired lease cannot be renewed by an old worker even before recovery runs.
    if job.lease_until is None or job.lease_until <= datetime.now(UTC):
        raise LostLease("Worker lease expired")
    return job


class LostLease(Exception):
    pass


def mark_failure(job_id, token, code: str, message: str, transient: bool):
    with SessionLocal() as db, db.begin():
        try:
            job = fenced_job(db, job_id, token)
        except LostLease:
            return
        current = datetime.now(UTC)
        attempt = db.scalar(
            select(JobAttempt).where(
                JobAttempt.job_id == job.id, JobAttempt.attempt == job.attempts
            )
        )
        if attempt:
            attempt.status = "FAILED"
            attempt.error_code = code
            attempt.completed_at = current
        job.error_code, job.error_message = code, message
        job.lease_token, job.lease_until = None, None
        if transient and job.attempts < job.max_attempts:
            transition(job, "QUEUED")
            job.pending_dispatch = True
            job.next_dispatch_at = current + timedelta(seconds=min(60, 2**job.attempts))
        else:
            transition(job, "FAILED")
            job.completed_at = current
        db.add(
            AuditLog(
                user_id=job.owner_id,
                action="analysis_failed",
                resource_id=str(job.id),
                details={"error_code": code, "attempt": job.attempts, "state": job.status},
            )
        )


def recover_and_dispatch():
    """Beat recovery: expired leases and published-but-never-claimed tasks are fenced/requeued."""
    current = datetime.now(UTC)
    recovered = 0
    with SessionLocal() as db, db.begin():
        jobs = db.scalars(
            select(AnalysisJob)
            .where(AnalysisJob.status == "RUNNING", AnalysisJob.lease_until < current)
            .with_for_update(skip_locked=True)
            .limit(100)
        )
        for job in jobs:
            attempt = db.scalar(
                select(JobAttempt).where(
                    JobAttempt.job_id == job.id, JobAttempt.attempt == job.attempts
                )
            )
            if attempt:
                attempt.status = "ABANDONED"
                attempt.error_code = "WORKER_LEASE_EXPIRED"
                attempt.completed_at = current
            job.lease_token, job.lease_until = None, None
            job.error_code = "WORKER_LEASE_EXPIRED"
            job.error_message = "Worker stopped responding; recovery is scheduled"
            if job.attempts < job.max_attempts:
                transition(job, "QUEUED")
                job.pending_dispatch = True
                job.next_dispatch_at = current + timedelta(seconds=2**job.attempts)
            else:
                transition(job, "FAILED")
                job.completed_at = current
            recovered += 1
        # A publication may be acknowledged by Redis but lost before the worker claims it.
        stale = current - timedelta(seconds=max(60, get_settings().job_lease_seconds))
        queued = db.scalars(
            select(AnalysisJob)
            .where(
                AnalysisJob.status == "QUEUED",
                AnalysisJob.pending_dispatch.is_(False),
                AnalysisJob.dispatched_at < stale,
            )
            .with_for_update(skip_locked=True)
            .limit(100)
        )
        for job in queued:
            job.pending_dispatch = True
            job.next_dispatch_at = current
    with SessionLocal() as db:
        pending = list(
            db.scalars(
                select(AnalysisJob.id)
                .where(
                    AnalysisJob.status == "QUEUED",
                    AnalysisJob.pending_dispatch.is_(True),
                    AnalysisJob.next_dispatch_at <= current,
                )
                .limit(100)
            )
        )
    dispatched = sum(bool(dispatch_one(job_id)) for job_id in pending)
    return {"recovered": recovered, "dispatched": dispatched}


def retry_job(db: Session, job_id, owner_id):
    job = db.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.id == job_id, AnalysisJob.owner_id == owner_id)
        .with_for_update()
    )
    if not job:
        raise AppError(404, "JOB_NOT_FOUND", "Job was not found")
    if job.status != "FAILED" or job.attempts >= job.max_attempts:
        raise AppError(409, "JOB_NOT_RETRYABLE", "Job cannot be retried in its current state")
    transition(job, "QUEUED")
    job.pending_dispatch = True
    job.dispatch_attempts = 0
    job.next_dispatch_at = datetime.now(UTC)
    job.completed_at = None
    job.error_code, job.error_message = None, None
    db.add(AuditLog(user_id=owner_id, action="analysis_retry", resource_id=str(job.id)))
    db.commit()
    return job
