"""Defensive GTFS static ZIP importer."""

import csv
import io
import sqlite3
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.stop_name import normalize_stop_name

_INSERT_BATCH_SIZE = 5_000


@dataclass(frozen=True, slots=True)
class StaticFeed:
    """Normalised data extracted from one GTFS static archive."""

    stops: tuple[tuple[str, str, str | None, float | None, float | None], ...]
    service_dates: tuple[tuple[str, str], ...]
    departures: tuple[tuple[str, str, int, str, int, str | None, str | None], ...]


def parse_static_feed(payload: bytes) -> StaticFeed:
    """Parse supported GTFS files, discarding malformed dates and times safely."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        stops = tuple(_parse_stops(_read_csv(archive, "stops.txt")))
        trips = _trips(_read_csv(archive, "trips.txt"), _routes(_read_csv(archive, "routes.txt")))
        service_dates = tuple(_service_dates(archive))
        departures = tuple(_departures(_read_csv(archive, "stop_times.txt"), trips))
    return StaticFeed(stops=stops, service_dates=service_dates, departures=departures)


def replace_static_feed(connection: sqlite3.Connection, provider_slug: str, feed: StaticFeed) -> None:
    """Atomically replace a provider's schedule while retaining independent metadata."""
    for table_name in (
        "stops",
        "service_dates",
        "departures",
        "realtime_delays",
        "realtime_trip_cancellations",
        "realtime_skipped_stops",
    ):
        connection.execute(f"DELETE FROM {table_name} WHERE provider_slug = ?", (provider_slug,))
    connection.executemany(
        """INSERT INTO stops(provider_slug, stop_id, stop_name, stop_code, latitude, longitude)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ((provider_slug, *item) for item in feed.stops),
    )
    connection.executemany(
        "INSERT INTO service_dates(provider_slug, service_id, service_date) VALUES (?, ?, ?)",
        ((provider_slug, *item) for item in feed.service_dates),
    )
    connection.executemany(
        """INSERT INTO departures(provider_slug, trip_id, stop_id, stop_sequence, service_id,
           scheduled_seconds, route_name, destination) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ((provider_slug, *item) for item in feed.departures),
    )


def replace_static_feed_from_payload(connection: sqlite3.Connection, provider_slug: str, payload: bytes) -> None:
    """Replace static data while streaming a large stop-time CSV file in bounded batches."""
    _delete_static_feed(connection, provider_slug)
    append_static_feed_from_payload(connection, provider_slug, payload)


def append_static_feed_from_payload(connection: sqlite3.Connection, provider_slug: str, payload: bytes) -> None:
    """Append one schedule archive to a provider without materialising stop times."""
    connection.execute("PRAGMA temp_store = FILE")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        routes = _routes(_iter_csv(archive, "routes.txt"))
        _stage_trips(connection, _iter_csv(archive, "trips.txt"), routes)
        stops = tuple(_parse_stops(_iter_csv(archive, "stops.txt")))
        service_dates = tuple(_service_dates(archive))
        connection.executemany(
            """INSERT OR REPLACE INTO stops(provider_slug, stop_id, stop_name, stop_code, latitude, longitude)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ((provider_slug, *item) for item in stops),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO service_dates(provider_slug, service_id, service_date) VALUES (?, ?, ?)",
            ((provider_slug, *item) for item in service_dates),
        )
        _insert_departures(connection, provider_slug, _iter_csv(archive, "stop_times.txt"))


def _delete_static_feed(connection: sqlite3.Connection, provider_slug: str) -> None:
    for table_name in (
        "stops",
        "service_dates",
        "departures",
        "realtime_delays",
        "realtime_trip_cancellations",
        "realtime_skipped_stops",
    ):
        connection.execute(f"DELETE FROM {table_name} WHERE provider_slug = ?", (provider_slug,))


def _stage_trips(connection: sqlite3.Connection, rows: Iterable[Mapping[str, str]], routes: Mapping[str, str]) -> None:
    connection.execute("DROP TABLE IF EXISTS gtfs_import_trips")
    connection.execute(
        """CREATE TEMP TABLE gtfs_import_trips (
               trip_id TEXT PRIMARY KEY,
               service_id TEXT NOT NULL,
               route_name TEXT NOT NULL,
               destination TEXT
           ) WITHOUT ROWID"""
    )
    batch: list[tuple[str, str, str, str | None]] = []
    for row in rows:
        trip_id = row.get("trip_id", "").strip()
        service_id = row.get("service_id", "").strip()
        route_id = row.get("route_id", "").strip()
        if trip_id and service_id:
            batch.append(
                (trip_id, service_id, routes.get(route_id) or route_id, _optional_text(row.get("trip_headsign")))
            )
        if len(batch) >= _INSERT_BATCH_SIZE:
            _insert_trip_batch(connection, batch)
            batch.clear()
    if batch:
        _insert_trip_batch(connection, batch)


def _insert_trip_batch(connection: sqlite3.Connection, batch: list[tuple[str, str, str, str | None]]) -> None:
    connection.executemany(
        """INSERT OR REPLACE INTO gtfs_import_trips(trip_id, service_id, route_name, destination)
           VALUES (?, ?, ?, ?)""",
        batch,
    )


def _insert_departures(connection: sqlite3.Connection, provider_slug: str, rows: Iterable[Mapping[str, str]]) -> None:
    batch: list[tuple[str, str, int, int]] = []
    for row in rows:
        item = _stop_time_item(row)
        if item is not None:
            batch.append(item)
        if len(batch) >= _INSERT_BATCH_SIZE:
            _insert_departure_batch(connection, provider_slug, batch)
            batch.clear()
    if batch:
        _insert_departure_batch(connection, provider_slug, batch)


def _stop_time_item(row: Mapping[str, str]) -> tuple[str, str, int, int] | None:
    trip_id = row.get("trip_id", "").strip()
    stop_id = row.get("stop_id", "").strip()
    sequence = _integer_or_none(row.get("stop_sequence"))
    scheduled_seconds = _time_seconds_or_none(row.get("departure_time"))
    if not trip_id or not stop_id or sequence is None or scheduled_seconds is None:
        return None
    return trip_id, stop_id, sequence, scheduled_seconds


def _insert_departure_batch(
    connection: sqlite3.Connection, provider_slug: str, batch: list[tuple[str, str, int, int]]
) -> None:
    trip_ids = tuple({item[0] for item in batch})
    placeholders = ", ".join("?" for _ in trip_ids)
    trip_rows = connection.execute(
        """SELECT trip_id, service_id, route_name, destination
           FROM gtfs_import_trips WHERE trip_id IN ("""
        f"{placeholders})",
        trip_ids,
    )
    trips = {
        str(row["trip_id"]): (
            str(row["service_id"]),
            str(row["route_name"]),
            str(row["destination"]) if row["destination"] is not None else None,
        )
        for row in trip_rows
    }
    departures = (
        (provider_slug, trip_id, stop_id, sequence, *trip, scheduled_seconds)
        for trip_id, stop_id, sequence, scheduled_seconds in batch
        if (trip := trips.get(trip_id)) is not None
    )
    connection.executemany(
        """INSERT OR REPLACE INTO departures(provider_slug, trip_id, stop_id, stop_sequence, service_id,
           route_name, destination, scheduled_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        departures,
    )


def _read_csv(archive: zipfile.ZipFile, filename: str) -> list[dict[str, str]]:
    return list(_iter_csv(archive, filename))


def _iter_csv(archive: zipfile.ZipFile, filename: str) -> Iterator[dict[str, str]]:
    try:
        with archive.open(filename) as raw_file:
            text_file = io.TextIOWrapper(raw_file, encoding="utf-8-sig", newline="")
            yield from (dict(row) for row in csv.DictReader(text_file))
    except KeyError as error:
        raise ValueError(f"GTFS archive lacks required {filename}") from error


def _parse_stops(
    rows: Iterable[Mapping[str, str]],
) -> Iterable[tuple[str, str, str | None, float | None, float | None]]:
    for row in rows:
        stop_id = row.get("stop_id", "").strip()
        name = normalize_stop_name(row.get("stop_name", ""))
        if stop_id and name:
            yield (
                stop_id,
                name,
                _optional_text(row.get("stop_code")),
                _float_or_none(row.get("stop_lat")),
                _float_or_none(row.get("stop_lon")),
            )


def _routes(rows: Iterable[Mapping[str, str]]) -> dict[str, str]:
    return {
        route_id: _first_text(row.get("route_short_name"), row.get("route_long_name")) or route_id
        for row in rows
        if (route_id := row.get("route_id", "").strip())
    }


def _trips(rows: Iterable[Mapping[str, str]], routes: Mapping[str, str]) -> dict[str, tuple[str, str, str | None]]:
    result: dict[str, tuple[str, str, str | None]] = {}
    for row in rows:
        trip_id = row.get("trip_id", "").strip()
        service_id = row.get("service_id", "").strip()
        route_id = row.get("route_id", "").strip()
        if trip_id and service_id:
            result[trip_id] = (
                service_id,
                routes.get(route_id) or route_id,
                _optional_text(row.get("trip_headsign")),
            )
    return result


def _service_dates(archive: zipfile.ZipFile) -> Iterable[tuple[str, str]]:
    try:
        calendar_rows = _read_csv(archive, "calendar.txt")
    except ValueError:
        calendar_rows = []
    active_dates: dict[str, set[date]] = defaultdict(set)
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    for row in calendar_rows:
        service_id = row.get("service_id", "").strip()
        start = _date_or_none(row.get("start_date"))
        end = _date_or_none(row.get("end_date"))
        if not service_id or start is None or end is None or end < start:
            continue
        for offset in range((end - start).days + 1):
            candidate = start + timedelta(days=offset)
            if row.get(weekdays[candidate.weekday()], "0") == "1":
                active_dates[service_id].add(candidate)
    try:
        exceptions = _read_csv(archive, "calendar_dates.txt")
    except ValueError:
        exceptions = []
    for row in exceptions:
        service_id = row.get("service_id", "").strip()
        exception_date = _date_or_none(row.get("date"))
        if not service_id or exception_date is None:
            continue
        if row.get("exception_type") == "1":
            active_dates[service_id].add(exception_date)
        elif row.get("exception_type") == "2":
            active_dates[service_id].discard(exception_date)
    for service_id, dates in active_dates.items():
        for service_date in dates:
            yield service_id, service_date.isoformat()


def _departures(
    rows: Iterable[Mapping[str, str]], trips: Mapping[str, tuple[str, str, str | None]]
) -> Iterable[tuple[str, str, int, str, int, str | None, str | None]]:
    for row in rows:
        trip_id = row.get("trip_id", "").strip()
        stop_id = row.get("stop_id", "").strip()
        sequence = _integer_or_none(row.get("stop_sequence"))
        scheduled_seconds = _time_seconds_or_none(row.get("departure_time"))
        trip = trips.get(trip_id)
        if trip is not None and stop_id and sequence is not None and scheduled_seconds is not None:
            service_id, route_name, destination = trip
            yield trip_id, stop_id, sequence, service_id, scheduled_seconds, route_name, destination


def _date_or_none(value: str | None) -> date | None:
    if value is None or len(value) != 8 or not value.isdigit():
        return None
    try:
        parsed = date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None
    return parsed if 2000 <= parsed.year <= 2100 else None


def _time_seconds_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    pieces = value.strip().split(":")
    if len(pieces) != 3 or not all(piece.isdigit() for piece in pieces):
        return None
    hour, minute, second = (int(piece) for piece in pieces)
    if hour > 47 or minute > 59 or second > 59:
        return None
    return hour * 3600 + minute * 60 + second


def _integer_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _float_or_none(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _optional_text(value: str | None) -> str | None:
    return value.strip() if value is not None and value.strip() else None


def _first_text(*values: str | None) -> str | None:
    for value in values:
        text = _optional_text(value)
        if text is not None:
            return text
    return None
