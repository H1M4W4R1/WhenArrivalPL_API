"""Runtime configuration and safe provider selection."""

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Settings that do not depend on a web framework."""

    database_path: Path
    providers: tuple[str, ...]
    refresh_seconds: int
    static_refresh_seconds: int


def parse_settings(arguments: Sequence[str] | None = None) -> Settings:
    """Read command-line options. Omitting --provider selects every registered provider."""
    parser = ArgumentParser(description="Reduced GTFS REST API")
    parser.add_argument("--provider", action="append", dest="providers", metavar="SLUG")
    parser.add_argument("--database", default="data/transit.sqlite3", metavar="PATH")
    parser.add_argument("--refresh-seconds", type=int, default=60, metavar="SECONDS")
    parser.add_argument("--static-refresh-seconds", type=int, default=86_400, metavar="SECONDS")
    parsed: Namespace = parser.parse_args(arguments)
    refresh_seconds = int(parsed.refresh_seconds)
    static_refresh_seconds = int(parsed.static_refresh_seconds)
    if refresh_seconds < 15 or static_refresh_seconds < refresh_seconds:
        parser.error("refresh values must be at least 15 seconds and static refresh cannot be smaller")
    supplied_providers = parsed.providers if isinstance(parsed.providers, list) else []
    return Settings(
        database_path=Path(str(parsed.database)),
        providers=tuple(str(value).lower() for value in supplied_providers),
        refresh_seconds=refresh_seconds,
        static_refresh_seconds=static_refresh_seconds,
    )
