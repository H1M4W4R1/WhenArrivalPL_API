"""Ticket-machine response."""

from app.models.request_model_base import RequestModelBase


class TicketMachineModel(RequestModelBase):
    """A ticket-machine location."""

    id: str
    name: str
    latitude: float | None
    longitude: float | None
    machine_type: str | None
