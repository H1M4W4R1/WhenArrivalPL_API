"""Wrocław's current GTFS archive, resolved from its official catalog."""

import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from app.providers.base import TransitProvider

_CATALOG_URL = "https://open-data.cui.wroclaw.pl/hdb/ft/6/"
_ALLOWED_HOST = "open-data.cui.wroclaw.pl"
_DOWNLOAD_PATH = re.compile(r"/hdb/download/\d+/?")


class WroclawProvider(TransitProvider):
    """Wrocław schedule feed with a rotating official download URL."""

    slug = "wroclaw"
    city = "Wrocław"
    static_url = _CATALOG_URL

    def static_feed_urls(self) -> tuple[str, ...]:
        """Resolve the first current GTFS archive from the official catalog."""
        request = Request(_CATALOG_URL, headers={"User-Agent": "IOTOpenAPI/0.1"})
        with urlopen(request, timeout=30) as response:  # noqa: S310 - source-controlled catalog URL.
            document = response.read().decode("utf-8", errors="replace")
        return (_select_current_feed_url(_DOWNLOAD_PATH.findall(document)),)


def _select_current_feed_url(candidates: list[str]) -> str:
    """Return the first trusted archive URL in catalog display order."""
    for candidate in candidates:
        resolved = urljoin(_CATALOG_URL, candidate)
        parsed = urlparse(resolved)
        if parsed.scheme == "https" and parsed.hostname == _ALLOWED_HOST and _DOWNLOAD_PATH.fullmatch(parsed.path):
            return resolved
    raise ValueError("Wrocław catalog does not contain a valid GTFS archive")
