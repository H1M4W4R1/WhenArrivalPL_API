"""Transit stop response."""

from app.models.request_model_base import RequestModelBase


class StopModel(RequestModelBase):
    """A GTFS stop reduced for embedded clients."""

    id: str
    name: str
    latitude: float | None
    longitude: float | None
    code: str | None
