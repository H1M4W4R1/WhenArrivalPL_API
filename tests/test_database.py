"""SQLite connection configuration tests."""

from pathlib import Path
from threading import Event, Thread

from app.core.database import Database


def test_initialize_enables_wal_and_configures_busy_timeout(tmp_path: Path) -> None:
    """API readers can continue while a refresh transaction writes."""
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()

    with database.connection() as connection:
        journal_mode_row = connection.execute("PRAGMA journal_mode").fetchone()
        busy_timeout_row = connection.execute("PRAGMA busy_timeout").fetchone()

    assert journal_mode_row is not None and journal_mode_row[0] == "wal"
    assert busy_timeout_row is not None and busy_timeout_row[0] == 30_000


def test_write_connections_are_serialized(tmp_path: Path) -> None:
    """Concurrent refresh jobs cannot start competing write transactions."""
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    first_writer_started = Event()
    release_first_writer = Event()
    second_writer_started = Event()

    def hold_first_writer() -> None:
        with database.write_connection():
            first_writer_started.set()
            assert release_first_writer.wait(timeout=2.0)

    def start_second_writer() -> None:
        with database.write_connection():
            second_writer_started.set()

    first_thread = Thread(target=hold_first_writer)
    second_thread = Thread(target=start_second_writer)
    first_thread.start()
    assert first_writer_started.wait(timeout=2.0)
    second_thread.start()
    assert not second_writer_started.wait(timeout=0.1)
    release_first_writer.set()
    first_thread.join(timeout=2.0)
    second_thread.join(timeout=2.0)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert second_writer_started.is_set()
