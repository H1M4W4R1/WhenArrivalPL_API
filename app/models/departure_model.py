"""Scheduled departure response."""

from datetime import datetime

from app.models.request_model_base import RequestModelBase


class DepartureModel(RequestModelBase):
    """A scheduled departure enriched by the real-time delay, if available."""

    trip_id: str
    stop_name: str
    route: str | None
    destination: str | None
    scheduled_at: datetime
    estimated_at: datetime
    delay_seconds: int
