from typing import Protocol

from app.schemas.events import EventInput


class AnalysisProvider(Protocol):
    """Application boundary for a row-processing provider; no model implementation."""

    version: str

    def process(self, event: EventInput, *, row_index: int = 0) -> dict: ...
