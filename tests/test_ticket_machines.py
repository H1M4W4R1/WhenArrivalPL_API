"""Ticket-machine normalisation tests."""

from pathlib import Path

from app.core.database import Database
from app.repositories.ticket_machines import replace_ticket_machines
from app.repositories.transit_queries import ticket_machines


def test_machine_list_is_normalised(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    with database.connection() as connection:
        connection.execute("INSERT INTO providers(slug, city) VALUES ('gdansk', 'Gdańsk')")
        replace_ticket_machines(
            connection,
            "gdansk",
            {"machines": [{"id": 7, "location": "Main station", "lat": "54.3", "lon": "18.6", "type": "cash"}]},
        )
        result = ticket_machines(connection, "gdansk")

    assert result[0].id == "7"
    assert result[0].latitude == 54.3
