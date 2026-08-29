"""Shared GTFS stop-name normalisation."""

import re

_POSITION_SUFFIX = re.compile(r"\s+\d{2}$")


def normalize_stop_name(value: str) -> str:
    """Remove a GTFS two-digit boarding-position suffix from a stop name."""
    return _POSITION_SUFFIX.sub("", value.strip())


def casefold_text(value: str | None) -> str | None:
    """Return a Unicode-aware case-insensitive comparison value."""
    return value.casefold() if value is not None else None
