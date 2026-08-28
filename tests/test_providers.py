"""Provider registry configuration tests."""

from datetime import date

from app.providers.olsztyn import _select_current_feed_url
from app.providers.registry import registered_providers
from app.providers.wroclaw import _select_current_feed_url as select_wroclaw_feed_url


def test_registry_contains_every_public_missing_polish_city_feed() -> None:
    providers = registered_providers()

    assert {"krakow", "wroclaw", "poznan", "szczecin", "bialystok", "gdynia", "olsztyn"}.issubset(providers)
    assert len(providers) == len(set(providers))
    assert len(providers["krakow"].static_feed_urls()) == 3
    assert providers["szczecin"].trip_updates_url is not None


def test_olsztyn_catalog_resolution_prefers_the_archive_covering_today() -> None:
    selected = _select_current_feed_url(
        [
            "https://zdzit.olsztyn.eu/wp-content/uploads/2026/06/GTFS_2026_06_27-08_31.zip",
            "https://zdzit.olsztyn.eu/wp-content/uploads/2026/07/GTFS_2026_07_31-08_31.zip",
            "https://untrusted.example/GTFS_2026_08_01-08_31.zip",
        ],
        date(2026, 8, 28),
    )

    assert selected.endswith("GTFS_2026_07_31-08_31.zip")


def test_wroclaw_catalog_resolution_returns_the_first_trusted_download() -> None:
    selected = select_wroclaw_feed_url(["/hdb/download/127/", "https://untrusted.example/hdb/download/128/"])

    assert selected == "https://open-data.cui.wroclaw.pl/hdb/download/127/"
