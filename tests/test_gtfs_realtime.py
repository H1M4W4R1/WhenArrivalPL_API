"""GTFS-Realtime TripUpdates importer tests."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2  # type: ignore[import-untyped]

from app.core.database import Database
from app.repositories.gtfs_realtime import replace_realtime_delays


def test_imports_delay_from_absolute_prediction_time(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    scheduled_at = datetime(2026, 8, 28, 9, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
    message = _trip_update("T1", 1)
    message.entity[0].trip_update.stop_time_update[0].departure.time = int(scheduled_at.timestamp()) + 180

    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('test', 'Test')")
        connection.execute("INSERT INTO service_dates VALUES ('test', 'weekday', '2026-08-28')")
        connection.execute("INSERT INTO departures VALUES ('test', 'T1', 'S1', 1, 'weekday', 32400, '1', NULL)")
        replace_realtime_delays(connection, "test", (message.SerializeToString(),))
        row = connection.execute(
            "SELECT delay_seconds FROM realtime_delays WHERE provider_slug = 'test' AND trip_id = 'T1'"
        ).fetchone()

    assert row is not None and row["delay_seconds"] == 180


def test_imports_all_configured_feed_snapshots(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    first = _trip_update("A", 1)
    first.entity[0].trip_update.stop_time_update[0].departure.delay = 60
    second = _trip_update("B", 2)
    second.entity[0].trip_update.stop_time_update[0].arrival.delay = 120

    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('test', 'Test')")
        replace_realtime_delays(connection, "test", (first.SerializeToString(), second.SerializeToString()))
        rows = connection.execute(
            """SELECT trip_id, stop_sequence, delay_seconds
               FROM realtime_delays WHERE provider_slug = 'test' ORDER BY trip_id"""
        ).fetchall()

    assert [tuple(row) for row in rows] == [("A", 1, 60), ("B", 2, 120)]


def test_imports_cancelled_trips_and_skipped_stops(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    cancelled = _trip_update("cancelled", 1)
    cancelled.entity[0].trip_update.trip.schedule_relationship = gtfs_realtime_pb2.TripDescriptor.CANCELED
    skipped = _trip_update("skipped", 2)
    skipped.entity[0].trip_update.stop_time_update[
        0
    ].schedule_relationship = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SKIPPED

    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('test', 'Test')")
        replace_realtime_delays(connection, "test", (cancelled.SerializeToString(), skipped.SerializeToString()))
        cancelled_rows = connection.execute("SELECT trip_id FROM realtime_trip_cancellations").fetchall()
        skipped_rows = connection.execute("SELECT trip_id, stop_sequence FROM realtime_skipped_stops").fetchall()

    assert [tuple(row) for row in cancelled_rows] == [("cancelled",)]
    assert [tuple(row) for row in skipped_rows] == [("skipped", 2)]


def _trip_update(trip_id: str, stop_sequence: int) -> gtfs_realtime_pb2.FeedMessage:
    """Build one complete GTFS-Realtime TripUpdates feed."""
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    entity = message.entity.add()
    entity.id = trip_id
    update = entity.trip_update
    update.trip.trip_id = trip_id
    update.stop_time_update.add().stop_sequence = stop_sequence
    return message
