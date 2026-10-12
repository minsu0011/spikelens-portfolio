import asyncio
import csv
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import require_user
from app.db.session import SessionLocal, get_db
from app.models import AnalysisJob, AnalysisResult, Event, User, UserSession
from app.schemas.jobs import AnalysisInput, job_output
from app.services.csv_validation import safe_csv_cell
from app.services.jobs import create_job, dispatch_one, retry_job

router = APIRouter(tags=["Analysis jobs"])


def owned_job(db, job_id, user_id):
    job = db.scalar(
        select(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.owner_id == user_id)
    )
    if not job:
        raise AppError(404, "JOB_NOT_FOUND", "Job was not found")
    return job


@router.post("/analyses", status_code=202)
def analyze(
    data: AnalysisInput,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if (
        not idempotency_key
        or not 8 <= len(idempotency_key) <= 128
        or not all(32 < ord(char) < 127 for char in idempotency_key)
    ):
        raise AppError(
            422,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Supply an Idempotency-Key header of 8–128 printable characters",
        )
    job = create_job(db, user.id, data.upload_id, idempotency_key)
    # Publication occurs after commit. A broker outage preserves pending_dispatch for beat recovery.
    dispatch_one(job.id)
    db.refresh(job)
    return job_output(job)


@router.get("/jobs")
def index(
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"] | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    predicate = [AnalysisJob.owner_id == user.id]
    if status:
        predicate.append(AnalysisJob.status == status)
    total = db.scalar(select(func.count()).select_from(AnalysisJob).where(*predicate)) or 0
    jobs = db.scalars(
        select(AnalysisJob)
        .where(*predicate)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return {
        "items": [job_output(job) for job in jobs],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/jobs/{job_id}")
def detail(job_id: uuid.UUID, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return job_output(owned_job(db, job_id, user.id))


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry(job_id: uuid.UUID, user: User = Depends(require_user), db: Session = Depends(get_db)):
    job = retry_job(db, job_id, user.id)
    dispatch_one(job.id)
    db.refresh(job)
    return job_output(job)


def result_item(result, event):
    return {
        "id": result.id,
        "event_id": result.event_id,
        "ticker": event.ticker,
        "event_time": event.event_time,
        "session": event.session,
        "anomaly_score": result.anomaly_score,
        "data_quality_score": result.data_quality_score,
        "event_summary": result.event_summary,
        "model_version": result.model_version,
        "metrics": result.metrics,
    }


@router.get("/jobs/{job_id}/results")
def results(
    job_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    job = owned_job(db, job_id, user.id)
    if job.status != "SUCCEEDED":
        raise AppError(409, "RESULTS_NOT_READY", "Results become available when analysis succeeds")
    total = (
        db.scalar(
            select(func.count()).select_from(AnalysisResult).where(AnalysisResult.job_id == job_id)
        )
        or 0
    )
    rows = db.execute(
        select(AnalysisResult, Event)
        .join(Event, Event.id == AnalysisResult.event_id)
        .where(AnalysisResult.job_id == job_id)
        .order_by(Event.event_time.asc(), Event.id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return {
        "items": [result_item(result, event) for result, event in rows],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/jobs/{job_id}/results.csv")
def results_csv(
    job_id: uuid.UUID, user: User = Depends(require_user), db: Session = Depends(get_db)
):
    job = owned_job(db, job_id, user.id)
    if job.status != "SUCCEEDED":
        raise AppError(409, "RESULTS_NOT_READY", "Results become available when analysis succeeds")
    rows = db.execute(
        select(AnalysisResult, Event)
        .join(Event, Event.id == AnalysisResult.event_id)
        .where(AnalysisResult.job_id == job_id)
        .order_by(Event.event_time.asc(), Event.id.asc())
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "event_id",
            "ticker",
            "event_time",
            "session",
            "anomaly_score",
            "data_quality_score",
            "event_summary",
            "model_version",
        ]
    )
    for result, event in rows:
        writer.writerow(
            [
                safe_csv_cell(value)
                for value in [
                    str(event.id),
                    event.ticker,
                    event.event_time.isoformat(),
                    event.session,
                    result.anomaly_score,
                    result.data_quality_score,
                    result.event_summary,
                    result.model_version,
                ]
            ]
        )
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="spikelens-{job_id}.csv"'},
    )


def stream_snapshot(job_id, user_id, session_id):
    with SessionLocal() as db:
        session = db.scalar(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.user_id == user_id,
                UserSession.expires_at > datetime.now(UTC),
            )
        )
        if not session:
            return None
        job = db.scalar(
            select(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.owner_id == user_id)
        )
        return job_output(job).model_dump(mode="json") if job else None


@router.get("/jobs/{job_id}/stream")
def stream(
    job_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    owned_job(db, job_id, user.id)
    user_id, session_id = user.id, request.state.auth_session.id
    # Close the auth/read transaction before returning a long-lived stream.
    db.close()

    async def generate():
        prior, heartbeat = None, 0
        while not await request.is_disconnected():
            snapshot = await asyncio.to_thread(stream_snapshot, job_id, user_id, session_id)
            if snapshot is None:
                yield "event: auth.expired\ndata: {}\n\n"
                return
            serialized = json.dumps(snapshot, separators=(",", ":"))
            if serialized != prior:
                name = {
                    "RUNNING": "job.started" if prior is None else "job.progress",
                    "SUCCEEDED": "job.completed",
                    "FAILED": "job.failed",
                }.get(snapshot["status"], "job.progress")
                yield f"event: {name}\ndata: {serialized}\n\n"
                prior = serialized
            if snapshot["status"] in {"SUCCEEDED", "FAILED"}:
                return
            heartbeat += 1
            if heartbeat % 10 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
