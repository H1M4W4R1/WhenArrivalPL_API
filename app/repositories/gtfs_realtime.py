"""GTFS-Realtime TripUpdate importer."""

import sqlite3
from datetime import UTC, datetime

from google.transit import gtfs_realtime_pb2  # type: ignore[import-untyped]


def replace_realtime_delays(connection: sqlite3.Connection, provider_slug: str, payload: bytes) -> None:
    """Replace delay observations with the newest protobuf TripUpdates snapshot."""
    message = gtfs_realtime_pb2.FeedMessage()
    message.ParseFromString(payload)
    observed_at = datetime.now(UTC).isoformat()
    rows: list[tuple[str, str, int, int, str]] = []
    for entity in message.entity:
        if not entity.HasField("trip_update"):
            continue
        trip_id = entity.trip_update.trip.trip_id.strip()
        if not trip_id:
            continue
        for update in entity.trip_update.stop_time_update:
            if not update.HasField("stop_sequence"):
                continue
            delay = _delay(update)
            if delay is not None:
                rows.append((provider_slug, trip_id, update.stop_sequence, delay, observed_at))
    connection.execute("DELETE FROM realtime_delays WHERE provider_slug = ?", (provider_slug,))
    connection.executemany(
        """INSERT INTO realtime_delays(provider_slug, trip_id, stop_sequence, delay_seconds, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        rows,
    )


def _delay(update: gtfs_realtime_pb2.TripUpdate.StopTimeUpdate) -> int | None:
    if update.HasField("departure") and update.departure.HasField("delay"):
        return int(update.departure.delay)
    if update.HasField("arrival") and update.arrival.HasField("delay"):
        return int(update.arrival.delay)
    return None
