import re
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SessionName = Literal["PREMARKET", "RTH", "AFTERHOURS"]


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str = Field(min_length=1, max_length=16)
    event_time: datetime
    session: SessionName
    event_type: Literal["PRICE_SPIKE", "VOLUME_SURGE", "VOLATILITY"] = "PRICE_SPIKE"
    p0_price: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    t5_price: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    volume: int = Field(ge=0, le=10**12)
    price_path: list[float] = Field(min_length=2, max_length=512)

    @field_validator("ticker")
    @classmethod
    def clean_ticker(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,15}", value):
            raise ValueError("Ticker must contain letters, digits, periods or hyphens")
        return value

    @field_validator("event_time")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_time must include a UTC offset")
        return value.astimezone(UTC)

    @field_validator("price_path")
    @classmethod
    def finite_prices(cls, value: list[float]) -> list[float]:
        import math

        if any(not math.isfinite(price) or price <= 0 or price > 1000000 for price in value):
            raise ValueError("All prices must be finite and positive")
        return value


class EventOutput(EventInput):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    anomaly_score: float
    data_quality_score: float
    model_version: str
    is_public: bool
    is_synthetic: bool
    created_at: datetime
