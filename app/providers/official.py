"""Official public GTFS providers not mirrored by mkuran.pl."""

from dataclasses import dataclass

from app.providers.base import TransitProvider


@dataclass(frozen=True, slots=True)
class OfficialProvider(TransitProvider):
    """A provider backed by one or more stable official GTFS archives."""

    slug: str
    city: str
    static_url: str
    trip_updates_url: str | None = None
    ticket_machines_url: str | None = None
    additional_static_urls: tuple[str, ...] = ()
    additional_trip_update_urls: tuple[str, ...] = ()

    def static_feed_urls(self) -> tuple[str, ...]:
        """Return every archive that belongs to this provider."""
        return (self.static_url, *self.additional_static_urls)

    def trip_update_urls(self) -> tuple[str, ...]:
        """Return every TripUpdates feed published for this provider."""
        return (*super().trip_update_urls(), *self.additional_trip_update_urls)


def official_providers() -> tuple[TransitProvider, ...]:
    """Return official city feeds absent from the mkuran.pl catalog."""
    return (
        OfficialProvider(
            "krakow",
            "Kraków",
            "https://gtfs.ztp.krakow.pl/GTFS_KRK_A.zip",
            additional_static_urls=(
                "https://gtfs.ztp.krakow.pl/GTFS_KRK_M.zip",
                "https://gtfs.ztp.krakow.pl/GTFS_KRK_T.zip",
            ),
        ),
        OfficialProvider(
            "poznan",
            "Poznań",
            "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile",
        ),
        OfficialProvider(
            "szczecin",
            "Szczecin",
            "https://www.zditm.szczecin.pl/storage/gtfs/gtfs.zip",
            "https://www.zditm.szczecin.pl/storage/gtfs/gtfs-rt-trips.pb",
        ),
        OfficialProvider(
            "bialystok",
            "Białystok",
            "https://komunikacja.bialystok.pl/cms/File/download/gtfs/google_transit.zip",
        ),
        OfficialProvider("gdynia", "Gdynia", "http://api.zdiz.gdynia.pl/pt/gtfs.zip"),
    )
