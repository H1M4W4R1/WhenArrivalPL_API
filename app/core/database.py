"""Small SQLite access layer with parameterised queries only."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.core.stop_name import casefold_text, normalize_stop_name


class Database:
    """Creates short-lived SQLite connections safe for FastAPI worker threads."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a transaction-capable connection and close it deterministically."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.create_function("normalized_stop_name", 1, normalize_stop_name, deterministic=True)
        connection.create_function("casefold_text", 1, casefold_text, deterministic=True)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the local schema when it does not already exist."""
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS providers (
                    slug TEXT PRIMARY KEY,
                    city TEXT NOT NULL,
                    static_updated_at TEXT,
                    realtime_updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS stops (
                    provider_slug TEXT NOT NULL,
                    stop_id TEXT NOT NULL,
                    stop_name TEXT NOT NULL,
                    stop_code TEXT,
                    latitude REAL,
                    longitude REAL,
                    PRIMARY KEY (provider_slug, stop_id),
                    FOREIGN KEY (provider_slug) REFERENCES providers(slug) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS stops_provider_name ON stops(provider_slug, stop_name);
                CREATE TABLE IF NOT EXISTS service_dates (
                    provider_slug TEXT NOT NULL,
                    service_id TEXT NOT NULL,
                    service_date TEXT NOT NULL,
                    PRIMARY KEY (provider_slug, service_id, service_date)
                );
                CREATE INDEX IF NOT EXISTS service_dates_lookup ON service_dates(provider_slug, service_date);
                CREATE TABLE IF NOT EXISTS departures (
                    provider_slug TEXT NOT NULL,
                    trip_id TEXT NOT NULL,
                    stop_id TEXT NOT NULL,
                    stop_sequence INTEGER NOT NULL,
                    service_id TEXT NOT NULL,
                    scheduled_seconds INTEGER NOT NULL,
                    route_name TEXT,
                    destination TEXT,
                    PRIMARY KEY (provider_slug, trip_id, stop_id, stop_sequence)
                );
                CREATE INDEX IF NOT EXISTS departures_stop ON departures(provider_slug, stop_id, scheduled_seconds);
                CREATE TABLE IF NOT EXISTS realtime_delays (
                    provider_slug TEXT NOT NULL,
                    trip_id TEXT NOT NULL,
                    stop_sequence INTEGER NOT NULL,
                    delay_seconds INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider_slug, trip_id, stop_sequence)
                );
                CREATE TABLE IF NOT EXISTS realtime_trip_cancellations (
                    provider_slug TEXT NOT NULL,
                    trip_id TEXT NOT NULL,
                    PRIMARY KEY (provider_slug, trip_id)
                );
                CREATE TABLE IF NOT EXISTS realtime_skipped_stops (
                    provider_slug TEXT NOT NULL,
                    trip_id TEXT NOT NULL,
                    stop_sequence INTEGER NOT NULL,
                    PRIMARY KEY (provider_slug, trip_id, stop_sequence)
                );
                CREATE TABLE IF NOT EXISTS ticket_machines (
                    provider_slug TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    machine_name TEXT NOT NULL,
                    machine_type TEXT,
                    latitude REAL,
                    longitude REAL,
                    PRIMARY KEY (provider_slug, machine_id)
                );
                """
            )
            connection.execute(
                """UPDATE stops SET stop_name = normalized_stop_name(stop_name)
                   WHERE stop_name != normalized_stop_name(stop_name)"""
            )
