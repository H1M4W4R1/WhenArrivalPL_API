"""Olsztyn's dated GTFS archive catalog."""

import re
from datetime import date
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from app.providers.base import TransitProvider

_CATALOG_URL = "https://zdzit.olsztyn.eu/gtfs/"
_ALLOWED_HOST = "zdzit.olsztyn.eu"
_FEED_PATH = re.compile(r"/wp-content/uploads/\d{4}/\d{2}/GTFS_(\d{4})_(\d{2})_(\d{2})-(\d{2})_(\d{2})\.zip")


class OlsztynProvider(TransitProvider):
    """Olsztyn schedule feed selected from its validity-dated official catalog."""

    slug = "olsztyn"
    city = "Olsztyn"
    static_url = _CATALOG_URL

    def static_feed_urls(self) -> tuple[str, ...]:
        """Resolve the newest trusted archive whose validity includes today."""
        request = Request(_CATALOG_URL, headers={"User-Agent": "IOTOpenAPI/0.1"})
        with urlopen(request, timeout=30) as response:  # noqa: S310 - source-controlled catalog URL.
            document = response.read().decode("utf-8", errors="replace")
        candidates = re.findall(r"https?://[^\"'\s>]+|/wp-content/[^\"'\s>]+", document)
        return (_select_current_feed_url(candidates, date.today()),)


def _select_current_feed_url(candidates: list[str], current_date: date) -> str:
    """Return the newest trusted archive that covers the requested date."""
    valid_feeds: list[tuple[date, str]] = []
    for candidate in candidates:
        resolved = urljoin(_CATALOG_URL, candidate)
        parsed = urlparse(resolved)
        match = _FEED_PATH.fullmatch(parsed.path)
        if parsed.scheme != "https" or parsed.hostname != _ALLOWED_HOST or match is None:
            continue
        start_date = date(int(match[1]), int(match[2]), int(match[3]))
        end_year = start_date.year + (int(match[4]) < start_date.month)
        end_date = date(end_year, int(match[4]), int(match[5]))
        if start_date <= current_date <= end_date:
            valid_feeds.append((start_date, resolved))
    if not valid_feeds:
        raise ValueError("Olsztyn catalog does not contain a valid current GTFS archive")
    return max(valid_feeds)[1]
