import hashlib
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Event


def source_key(owner_id, event) -> str:
    identity = f"{owner_id}|{event.ticker}|{event.event_time.isoformat()}|{event.session}"
    return hashlib.sha256(identity.encode()).hexdigest()


def visible_events(owner_id=None):
    return (
        or_(Event.is_public.is_(True), Event.owner_id == owner_id)
        if owner_id
        else Event.is_public.is_(True)
    )


def list_events(
    db: Session,
    owner_id=None,
    *,
    ticker=None,
    session=None,
    event_type=None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort="event_time_desc",
    page=1,
    limit=25,
):
    statement = select(Event).where(visible_events(owner_id))
    if ticker:
        statement = statement.where(Event.ticker == ticker.upper())
    if session:
        statement = statement.where(Event.session == session)
    if event_type:
        statement = statement.where(Event.event_type == event_type)
    if date_from:
        statement = statement.where(Event.event_time >= date_from)
    if date_to:
        statement = statement.where(Event.event_time <= date_to)
    count = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    order = {
        "event_time_desc": (Event.event_time.desc(), Event.id.desc()),
        "event_time_asc": (Event.event_time.asc(), Event.id.asc()),
        "anomaly_desc": (Event.anomaly_score.desc(), Event.event_time.desc(), Event.id.desc()),
    }[sort]
    items = list(db.scalars(statement.order_by(*order).offset((page - 1) * limit).limit(limit)))
    return {
        "items": items,
        "total": count,
        "page": page,
        "limit": limit,
        "pages": (count + limit - 1) // limit,
    }
