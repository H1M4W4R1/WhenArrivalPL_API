"""Shared GTFS stop-name normalisation."""

import re

_POSITION_SUFFIX = re.compile(r"\s+\d{2}$")


def normalize_stop_name(value: str) -> str:
    """Remove a GTFS two-digit boarding-position suffix from a stop name."""
    return _POSITION_SUFFIX.sub("", value.strip())
