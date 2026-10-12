from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models import AnalysisJob, User
from app.services.cache import redis_client

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/metrics")
def metrics(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.main import api_latencies

    users = db.scalar(select(func.count()).select_from(User)) or 0
    states = db.execute(select(AnalysisJob.status, func.count()).group_by(AnalysisJob.status)).all()
    total = sum(count for _, count in states)
    failed = next((count for state, count in states if state == "FAILED"), 0)
    times = db.execute(
        select(AnalysisJob.created_at, AnalysisJob.started_at, AnalysisJob.completed_at).where(
            AnalysisJob.status == "SUCCEEDED"
        )
    ).all()
    queue = [
        (started - created).total_seconds() for created, started, completed in times if started
    ]
    processing = [
        (completed - started).total_seconds()
        for created, started, completed in times
        if completed and started
    ]
    hits, misses, redis_status = 0, 0, "ok"
    try:
        hits, misses = [
            int(value or 0)
            for value in redis_client.mget(
                "spikelens:metrics:cache_hits", "spikelens:metrics:cache_misses"
            )
        ]
    except Exception:
        redis_status = "unavailable"
    latencies = sorted(api_latencies)

    def percentile(p):
        return (
            round(latencies[min(len(latencies) - 1, int((len(latencies) - 1) * p))], 3)
            if latencies
            else None
        )

    return {
        "users": users,
        "total_jobs": total,
        "jobs_by_status": [{"status": state, "count": count} for state, count in states],
        "failure_rate": round(failed / total, 4) if total else 0,
        "average_queue_wait_seconds": round(sum(queue) / len(queue), 3) if queue else None,
        "average_processing_seconds": round(sum(processing) / len(processing), 3)
        if processing
        else None,
        "cache": {
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hits / (hits + misses), 4) if hits + misses else None,
        },
        "api": {
            "requests": len(latencies),
            "p50_ms": percentile(0.5),
            "p95_ms": percentile(0.95),
            "scope": "current_api_process_last_10000",
        },
        "dependencies": {"database": "ok", "redis": redis_status},
    }
