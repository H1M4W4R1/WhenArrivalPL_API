# IOT Open API

Reduced FastAPI/SQLite transit data for embedded clients. It exposes static GTFS schedules, with GTFS-Realtime TripUpdates applied where a configured feed supports them.

## Run

1. Create a virtual environment and install the project: `python -m pip install -e .`
2. Start the small Gdańsk test provider: `iot-open-api --provider gdansk`
3. Start every registered provider: `iot-open-api`

The server listens on `http://0.0.0.0:8000`. Interactive OpenAPI documentation is available at `/docs`; the OpenAPI JSON document is at `/openapi.json`.

Static GTFS is fetched at startup and then every 24 hours by default. GTFS-RT TripUpdates and ticket-machine data refresh every 60 seconds. Change these values with `--refresh-seconds` and `--static-refresh-seconds`; the minimum refresh period is 15 seconds and the static period cannot be shorter than the regular refresh period.

Useful options:

| Option | Default | Meaning |
| --- | --- | --- |
| `--provider SLUG` | all providers | Load only one provider. Repeat the option to load several providers. |
| `--database PATH` | `data/transit.sqlite3` | SQLite database location. |
| `--refresh-seconds SECONDS` | `60` | GTFS-RT and ticket-machine refresh interval. |
| `--static-refresh-seconds SECONDS` | `86400` | Static GTFS refresh interval. |

`app/secrets.py` is gitignored and intentionally empty. A future provider requiring an API key must read it from that file and report itself disabled when its key is blank.

## API

All responses are JSON. Provider slugs come from `GET /transit`. Unknown provider slugs return `404` with `{"detail":"Unknown transit provider"}`. Invalid path and query values return FastAPI's standard `422` validation response.

| Method and path | Parameters | Response | Notes |
| --- | --- | --- | --- |
| `GET /health` | — | `{ "status": "ok", "providers": 25 }` | `providers` is the number configured for this server, not always 25. |
| `GET /status` | — | `[{ "slug", "city", "status", "progress" }]` | Refresh state for each configured provider. `city` is the full city name; `progress` is from `0.0` to `1.0`. |
| `GET /transit` | — | `[{ "slug", "city", "enabled", "has_realtime" }]` | Lists active configured providers. `has_realtime` means a GTFS-RT TripUpdates feed is configured. |
| `GET /transit/{provider}/stops` | optional `query` (1–100 characters) | `[{ "id", "name", "latitude", "longitude", "code" }]` | Lists up to 5,000 stops; with `query`, returns up to 500 case-insensitive name matches. |
| `GET /transit/{provider}/stops/{stop_name}` | URL-encoded `stop_name` (1–100 characters) | `[{ "id", "name", "latitude", "longitude", "code" }]` | Case-insensitive partial-name search, limited to 500 matches. |
| `GET /transit/{provider}/ticketing/machines` | — | `[{ "id", "name", "latitude", "longitude", "machine_type" }]` | Returns an empty list when the provider has no machine feed. Only Gdańsk currently has one. |
| `GET /transit/{provider}/schedule/{count}` | `count` (1–100) | `[{ "trip_id", "stop_name", "route", "destination", "scheduled_at", "estimated_at", "delay_seconds" }]` | Next departures across the provider. |
| `GET /transit/{provider}/schedule/{stop_name}/{count}` | URL-encoded `stop_name` (1–150 characters); `count` (1–100) | `[{ "trip_id", "stop_name", "route", "destination", "scheduled_at", "estimated_at", "delay_seconds" }]` | Next departures at a stop. An exact case-insensitive name match takes precedence; otherwise a partial-name match is used. |

Schedule times are ISO 8601 datetimes in the `Europe/Warsaw` time zone. `estimated_at` equals `scheduled_at + delay_seconds`. For static-only providers, `delay_seconds` is `0`; a GTFS-RT feed can also report cancelled trips and skipped stops, which are omitted. Results are ordered by lowest delay first and then scheduled time.

Stop names omit a trailing two-digit GTFS boarding-position suffix, such as `Abrahama 01` becoming `Abrahama`. This groups physical platforms into one stop for stop lists and lets schedule lookups use the human-readable name.

Example requests:

```text
GET /transit
GET /transit/gdansk/stops?query=Wrzeszcz
GET /transit/gdansk/schedule/Wrzeszcz%20PKP/10
GET /status
```

`/status` values are `pending`, `valid`, `downloading_delays`, `updating_delays`, `downloading_schedule`, `updating_schedule`, `downloading_ticket_machines`, `updating_ticket_machines`, or `failed`.

## Feed support

The table below is derived from the registered provider definitions: a feed supports GTFS-RT when its provider has at least one configured `trip_updates_url`. All feeds provide static GTFS.

| Slug | Feed / city | GTFS-RT TripUpdates |
| --- | --- | --- |
| `bialystok` | Białystok | No |
| `bydgoszcz` | Bydgoszcz | No |
| `elk` | Ełk | Yes |
| `elblag` | Elbląg | No |
| `gdansk` | Gdańsk | Yes |
| `gdynia` | Gdynia | No |
| `gizycko` | Giżycko | No |
| `gorzow-wlkp` | Gorzów Wielkopolski | No |
| `gzm` | Górnośląsko-Zagłębiowska Metropolia | No |
| `kielce` | Kielce | No |
| `krakow` | Kraków | No |
| `lomza` | Łomża | No |
| `lublin` | Lublin | No |
| `olsztyn` | Olsztyn | No |
| `polish-trains` | Polskie koleje | Yes |
| `poznan` | Poznań | No |
| `radom` | Radom | No |
| `rzeszow` | Rzeszów | No |
| `szczecin` | Szczecin | Yes |
| `swinoujscie` | Świnoujście | No |
| `torun` | Toruń | No |
| `warsaw` | Warszawa | No |
| `wejherowo` | Wejherowo | No |
| `wkd` | Warszawska Kolej Dojazdowa | Yes |
| `wroclaw` | Wrocław | No |

## Validation

```text
python -m pytest && ruff check . && mypy app
```
