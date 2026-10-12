from fastapi import APIRouter, Depends
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Event
from app.schemas.events import EventOutput
from app.services.cache import get_public_summary, set_public_summary

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    cached = get_public_summary()
    if cached:
        return cached
    count, tickers, volume, average = db.execute(
        select(
            func.count(Event.id),
            func.count(func.distinct(Event.ticker)),
            func.coalesce(func.sum(Event.volume), 0),
            func.coalesce(func.avg(Event.anomaly_score), 0),
        ).where(Event.is_public.is_(True))
    ).one()
    sessions = db.execute(
        select(Event.session, func.count()).where(Event.is_public.is_(True)).group_by(Event.session)
    ).all()
    days = db.execute(
        select(cast(Event.event_time, Date), func.count())
        .where(Event.is_public.is_(True))
        .group_by(cast(Event.event_time, Date))
        .order_by(cast(Event.event_time, Date).desc())
        .limit(30)
    ).all()
    recent = db.scalars(
        select(Event)
        .where(Event.is_public.is_(True))
        .order_by(Event.event_time.desc(), Event.id.desc())
        .limit(6)
    )
    result = {
        "total_events": count,
        "tickers": tickers,
        "total_volume": volume,
        "average_anomaly_score": round(float(average), 2),
        "by_session": [{"session": session, "count": n} for session, n in sessions],
        "daily_counts": [{"date": str(day), "count": n} for day, n in reversed(days)],
        "recent_events": [
            EventOutput.model_validate(item).model_dump(mode="json") for item in recent
        ],
        "data_source": "SYNTHETIC_DEMO_ONLY",
    }
    set_public_summary(result)
    return result
