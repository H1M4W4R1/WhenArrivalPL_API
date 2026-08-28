"""Read queries shaped for low-bandwidth clients."""

import sqlite3
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.departure_model import DepartureModel
from app.models.stop_model import StopModel
from app.models.ticket_machine_model import TicketMachineModel

_WARSAW = ZoneInfo("Europe/Warsaw")


def stops(connection: sqlite3.Connection, provider_slug: str, query: str | None) -> list[StopModel]:
    """Return stops, optionally narrowed by a case-insensitive name fragment."""
    if query:
        rows = connection.execute(
            """SELECT stop_id, stop_name, latitude, longitude, stop_code FROM stops
               WHERE provider_slug = ? AND stop_name LIKE ? COLLATE NOCASE
               ORDER BY stop_name, stop_id LIMIT 500""",
            (provider_slug, f"%{query.strip()}%"),
        ).fetchall()
    else:
        rows = connection.execute(
            """SELECT stop_id, stop_name, latitude, longitude, stop_code FROM stops
               WHERE provider_slug = ? ORDER BY stop_name, stop_id LIMIT 5000""",
            (provider_slug,),
        ).fetchall()
    return [
        StopModel(
            id=row["stop_id"],
            name=row["stop_name"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            code=row["stop_code"],
        )
        for row in rows
    ]


def ticket_machines(connection: sqlite3.Connection, provider_slug: str) -> list[TicketMachineModel]:
    """Return ticket machine positions in stable order."""
    rows = connection.execute(
        """SELECT machine_id, machine_name, machine_type, latitude, longitude FROM ticket_machines
           WHERE provider_slug = ? ORDER BY machine_name, machine_id""",
        (provider_slug,),
    ).fetchall()
    return [
        TicketMachineModel(
            id=row["machine_id"],
            name=row["machine_name"],
            machine_type=row["machine_type"],
            latitude=row["latitude"],
            longitude=row["longitude"],
        )
        for row in rows
    ]


def schedule(
    connection: sqlite3.Connection, provider_slug: str, stop_name: str | None, count: int, now: datetime | None = None
) -> list[DepartureModel]:
    """Return active departures, using an exact stop match before a fuzzy fallback."""
    current = now.astimezone(_WARSAW) if now is not None else datetime.now(_WARSAW)
    service_date = current.date()
    previous_service_date = service_date - timedelta(days=1)
    today_seconds = _seconds_since_midnight(current)
    rows = connection.execute(
        """SELECT d.trip_id, s.stop_name, d.scheduled_seconds, d.route_name, d.destination,
                  COALESCE(rt.delay_seconds, 0) AS delay_seconds, sd.service_date
           FROM departures AS d
           JOIN stops AS s ON s.provider_slug = d.provider_slug AND s.stop_id = d.stop_id
           JOIN service_dates AS sd ON sd.provider_slug = d.provider_slug AND sd.service_id = d.service_id
           LEFT JOIN realtime_delays AS rt ON rt.provider_slug = d.provider_slug
               AND rt.trip_id = d.trip_id AND rt.stop_sequence = d.stop_sequence
           WHERE d.provider_slug = ?
               AND (
                   ? IS NULL
                   OR s.stop_name = ? COLLATE NOCASE
                   OR (
                       NOT EXISTS (
                           SELECT 1 FROM stops AS exact_stop
                           WHERE exact_stop.provider_slug = ?
                               AND exact_stop.stop_name = ? COLLATE NOCASE
                       )
                       AND s.stop_name LIKE ? COLLATE NOCASE
                   )
               )
               AND ((sd.service_date = ? AND d.scheduled_seconds >= ?)
                    OR (sd.service_date = ? AND d.scheduled_seconds >= 86400))
           ORDER BY delay_seconds ASC, d.scheduled_seconds ASC LIMIT ?""",
        (
            provider_slug,
            stop_name,
            stop_name,
            provider_slug,
            stop_name,
            f"%{stop_name}%" if stop_name is not None else None,
            service_date.isoformat(),
            today_seconds,
            previous_service_date.isoformat(),
            count,
        ),
    ).fetchall()
    result: list[DepartureModel] = []
    for row in rows:
        departure_date = date_from_isoformat(row["service_date"])
        scheduled_at = datetime.combine(departure_date, time.min, tzinfo=_WARSAW) + timedelta(
            seconds=row["scheduled_seconds"]
        )
        result.append(
            DepartureModel(
                trip_id=row["trip_id"],
                stop_name=row["stop_name"],
                route=row["route_name"],
                destination=row["destination"],
                scheduled_at=scheduled_at,
                estimated_at=scheduled_at + timedelta(seconds=row["delay_seconds"]),
                delay_seconds=row["delay_seconds"],
            )
        )
    return result


def date_from_isoformat(value: str) -> date:
    """Parse schema-controlled ISO dates without accepting ambiguous values."""
    return datetime.fromisoformat(f"{value}T00:00:00").date()


def _seconds_since_midnight(value: datetime) -> int:
    return value.hour * 3600 + value.minute * 60 + value.second
