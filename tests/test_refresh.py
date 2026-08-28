"""Refresh worker installation tests."""

from pathlib import Path

from app.core.database import Database
from app.core.refresh import RefreshService


def test_completed_worker_database_is_installed_atomically(tmp_path: Path) -> None:
    target = Database(tmp_path / "target.sqlite3")
    staged = Database(tmp_path / "staged.sqlite3")
    target.initialize()
    staged.initialize()
    with target.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('warsaw', 'Warszawa')")
        connection.execute("INSERT INTO stops VALUES ('warsaw', 'old', 'Old stop', NULL, NULL, NULL)")
        connection.execute("INSERT INTO realtime_delays VALUES ('warsaw', 'T1', 1, 60, '2026-08-28T00:00:00+00:00')")
    with staged.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('warsaw', 'Warszawa')")
        connection.execute("INSERT INTO stops VALUES ('warsaw', 'S1', 'Central', NULL, NULL, NULL)")
        connection.execute("INSERT INTO service_dates VALUES ('warsaw', 'weekday', '2026-08-28')")
        connection.execute("INSERT INTO departures VALUES ('warsaw', 'T1', 'S1', 1, 'weekday', 32460, '6', 'Harbour')")

    RefreshService(target, [], 86_400)._install_static_database("warsaw", tmp_path / "staged.sqlite3")

    with target.connection() as connection:
        stops = connection.execute("SELECT stop_id FROM stops WHERE provider_slug = 'warsaw'").fetchall()
        departures = connection.execute("SELECT trip_id FROM departures WHERE provider_slug = 'warsaw'").fetchall()
        realtime_delays = connection.execute(
            "SELECT trip_id FROM realtime_delays WHERE provider_slug = 'warsaw'"
        ).fetchall()
        updated_at = connection.execute(
            "SELECT static_updated_at FROM providers WHERE slug = 'warsaw'"
        ).fetchone()

    assert [tuple(row) for row in stops] == [("S1",)]
    assert [tuple(row) for row in departures] == [("T1",)]
    assert realtime_delays == []
    assert updated_at is not None and updated_at[0] is not None
