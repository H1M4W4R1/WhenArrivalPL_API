"""Provider refresh status response."""

from pydantic import Field

from app.core.provider_status import ProviderRefreshState
from app.models.request_model_base import RequestModelBase


class ProviderStatusModel(RequestModelBase):
    """Current refresh state for one configured provider."""

    slug: str
    city: str
    status: ProviderRefreshState
    progress: float = Field(ge=0.0, le=1.0)
