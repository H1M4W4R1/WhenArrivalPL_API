"""Reduced transit-query tests."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.database import Database
from app.repositories.transit_queries import schedule, stops


def test_schedule_is_ordered_by_nearest_estimated_time_and_contains_estimated_time(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('gdansk', 'Gdańsk')")
        connection.execute("INSERT INTO stops VALUES ('gdansk', 'S1', 'Central', NULL, NULL, NULL)")
        connection.execute("INSERT INTO service_dates VALUES ('gdansk', 'weekday', '2026-08-28')")
        connection.execute("INSERT INTO departures VALUES ('gdansk', 'T1', 'S1', 1, 'weekday', 32460, '6', 'Harbour')")
        connection.execute("INSERT INTO departures VALUES ('gdansk', 'T2', 'S1', 1, 'weekday', 32520, '6', 'Airport')")
        connection.execute("INSERT INTO realtime_delays VALUES ('gdansk', 'T1', 1, 30, '2026-08-28T09:00:00+00:00')")
        result = schedule(
            connection,
            "gdansk",
            "Central",
            10,
            datetime(2026, 8, 28, 9, 0, tzinfo=ZoneInfo("Europe/Warsaw")),
        )

    assert [departure.trip_id for departure in result] == ["T1", "T2"]
    assert result[0].delay_seconds == 30
    assert result[0].estimated_at.minute == 1


def test_schedule_uses_fuzzy_stop_name_only_when_an_exact_name_is_absent(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('gdansk', 'Gdańsk')")
        connection.execute("INSERT INTO stops VALUES ('gdansk', 'S1', 'Main Station', NULL, NULL, NULL)")
        connection.execute("INSERT INTO stops VALUES ('gdansk', 'S2', 'Main Station North', NULL, NULL, NULL)")
        connection.execute("INSERT INTO service_dates VALUES ('gdansk', 'weekday', '2026-08-28')")
        connection.execute("INSERT INTO departures VALUES ('gdansk', 'T1', 'S1', 1, 'weekday', 32460, '6', 'Harbour')")
        connection.execute("INSERT INTO departures VALUES ('gdansk', 'T2', 'S2', 1, 'weekday', 32520, '6', 'Airport')")
        now = datetime(2026, 8, 28, 9, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
        exact_result = schedule(connection, "gdansk", "main station", 10, now)
        fuzzy_result = schedule(connection, "gdansk", "station north", 10, now)
        provider_result = schedule(connection, "gdansk", None, 1, now)

    assert [departure.trip_id for departure in exact_result] == ["T1"]
    assert exact_result[0].stop_name == "Main Station"
    assert [departure.trip_id for departure in fuzzy_result] == ["T2"]
    assert len(provider_result) == 1


def test_schedule_excludes_passed_overnight_departures_from_the_previous_service_date(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('gdansk', 'Gdańsk')")
        connection.execute("INSERT INTO stops VALUES ('gdansk', 'S1', 'Central', NULL, NULL, NULL)")
        connection.execute("INSERT INTO service_dates VALUES ('gdansk', 'weekday', '2026-08-27')")
        connection.execute("INSERT INTO departures VALUES ('gdansk', 'T1', 'S1', 1, 'weekday', 90000, '6', 'Past')")
        connection.execute("INSERT INTO departures VALUES ('gdansk', 'T2', 'S1', 1, 'weekday', 97200, '6', 'Upcoming')")
        result = schedule(
            connection,
            "gdansk",
            "Central",
            10,
            datetime(2026, 8, 28, 2, 0, tzinfo=ZoneInfo("Europe/Warsaw")),
        )

    assert [departure.trip_id for departure in result] == ["T2"]


def test_stops_search_returns_only_fuzzy_name_matches(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('gdansk', 'Gdańsk')")
        connection.execute("INSERT INTO stops VALUES ('gdansk', 'S1', 'Main Station', NULL, NULL, NULL)")
        connection.execute("INSERT INTO stops VALUES ('gdansk', 'S2', 'Airport', NULL, NULL, NULL)")
        result = stops(connection, "gdansk", "station")

    assert [stop.id for stop in result] == ["S1"]


def test_stop_search_matches_polish_letters_regardless_of_case(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('polish-trains', 'Polskie koleje')")
        connection.execute("INSERT INTO stops VALUES ('polish-trains', 'S1', 'Mława', NULL, NULL, NULL)")
        result = stops(connection, "polish-trains", "MŁAWA")

    assert [(stop.id, stop.name) for stop in result] == [("S1", "Mława")]


def test_schedule_matches_polish_letters_regardless_of_case(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('polish-trains', 'Polskie koleje')")
        connection.execute("INSERT INTO stops VALUES ('polish-trains', 'S1', 'Mława', NULL, NULL, NULL)")
        connection.execute("INSERT INTO service_dates VALUES ('polish-trains', 'weekday', '2026-08-28')")
        connection.execute(
            "INSERT INTO departures VALUES ('polish-trains', 'T1', 'S1', 1, 'weekday', 32460, 'IC', 'Warszawa')"
        )
        result = schedule(
            connection,
            "polish-trains",
            "MŁAWA",
            10,
            datetime(2026, 8, 28, 9, 0, tzinfo=ZoneInfo("Europe/Warsaw")),
        )

    assert [departure.trip_id for departure in result] == ["T1"]


def test_stop_lists_group_positions_and_schedule_uses_the_normalized_name(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('gdansk', 'Gdańsk')")
        connection.execute("INSERT INTO stops VALUES ('gdansk', 'S1', 'Main Station 01', NULL, NULL, NULL)")
        connection.execute("INSERT INTO stops VALUES ('gdansk', 'S2', 'Main Station 02', NULL, NULL, NULL)")
        connection.execute("INSERT INTO stops VALUES ('gdansk', 'S3', 'Main Station North 01', NULL, NULL, NULL)")
        connection.execute("INSERT INTO service_dates VALUES ('gdansk', 'weekday', '2026-08-28')")
        connection.execute("INSERT INTO departures VALUES ('gdansk', 'T1', 'S1', 1, 'weekday', 32460, '6', 'Harbour')")
        connection.execute("INSERT INTO departures VALUES ('gdansk', 'T2', 'S2', 1, 'weekday', 32520, '6', 'Airport')")
        connection.execute("INSERT INTO departures VALUES ('gdansk', 'T3', 'S3', 1, 'weekday', 32580, '6', 'North')")
    database.initialize()

    with database.connection() as connection:
        stop_result = stops(connection, "gdansk", "main station")
        schedule_result = schedule(
            connection,
            "gdansk",
            "Main Station 01",
            10,
            datetime(2026, 8, 28, 9, 0, tzinfo=ZoneInfo("Europe/Warsaw")),
        )

    assert [(stop.id, stop.name) for stop in stop_result] == [
        ("S1", "Main Station"),
        ("S3", "Main Station North"),
    ]
    assert [departure.trip_id for departure in schedule_result] == ["T1", "T2"]
    assert {departure.stop_name for departure in schedule_result} == {"Main Station"}
