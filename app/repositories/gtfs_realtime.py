"""GTFS-Realtime TripUpdate importer."""

import sqlite3
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2  # type: ignore[import-untyped]

_WARSAW = ZoneInfo("Europe/Warsaw")
_TRIP_ID_BATCH_SIZE = 500


def replace_realtime_delays(connection: sqlite3.Connection, provider_slug: str, payloads: Iterable[bytes]) -> None:
    """Replace delay observations with the newest protobuf TripUpdates snapshot."""
    delays: dict[tuple[str, int], int] = {}
    estimated_times: dict[tuple[str, int], int] = {}
    cancelled_trips: set[str] = set()
    skipped_stops: set[tuple[str, int]] = set()
    for payload in payloads:
        message = gtfs_realtime_pb2.FeedMessage()
        message.ParseFromString(payload)
        if not message.IsInitialized() or not message.header.gtfs_realtime_version.strip():
            raise ValueError("GTFS-Realtime feed has no valid header")
        _collect_observations(message, delays, estimated_times, cancelled_trips, skipped_stops)
    for key, delay in _delays_from_absolute_times(connection, provider_slug, estimated_times).items():
        delays.setdefault(key, delay)
    observed_at = datetime.now(UTC).isoformat()
    connection.execute("DELETE FROM realtime_delays WHERE provider_slug = ?", (provider_slug,))
    connection.execute("DELETE FROM realtime_trip_cancellations WHERE provider_slug = ?", (provider_slug,))
    connection.execute("DELETE FROM realtime_skipped_stops WHERE provider_slug = ?", (provider_slug,))
    connection.executemany(
        """INSERT INTO realtime_delays(provider_slug, trip_id, stop_sequence, delay_seconds, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        ((provider_slug, trip_id, sequence, delay, observed_at) for (trip_id, sequence), delay in delays.items()),
    )
    connection.executemany(
        "INSERT INTO realtime_trip_cancellations(provider_slug, trip_id) VALUES (?, ?)",
        ((provider_slug, trip_id) for trip_id in cancelled_trips),
    )
    connection.executemany(
        """INSERT INTO realtime_skipped_stops(provider_slug, trip_id, stop_sequence)
           VALUES (?, ?, ?)""",
        ((provider_slug, trip_id, sequence) for trip_id, sequence in skipped_stops),
    )


def _collect_observations(
    message: gtfs_realtime_pb2.FeedMessage,
    delays: dict[tuple[str, int], int],
    estimated_times: dict[tuple[str, int], int],
    cancelled_trips: set[str],
    skipped_stops: set[tuple[str, int]],
) -> None:
    """Collect direct delays and absolute predictions from one complete feed."""
    for entity in message.entity:
        if not entity.HasField("trip_update"):
            continue
        trip_id = entity.trip_update.trip.trip_id.strip()
        if not trip_id:
            continue
        if entity.trip_update.trip.schedule_relationship == gtfs_realtime_pb2.TripDescriptor.CANCELED:
            cancelled_trips.add(trip_id)
            continue
        for update in entity.trip_update.stop_time_update:
            if not update.HasField("stop_sequence"):
                continue
            key = trip_id, int(update.stop_sequence)
            if update.schedule_relationship == gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SKIPPED:
                skipped_stops.add(key)
                continue
            delay = _delay(update)
            if delay is not None:
                delays[key] = delay
                continue
            estimated_time = _estimated_time(update)
            if estimated_time is not None:
                estimated_times[key] = estimated_time


def _delays_from_absolute_times(
    connection: sqlite3.Connection, provider_slug: str, estimated_times: dict[tuple[str, int], int]
) -> dict[tuple[str, int], int]:
    """Convert absolute GTFS-Realtime stop predictions into schedule-relative delays."""
    if not estimated_times:
        return {}
    trip_ids = tuple({trip_id for trip_id, _ in estimated_times})
    local_dates = [datetime.fromtimestamp(timestamp, _WARSAW).date() for timestamp in estimated_times.values()]
    earliest_date = min(local_dates) - timedelta(days=1)
    latest_date = max(local_dates) + timedelta(days=1)
    candidates: dict[tuple[str, int], tuple[float, int]] = {}
    for trip_id_batch in _batches(trip_ids, _TRIP_ID_BATCH_SIZE):
        placeholders = ", ".join("?" for _ in trip_id_batch)
        rows = connection.execute(
            """SELECT d.trip_id, d.stop_sequence, d.scheduled_seconds, sd.service_date
               FROM departures AS d
               JOIN service_dates AS sd ON sd.provider_slug = d.provider_slug AND sd.service_id = d.service_id
               WHERE d.provider_slug = ? AND d.trip_id IN ("""
            f"{placeholders}) AND sd.service_date BETWEEN ? AND ?",
            (provider_slug, *trip_id_batch, earliest_date.isoformat(), latest_date.isoformat()),
        )
        for row in rows:
            key = str(row["trip_id"]), int(row["stop_sequence"])
            predicted_time = estimated_times.get(key)
            if predicted_time is None:
                continue
            scheduled_time = _scheduled_timestamp(str(row["service_date"]), int(row["scheduled_seconds"]))
            distance = abs(predicted_time - scheduled_time)
            candidate = candidates.get(key)
            if candidate is None or distance < candidate[0]:
                candidates[key] = distance, scheduled_time
    return {key: estimated_times[key] - scheduled_time for key, (_, scheduled_time) in candidates.items()}


def _batches(values: tuple[str, ...], size: int) -> Iterable[tuple[str, ...]]:
    """Yield non-empty fixed-size tuples without relying on Python-version-specific helpers."""
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _scheduled_timestamp(service_date: str, scheduled_seconds: int) -> int:
    """Return the absolute timestamp for a Poland GTFS scheduled stop time."""
    scheduled_date = date.fromisoformat(service_date)
    scheduled = datetime.combine(scheduled_date, time.min, tzinfo=_WARSAW) + timedelta(seconds=scheduled_seconds)
    return int(scheduled.timestamp())


def _delay(update: gtfs_realtime_pb2.TripUpdate.StopTimeUpdate) -> int | None:
    if update.HasField("departure") and update.departure.HasField("delay"):
        return int(update.departure.delay)
    if update.HasField("arrival") and update.arrival.HasField("delay"):
        return int(update.arrival.delay)
    return None


def _estimated_time(update: gtfs_realtime_pb2.TripUpdate.StopTimeUpdate) -> int | None:
    """Return an absolute departure or arrival prediction when supplied."""
    if update.HasField("departure") and update.departure.HasField("time"):
        return int(update.departure.time)
    if update.HasField("arrival") and update.arrival.HasField("time"):
        return int(update.arrival.time)
    return None
