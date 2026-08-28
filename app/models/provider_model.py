"""Transit provider metadata response."""

from app.models.request_model_base import RequestModelBase


class ProviderModel(RequestModelBase):
    """A configured transit provider."""

    slug: str
    city: str
    enabled: bool
    has_realtime: bool
