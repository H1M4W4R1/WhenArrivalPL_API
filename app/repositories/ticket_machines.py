"""Ticket-machine JSON normalisation."""

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any


def replace_ticket_machines(
    connection: sqlite3.Connection, provider_slug: str, document: object
) -> None:
    """Replace provider machines from a documented or bare JSON collection."""
    records = _records(document)
    rows: list[tuple[str, str, str, str | None, float | None, float | None]] = []
    for index, record in enumerate(records):
        identifier = _text(record, "id", "machine_id", "identifier", "number") or str(index + 1)
        name = _text(record, "name", "machine_name", "location", "address") or identifier
        rows.append(
            (
                provider_slug,
                identifier,
                name,
                _machine_type(record),
                _number(record, "latitude", "lat", "y"),
                _number(record, "longitude", "lon", "lng", "x"),
            )
        )
    connection.execute("DELETE FROM ticket_machines WHERE provider_slug = ?", (provider_slug,))
    connection.executemany(
        """INSERT INTO ticket_machines(provider_slug, machine_id, machine_name, machine_type,
           latitude, longitude) VALUES (?, ?, ?, ?, ?, ?)""",
        rows,
    )


def _records(document: object) -> Sequence[Mapping[str, Any]]:
    if isinstance(document, list):
        return [item for item in document if isinstance(item, Mapping)]
    if isinstance(document, Mapping):
        for key in ("data", "machines", "ticket_machines", "results"):
            candidate = document.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, Mapping)]
    return []


def _text(record: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _number(record: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _machine_type(record: Mapping[str, Any]) -> str | None:
    direct_type = _text(record, "type", "machine_type", "device_type")
    if direct_type is not None:
        return direct_type
    payment_methods = record.get("paymentMethods", record.get("payment_methods"))
    if isinstance(payment_methods, list):
        methods = [str(method).strip() for method in payment_methods if str(method).strip()]
        return ", ".join(methods) if methods else None
    return None
