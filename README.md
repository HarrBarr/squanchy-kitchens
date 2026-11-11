# Squanchy Kitchens

Fridge temperature logs for Squanchy Bakery. Summer uploads the weekly raw logger files.
The app standardises them, flags sensor errors, gaps and real warming events, and answers
the Ministry of Health question: **when did this fridge go above 5°C, and for how long?**

- **Dashboard:** every fridge as a red / amber / green card, built for a phone.
- **Fridge chart:** temperature with the 5°C line. Gaps show as gaps and are never joined
  with a line. Door-opening spikes and sensor errors are marked.
- **Inspector report:** every excursion with start, end, duration, peak and readings. It
  exports to CSV and has a print layout.
- **Logger registry:** which logger is in which fridge, since when, in °C or °F. Summer can
  record a move herself.

There is no LLM and no agent workflow. Stack: FastAPI + SQLAlchemy + Alembic, MySQL 8,
Angular 22 + Angular Material + ECharts, all in Docker Compose.

## Run it (only Docker needed)

You need Docker Desktop, or Docker Engine 24+ with Compose v2. You do not need Python, Node
or MySQL on the host, and there is no `.env` step.

```bash
git clone https://github.com/HarrBarr/squanchy-kitchens.git
cd squanchy-kitchens
docker compose up --build
```

If you don't have Git, download the ZIP from GitHub, unzip it, `cd` into the folder and run
the same command.

Open **http://localhost:8080**. On the first start the API waits for MySQL, runs the
migrations and seeds the logger registry from `data/loggers.csv`. It then imports the mock
week in `data/mock-logger-files/` (2026-W38, 14–20 Sep 2026). The dashboard should show
**three red fridges**:

| Fridge | What happened |
|---|---|
| Rishon LeZion / Cream cakes | Died Monday 06:15 and never recovered. **Ongoing**, peak 11.5°C |
| Be'er Sheva / Dairy | Slow two-day drift from Wednesday 13:45. **Ongoing**, peak 9.4°C |
| Ashdod / Dairy | Power cut Wednesday 03:00–04:00, 60 min, peak 7.4°C, recovered |

Three fridges are amber. Beit Shemesh Dairy has a 10-hour battery gap, Jerusalem Dairy a
2 h 15 min gap, and Haifa Dairy four `ERR` readings. Everything else is green, including the
Tel Aviv door-opening spikes.

To start empty and upload files yourself:

```bash
SEED_DEMO_DATA=false docker compose up --build     # or: make up-empty
```

MySQL's port 3306 is **not** published, so it can't clash with a MySQL already on your
machine. The only published port is 8080. The OpenAPI docs are at
http://localhost:8080/api/docs.

## Uploading a file

Click **Upload**, pick a raw export and confirm the logger. If the file name contains the
code, e.g. `TL-0512_2026-W38.csv`, the logger is pre-selected and you can change it. The
import summary lists new, duplicate and updated readings, sensor errors, gaps and
excursions, plus any warnings.

- An **identical file** (same SHA-256) is a no-op and returns "already imported".
- A **corrected file** updates the overlapping readings (the latest file wins) and the
  excursions are recomputed. Every original file is kept on disk for audit.
- An **unknown logger** (try `TL-9999_2026-W38.csv`) gets a 422 with a message pointing to
  the Logger registry. Nothing is written. Add the logger there and upload again.

## Tests (in containers)

```bash
make test
# = docker compose run --rm api pytest
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --no-deps web npx ng test --watch=false
```

- **Backend:** 70 pytest tests. They cover the parser (every format family and the
  sample-table pins), timezone/DST and °F conversion, the rules engine, ingest (duplicates,
  out-of-order rows, idempotency, unknown logger, the TL-0417 move) and the API (colours,
  report, CSV, registry). They also include the **golden test**
  [`backend/tests/test_excursions_golden.py`](backend/tests/test_excursions_golden.py), which
  imports the whole mock week and compares the result with
  [`data/expected_excursions.json`](data/expected_excursions.json).
  Inside Compose the tests create a throwaway schema `squanchy_kitchens_test` on the
  `mysql` service as root, migrate it with Alembic and drop it afterwards. The demo database
  is never touched. On a host without `TEST_DATABASE_URL`, the same tests run against a
  temporary SQLite file (`cd backend && pytest`).
- **Frontend:** 18 Vitest tests in the Node `dev` image. They cover the card colour helper,
  filename → logger, the upload dialog (submit stays disabled until a file and a logger are
  chosen), the chart breaking at gaps and `ERR`, and empty-state smoke tests for each route.

## Development (hot reload, still only Docker)

```bash
make dev   # docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- UI at http://localhost:4200 (`ng serve`, proxying `/api` to `api:8000`)
- API at http://localhost:8000/api/docs (uvicorn `--reload`, `./backend` bind-mounted)

| Command | What it does |
|---|---|
| `make up` / `make up-empty` | Demo mode, with or without the mock week |
| `make dev` | Hot-reload dev mode |
| `make seed-demo` | Import the mock week into a running stack (idempotent) |
| `make test` | Backend + frontend tests in containers |
| `make lint` / `make fmt` | ruff + mypy, prettier |
| `make reset-db` | `down -v` then `up` (**deletes** MySQL data and stored uploads) |

Every setting has a default in `docker-compose.yml` (`${VAR:-default}`). `.env.example`
lists them in case you want to override one. The alert rules are configurable:
`ALERT_THRESHOLD_C=5.0`, `SAMPLE_INTERVAL_MINUTES=15`, `MIN_EXCURSION_READINGS=2`.

## How it works

```
web (nginx :8080) ──/api──▶ api (FastAPI :8000) ──▶ mysql (8.4, named volume)
   Angular SPA                parse → normalise → upsert → recompute rules
```

1. **Parse** (`backend/app/parsing/`). Sniffs the delimiter (`,` `;` tab) and skips device
   preamble lines (`Serial:`, `Units: F`…). It finds the time and temperature columns by
   header name, so reversed `Temp,Time` works, and falls back to guessing from the values
   when there is no header. Accepted timestamps are `YYYY-MM-DD HH:MM[:SS]`, ISO `T` and
   day-first `DD/MM/YYYY`. `ERR` and garbage cells are kept as sensor errors when the
   timestamp is valid.
2. **Normalise** (`backend/app/normalize.py`). Timestamps are read as Asia/Jerusalem with
   `zoneinfo` (DST-correct) and stored in UTC next to the local wall-clock time. The **unit
   comes from the registry assignment**, never from the size of the value. The fridge is the
   one the logger was assigned to at that moment, so TL-0417's mid-week move splits its file
   across two fridges.
3. **Store** (`backend/app/ingest.py`). The original file and its SHA-256 are kept.
   Readings upsert on `(logger_id, ts_utc)`.
4. **Rules** (`backend/app/rules.py`). Two or more consecutive readings strictly above
   5.0°C make an excursion. A single one is a spike, which is shown but is not an alert.
   `ERR`, a hole longer than 15 minutes, or a logger move breaks a run. Duration is the last
   minus the first reading of the run. Gaps are reported separately.

The full planning document is
[`squanchy-kitchens-development.md`](squanchy-kitchens-development.md). Decisions and open
questions are in [`NOTES.md`](NOTES.md). The mock data and its scenarios are in
[`data/mock-logger-files/SCENARIOS.md`](data/mock-logger-files/SCENARIOS.md).
