# IOT Open API

Reduced FastAPI/SQLite transit data for embedded clients. Data is kept per provider
and uses public GTFS sources. Gdańsk uses ZTM's official static GTFS, GTFS-RT Trip
Updates, and ticket-machine feed. Municipal feeds are sourced from
[mkuran.pl/gtfs](https://mkuran.pl/gtfs/) where available, otherwise from their
official provider endpoints. Kraków's three official archives are merged under the
single `krakow` provider.

## Run

1. Create a virtual environment and install the project: `python -m pip install -e .`
2. Start only the small Gdańsk test provider: `iot-open-api --provider gdansk`
3. Start every registered provider: `iot-open-api`

Static GTFS is fetched at startup and then every 24 hours by default. GTFS-RT delays
and machine data refresh every 60 seconds. Change these values with
`--refresh-seconds` and `--static-refresh-seconds` (minimum refresh is 15 seconds).

`app/secrets.py` is gitignored and intentionally empty. A future provider requiring
an API key must read it from that file and report itself disabled when its key is blank.

## Endpoints

- `GET /health`
- `GET /transit`
- `GET /transit/{provider}/stops?query=Wrzeszcz`
- `GET /transit/{provider}/stops/{url-encoded-stop-name}`
- `GET /transit/{provider}/ticketing/machines`
- `GET /transit/{provider}/schedule/{url-encoded-stop-name}/{count}`
- `GET /transit/{provider}/schedule/{count}`

The stop-name route returns only case-insensitive fuzzy name matches. Schedule stop
matching tries a case-insensitive exact name first, then fuzzy matching only when no
exact stop exists. The schedule response includes the `stop_name`, `scheduled_at`,
`estimated_at`, and `delay_seconds`; it is ordered by ascending delay, then scheduled
time. Invalid GTFS calendar dates are rejected, while valid GTFS after-midnight times
are kept.

## Validation

`python -m pytest && ruff check . && mypy app`
