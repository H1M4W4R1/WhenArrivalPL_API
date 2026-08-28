"""GTFS static importer tests."""

import io
import zipfile
from pathlib import Path

from app.core.database import Database
from app.repositories.gtfs_static import (
    append_static_feed_from_payload,
    parse_static_feed,
    replace_static_feed_from_payload,
)


def test_skips_invalid_dates_and_keeps_gtfs_after_midnight_times() -> None:
    payload = _feed_zip(
        {
            "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nS1,Central,54.0,18.0\n",
            "routes.txt": "route_id,route_short_name\nR1,6\n",
            "trips.txt": "route_id,service_id,trip_id,trip_headsign\nR1,good,T1,Harbour\n",
            "calendar.txt": (
                "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                "good,1,1,1,1,1,1,1,20260828,20260828\n"
                "bad,1,1,1,1,1,1,1,00260828,20260828\n"
            ),
            "stop_times.txt": "trip_id,stop_id,stop_sequence,departure_time\nT1,S1,1,25:10:00\n",
        }
    )

    parsed = parse_static_feed(payload)

    assert parsed.service_dates == (("good", "2026-08-28"),)
    assert parsed.departures[0][4] == 90_600


def test_streaming_import_populates_database_without_materialising_stop_times(tmp_path: Path) -> None:
    payload = _feed_zip(
        {
            "stops.txt": "stop_id,stop_name\nS1,Central\n",
            "routes.txt": "route_id,route_short_name\nR1,6\n",
            "trips.txt": "route_id,service_id,trip_id,trip_headsign\nR1,weekday,T1,Harbour\n",
            "calendar_dates.txt": "service_id,date,exception_type\nweekday,20260828,1\n",
            "stop_times.txt": (
                "trip_id,stop_id,stop_sequence,departure_time\n"
                "T1,S1,1,09:01:00\n"
                "unknown,S1,2,09:02:00\n"
                "T1,S1,invalid,09:03:00\n"
            ),
        }
    )
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()

    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('warsaw', 'Warszawa')")
        replace_static_feed_from_payload(connection, "warsaw", payload)
        stops = connection.execute("SELECT stop_id, stop_name FROM stops WHERE provider_slug = 'warsaw'").fetchall()
        service_dates = connection.execute(
            "SELECT service_id, service_date FROM service_dates WHERE provider_slug = 'warsaw'"
        ).fetchall()
        departures = connection.execute(
            """SELECT trip_id, stop_id, stop_sequence, service_id, scheduled_seconds, route_name, destination
               FROM departures WHERE provider_slug = 'warsaw'"""
        ).fetchall()

    assert [tuple(row) for row in stops] == [("S1", "Central")]
    assert [tuple(row) for row in service_dates] == [("weekday", "2026-08-28")]
    assert [tuple(row) for row in departures] == [("T1", "S1", 1, "weekday", 32_460, "6", "Harbour")]


def test_streaming_import_merges_multiple_static_archives(tmp_path: Path) -> None:
    first_payload = _feed_zip(
        {
            "stops.txt": "stop_id,stop_name\nS1,Central\n",
            "routes.txt": "route_id,route_short_name\nR1,1\n",
            "trips.txt": "route_id,service_id,trip_id\nR1,weekday,T1\n",
            "calendar_dates.txt": "service_id,date,exception_type\nweekday,20260828,1\n",
            "stop_times.txt": "trip_id,stop_id,stop_sequence,departure_time\nT1,S1,1,09:01:00\n",
        }
    )
    second_payload = _feed_zip(
        {
            "stops.txt": "stop_id,stop_name\nS2,Harbour\n",
            "routes.txt": "route_id,route_short_name\nR2,2\n",
            "trips.txt": "route_id,service_id,trip_id\nR2,weekend,T2\n",
            "calendar_dates.txt": "service_id,date,exception_type\nweekend,20260829,1\n",
            "stop_times.txt": "trip_id,stop_id,stop_sequence,departure_time\nT2,S2,1,10:01:00\n",
        }
    )
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()

    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('krakow', 'Kraków')")
        replace_static_feed_from_payload(connection, "krakow", first_payload)
        append_static_feed_from_payload(connection, "krakow", second_payload)
        stops = connection.execute(
            "SELECT stop_id FROM stops WHERE provider_slug = 'krakow' ORDER BY stop_id"
        ).fetchall()
        departures = connection.execute(
            "SELECT trip_id FROM departures WHERE provider_slug = 'krakow' ORDER BY trip_id"
        ).fetchall()

    assert [tuple(row) for row in stops] == [("S1",), ("S2",)]
    assert [tuple(row) for row in departures] == [("T1",), ("T2",)]


def _feed_zip(files: dict[str, str]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
    return stream.getvalue()
