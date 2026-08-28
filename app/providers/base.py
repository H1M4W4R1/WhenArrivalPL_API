"""Provider contract for static, real-time and ancillary feeds."""

from abc import ABC


class TransitProvider(ABC):
    """A city's externally hosted transit data."""

    slug: str
    city: str
    static_url: str
    trip_updates_url: str | None = None
    ticket_machines_url: str | None = None

    def static_feed_urls(self) -> tuple[str, ...]:
        """Return one or more static GTFS archives that form this provider's schedule."""
        return (self.static_url,)

    def trip_update_urls(self) -> tuple[str, ...]:
        """Return every GTFS-Realtime TripUpdates feed for this provider."""
        return (self.trip_updates_url,) if self.trip_updates_url is not None else ()

    @property
    def enabled(self) -> bool:
        """Whether required credentials are present."""
        return True
