"""Health response."""

from app.models.request_model_base import RequestModelBase


class HealthModel(RequestModelBase):
    """Application health and configured-provider count."""

    status: str
    providers: int
