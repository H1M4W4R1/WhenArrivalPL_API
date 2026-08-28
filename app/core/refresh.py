"""Periodic provider refresh orchestration."""

import asyncio
import json
import logging
import sqlite3
import tempfile
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from urllib.request import Request, urlopen

from app.core.database import Database
from app.providers.base import TransitProvider
from app.repositories.gtfs_realtime import replace_realtime_delays
from app.repositories.gtfs_static import append_static_feed_from_payload, replace_static_feed_from_payload
from app.repositories.ticket_machines import replace_ticket_machines

LOGGER = logging.getLogger(__name__)
# Warsaw's public GTFS archive exceeds 100 MiB. Keep a finite limit because source
# URLs are trusted configuration, but never accept an unbounded response.
_MAX_STATIC_BYTES = 250 * 1024 * 1024
_MAX_AUXILIARY_BYTES = 10 * 1024 * 1024
_STATIC_WORKER_COUNT = 2


class RefreshService:
    """Refreshes static data sparingly and real-time overlays every cycle."""

    def __init__(
        self,
        database: Database,
        providers: list[TransitProvider],
        static_refresh_seconds: int,
    ) -> None:
        self._database = database
        self._providers = providers
        self._static_refresh_interval = timedelta(seconds=static_refresh_seconds)

    async def refresh_all(self) -> None:
        """Refresh all configured providers without one failure stopping the others."""
        for provider in self._providers:
            self._ensure_provider(provider)
        await self._refresh_static_feeds()
        for provider in self._providers:
            try:
                await asyncio.to_thread(self._refresh_auxiliary_data, provider)
            except Exception:
                LOGGER.exception("Refresh failed for provider %s", provider.slug)

    async def _refresh_static_feeds(self) -> None:
        due_providers = [provider for provider in self._providers if self._static_refresh_due(provider.slug)]
        if not due_providers:
            return
        loop = asyncio.get_running_loop()
        with (
            tempfile.TemporaryDirectory(prefix="iot-open-api-static-") as directory,
            ProcessPoolExecutor(max_workers=min(_STATIC_WORKER_COUNT, len(due_providers))) as executor,
        ):
            tasks = []
            for provider in due_providers:
                try:
                    static_urls = await asyncio.to_thread(provider.static_feed_urls)
                except Exception:
                    LOGGER.exception("Could not resolve static feed URL for provider %s", provider.slug)
                    continue
                tasks.append(
                    loop.run_in_executor(
                        executor,
                        _build_static_database,
                        provider.slug,
                        provider.city,
                        static_urls,
                        str(Path(directory) / f"{provider.slug}.sqlite3"),
                    )
                )
            for task in asyncio.as_completed(tasks):
                try:
                    provider_slug, staged_path = await task
                    await asyncio.to_thread(self._install_static_database, provider_slug, Path(staged_path))
                except Exception:
                    LOGGER.exception("Static refresh failed")

    def _refresh_auxiliary_data(self, provider: TransitProvider) -> None:
        if provider.trip_updates_url is not None:
            realtime_payload = _download(provider.trip_updates_url, _MAX_AUXILIARY_BYTES)
            with self._database.connection() as connection:
                replace_realtime_delays(connection, provider.slug, realtime_payload)
                connection.execute(
                    "UPDATE providers SET realtime_updated_at = ? WHERE slug = ?",
                    (datetime.now(UTC).isoformat(), provider.slug),
                )
        if provider.ticket_machines_url is not None:
            machines_payload = _download(provider.ticket_machines_url, _MAX_AUXILIARY_BYTES)
            machines_document = json.loads(machines_payload)
            with self._database.connection() as connection:
                replace_ticket_machines(connection, provider.slug, machines_document)

    def _install_static_database(self, provider_slug: str, staged_path: Path) -> None:
        """Atomically copy one completed worker database into the shared API database."""
        with self._database.connection() as connection:
            connection.execute("ATTACH DATABASE ? AS staged", (str(staged_path),))
            for table_name in ("stops", "service_dates", "departures", "realtime_delays"):
                connection.execute(f"DELETE FROM {table_name} WHERE provider_slug = ?", (provider_slug,))
            _copy_staged_rows(connection, "stops", provider_slug)
            _copy_staged_rows(connection, "service_dates", provider_slug)
            _copy_staged_rows(connection, "departures", provider_slug)
            connection.execute(
                "UPDATE providers SET static_updated_at = ? WHERE slug = ?",
                (datetime.now(UTC).isoformat(), provider_slug),
            )

    def _ensure_provider(self, provider: TransitProvider) -> None:
        with self._database.connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO providers(slug, city) VALUES (?, ?)",
                (provider.slug, provider.city),
            )

    def _static_refresh_due(self, provider_slug: str) -> bool:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT static_updated_at FROM providers WHERE slug = ?", (provider_slug,)
            ).fetchone()
        if row is None or row["static_updated_at"] is None:
            return True
        try:
            last_updated = datetime.fromisoformat(row["static_updated_at"])
        except ValueError:
            return True
        return datetime.now(UTC) - last_updated.astimezone(UTC) >= self._static_refresh_interval


def _build_static_database(
    provider_slug: str,
    city: str,
    static_urls: tuple[str, ...],
    database_path: str,
) -> tuple[str, str]:
    """Build one provider database in a separate process before it is published."""
    if not static_urls:
        raise ValueError(f"Provider {provider_slug} has no static GTFS URL")
    database = Database(Path(database_path))
    database.initialize()
    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES (?, ?)", (provider_slug, city))
        for index, static_url in enumerate(static_urls):
            static_payload = _download(static_url, _MAX_STATIC_BYTES)
            if index == 0:
                replace_static_feed_from_payload(connection, provider_slug, static_payload)
            else:
                append_static_feed_from_payload(connection, provider_slug, static_payload)
    return provider_slug, database_path


def _copy_staged_rows(connection: sqlite3.Connection, table_name: str, provider_slug: str) -> None:
    """Copy a known provider-scoped table from a worker database without dynamic input."""
    columns = {
        "stops": "provider_slug, stop_id, stop_name, stop_code, latitude, longitude",
        "service_dates": "provider_slug, service_id, service_date",
        "departures": (
            "provider_slug, trip_id, stop_id, stop_sequence, service_id, scheduled_seconds, route_name, destination"
        ),
    }
    selected_columns = columns[table_name]
    connection.execute(
        f"INSERT INTO {table_name}({selected_columns}) "
        f"SELECT {selected_columns} FROM staged.{table_name} WHERE provider_slug = ?",
        (provider_slug,),
    )


def _download(url: str, maximum_size: int) -> bytes:
    """Download a bounded HTTPS/HTTP public feed with a fixed timeout."""
    request = Request(url, headers={"User-Agent": "IOTOpenAPI/0.1"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - URLs are source-controlled providers.
        content_length = response.headers.get("Content-Length")
        if content_length is not None and int(content_length) > maximum_size:
            raise ValueError(f"Feed exceeds maximum size: {url}")
        payload = cast(bytes, response.read(maximum_size + 1))
    if len(payload) > maximum_size:
        raise ValueError(f"Feed exceeds maximum size: {url}")
    return payload
