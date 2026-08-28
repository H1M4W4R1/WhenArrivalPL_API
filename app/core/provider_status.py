"""Thread-safe provider refresh status tracking."""

from dataclasses import dataclass
from enum import StrEnum
from threading import Lock


class ProviderRefreshState(StrEnum):
    """A provider's current refresh stage."""

    PENDING = "pending"
    VALID = "valid"
    DOWNLOADING_DELAYS = "downloading_delays"
    UPDATING_DELAYS = "updating_delays"
    DOWNLOADING_SCHEDULE = "downloading_schedule"
    UPDATING_SCHEDULE = "updating_schedule"
    DOWNLOADING_TICKET_MACHINES = "downloading_ticket_machines"
    UPDATING_TICKET_MACHINES = "updating_ticket_machines"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProviderRefreshStatus:
    """An immutable snapshot of one provider's refresh progress."""

    slug: str
    state: ProviderRefreshState
    progress: float


class ProviderStatusTracker:
    """Own provider refresh state shared by the API and worker threads."""

    def __init__(self, provider_slugs: tuple[str, ...]) -> None:
        self._lock = Lock()
        self._statuses = {
            slug: ProviderRefreshStatus(slug, ProviderRefreshState.PENDING, 0.0) for slug in provider_slugs
        }

    def set(self, provider_slug: str, state: ProviderRefreshState, progress: float) -> None:
        """Set one provider's bounded progress value."""
        if not 0.0 <= progress <= 1.0:
            raise ValueError("Provider progress must be between 0.0 and 1.0")
        with self._lock:
            if provider_slug not in self._statuses:
                raise ValueError(f"Unknown provider status: {provider_slug}")
            self._statuses[provider_slug] = ProviderRefreshStatus(provider_slug, state, progress)

    def snapshots(self) -> tuple[ProviderRefreshStatus, ...]:
        """Return a deterministic, immutable copy of every configured provider state."""
        with self._lock:
            return tuple(self._statuses[slug] for slug in sorted(self._statuses))
