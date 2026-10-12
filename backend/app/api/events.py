import uuid
from datetime import UTC, date, datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import optional_user, require_user
from app.db.session import get_db
from app.models import AuditLog, Event, User
from app.providers.demo import DemoAnalysisProvider
from app.repositories.events import list_events, source_key, visible_events
from app.schemas.events import EventInput, EventOutput, SessionName

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("")
def index(
    ticker: str | None = Query(None, max_length=16),
    session: SessionName | None = None,
    event_type: Literal["PRICE_SPIKE", "VOLUME_SURGE", "VOLATILITY"] | None = None,
    event_date_from: date | None = None,
    event_date_to: date | None = None,
    sort: Literal["event_time_desc", "event_time_asc", "anomaly_desc"] = "event_time_desc",
    page: int = Query(1, ge=1, le=100000),
    limit: int = Query(25, ge=1, le=100),
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    if event_date_from and event_date_to and event_date_from > event_date_to:
        raise AppError(422, "INVALID_DATE_RANGE", "Start date must precede end date")
    result = list_events(
        db,
        user.id if user else None,
        ticker=ticker,
        session=session,
        event_type=event_type,
        sort=sort,
        page=page,
        limit=limit,
        date_from=datetime.combine(event_date_from, time.min, UTC) if event_date_from else None,
        date_to=datetime.combine(event_date_to, time.max, UTC) if event_date_to else None,
    )
    result["items"] = [EventOutput.model_validate(item) for item in result["items"]]
    return result


@router.get("/{event_id}", response_model=EventOutput)
def detail(
    event_id: uuid.UUID, user: User | None = Depends(optional_user), db: Session = Depends(get_db)
):
    event = db.scalar(
        select(Event).where(Event.id == event_id, visible_events(user.id if user else None))
    )
    if not event:
        raise AppError(404, "EVENT_NOT_FOUND", "Event was not found")
    return event


@router.post("", response_model=EventOutput, status_code=201)
def create(data: EventInput, user: User = Depends(require_user), db: Session = Depends(get_db)):
    scores = DemoAnalysisProvider().process(data)
    event = Event(
        **data.model_dump(),
        owner_id=user.id,
        is_public=False,
        is_synthetic=False,
        source_key=source_key(user.id, data),
        anomaly_score=scores["anomaly_score"],
        data_quality_score=scores["data_quality_score"],
        model_version=scores["model_version"],
    )
    db.add(event)
    try:
        db.flush()
        db.add(AuditLog(user_id=user.id, action="event_created", resource_id=str(event.id)))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            409, "DUPLICATE_EVENT", "This ticker, timestamp and session already exist"
        ) from exc
    return event


@router.put("/{event_id}", response_model=EventOutput)
def update(
    event_id: uuid.UUID,
    data: EventInput,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    event = db.scalar(select(Event).where(Event.id == event_id, Event.owner_id == user.id))
    if not event:
        raise AppError(404, "EVENT_NOT_FOUND", "Owned event was not found")
    if event.upload_id:
        raise AppError(409, "IMMUTABLE_UPLOAD_EVENT", "Uploaded analysis events are immutable")
    scores = DemoAnalysisProvider().process(data)
    for field, value in data.model_dump().items():
        setattr(event, field, value)
    event.source_key = source_key(user.id, data)
    event.anomaly_score = scores["anomaly_score"]
    event.data_quality_score = scores["data_quality_score"]
    try:
        db.add(AuditLog(user_id=user.id, action="event_updated", resource_id=str(event.id)))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "DUPLICATE_EVENT", "This event identity already exists") from exc
    return event


@router.delete("/{event_id}", status_code=204)
def remove(event_id: uuid.UUID, user: User = Depends(require_user), db: Session = Depends(get_db)):
    event = db.scalar(select(Event).where(Event.id == event_id, Event.owner_id == user.id))
    if not event:
        raise AppError(404, "EVENT_NOT_FOUND", "Owned event was not found")
    if event.upload_id:
        raise AppError(409, "IMMUTABLE_UPLOAD_EVENT", "Uploaded analysis events are immutable")
    db.delete(event)
    db.add(AuditLog(user_id=user.id, action="event_deleted", resource_id=str(event.id)))
    db.commit()
