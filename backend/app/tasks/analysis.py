import hashlib
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logger
from app.db.session import SessionLocal
from app.models import AnalysisResult, AuditLog, Event, JobAttempt, Upload
from app.providers.demo import DemoAnalysisProvider
from app.repositories.events import source_key
from app.services.csv_validation import parse_csv
from app.services.jobs import (
    LostLease,
    claim_job,
    fenced_job,
    mark_failure,
    recover_and_dispatch,
    transition,
)
from app.services.storage import LocalUploadStorage
from app.tasks.celery_app import celery_app

logger = configure_logger()


class AnalysisInputError(Exception):
    pass


def process_job(job_id, celery_task_id=None, *, checkpoint_hook=None):
    started = time.perf_counter()
    claim = claim_job(job_id, celery_task_id)
    if not claim:
        return {"status": "not_claimed"}
    token, ident = claim["lease_token"], claim["id"]
    try:
        with SessionLocal() as db:
            upload = db.get(Upload, claim["upload_id"])
            if not upload:
                raise AnalysisInputError("Upload metadata is unavailable")
            storage_key, expected_sha = upload.storage_key, upload.sha256
        data = LocalUploadStorage().read(storage_key)
        if hashlib.sha256(data).hexdigest() != expected_sha:
            raise AnalysisInputError("Upload checksum verification failed")
        events, errors, _ = parse_csv(data, get_settings().max_upload_rows)
        if errors:
            raise AnalysisInputError("Stored CSV failed validation")
        engine = DemoAnalysisProvider()
        for start in range(0, len(events), 100):
            chunk = events[start : start + 100]
            scored = [
                (event, engine.process(event, row_index=start + index), source_key(claim["owner_id"], event))
                for index, event in enumerate(chunk)
            ]
            with SessionLocal() as db, db.begin():
                job = fenced_job(db, ident, token)
                for event, result, key in scored:
                    values = dict(
                        id=uuid.uuid4(),
                        owner_id=claim["owner_id"],
                        upload_id=claim["upload_id"],
                        **event.model_dump(),
                        source_key=key,
                        anomaly_score=result["anomaly_score"],
                        data_quality_score=result["data_quality_score"],
                        model_version=engine.version,
                        is_public=False,
                        is_synthetic=False,
                        created_at=datetime.now(UTC),
                    )
                    db.execute(
                        insert(Event)
                        .values(**values)
                        .on_conflict_do_nothing(index_elements=[Event.source_key])
                    )
                    record = db.scalar(select(Event).where(Event.source_key == key))
                    if (
                        not record
                        or record.p0_price != event.p0_price
                        or record.t5_price != event.t5_price
                        or record.volume != event.volume
                        or record.price_path != event.price_path
                        or record.event_type != event.event_type
                    ):
                        raise AnalysisInputError(
                            "Existing event identity conflicts with uploaded content"
                        )
                    if record.upload_id is None:
                        raise AnalysisInputError(
                            "Upload event identity conflicts with a manually created event"
                        )
                    db.execute(
                        insert(AnalysisResult)
                        .values(
                            id=uuid.uuid4(),
                            job_id=ident,
                            event_id=record.id,
                            **result,
                            created_at=datetime.now(UTC),
                        )
                        .on_conflict_do_nothing(
                            index_elements=[AnalysisResult.job_id, AnalysisResult.event_id]
                        )
                    )
                job.processed_rows = (
                    db.scalar(
                        select(func.count())
                        .select_from(AnalysisResult)
                        .where(AnalysisResult.job_id == ident)
                    )
                    or 0
                )
                job.lease_until = datetime.now(UTC) + timedelta(
                    seconds=get_settings().job_lease_seconds
                )
                logger.info(
                    "job_progress job_id=%s processed_rows=%d total_rows=%d attempt=%d",
                    ident,
                    job.processed_rows,
                    job.total_rows,
                    job.attempts,
                )
            if checkpoint_hook:
                checkpoint_hook("batch_committed", ident)
        if checkpoint_hook:
            checkpoint_hook("before_complete", ident)
        with SessionLocal() as db, db.begin():
            job = fenced_job(db, ident, token)
            actual = (
                db.scalar(
                    select(func.count())
                    .select_from(AnalysisResult)
                    .where(AnalysisResult.job_id == ident)
                )
                or 0
            )
            if actual != job.total_rows:
                raise AnalysisInputError("Result count does not match the validated upload")
            transition(job, "SUCCEEDED")
            job.processed_rows = actual
            job.completed_at = datetime.now(UTC)
            job.lease_token, job.lease_until = None, None
            attempt = db.scalar(
                select(JobAttempt).where(
                    JobAttempt.job_id == ident, JobAttempt.attempt == job.attempts
                )
            )
            if attempt:
                attempt.status = "SUCCEEDED"
                attempt.completed_at = job.completed_at
            db.add(
                AuditLog(
                    user_id=job.owner_id,
                    action="analysis_succeeded",
                    resource_id=str(job.id),
                    details={
                        "rows": actual,
                        "duration_seconds": round(time.perf_counter() - started, 3),
                    },
                )
            )
        logger.info(
            "job_completed job_id=%s duration_seconds=%.3f", ident, time.perf_counter() - started
        )
        return {"status": "SUCCEEDED", "rows": actual}
    except LostLease:
        logger.warning("job_lost_lease job_id=%s", ident)
        return {"status": "lost_lease"}
    except (AnalysisInputError, AppError, ValueError) as exc:
        mark_failure(
            ident,
            token,
            "INPUT_REJECTED",
            str(exc)[:250]
            if isinstance(exc, AnalysisInputError)
            else "Uploaded input failed validation",
            False,
        )
        return {"status": "FAILED"}
    except (SQLAlchemyError, OSError, Exception) as exc:
        # A DB outage may prevent writing failure state; expired lease recovery remains durable.
        logger.error("job_execution_error job_id=%s error_type=%s", ident, type(exc).__name__)
        try:
            mark_failure(
                ident,
                token,
                "PROCESSING_TEMPORARY_FAILURE",
                "Analysis interrupted; a bounded retry is scheduled",
                True,
            )
        except SQLAlchemyError:
            logger.error("job_failure_state_write_unavailable job_id=%s", ident)
        return {"status": "interrupted"}


@celery_app.task(name="spikelens.analyze", bind=True, acks_late=True, reject_on_worker_lost=True)
def analyze(self, job_id: str):
    return process_job(job_id, self.request.id)


@celery_app.task(name="spikelens.recover")
def recover():
    return recover_and_dispatch()
