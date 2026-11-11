# Squanchy Kitchens: Development Guide

This guide covers everything needed to run, develop and test **Squanchy Kitchens**, a containerised full-stack app for Squanchy Bakery. Operations manager Summer Smith uploads weekly temperature-logger files. The app standardises them, flags sensor errors, gaps and genuine warming events, and answers the Ministry of Health question: *when did this fridge go above 5°C, and for how long?*

There is no LLM and no agentic workflow. The only future-looking idea we considered — automatically reading the files out of Summer's inbox — is listed under "what's next" and is not in scope.

The official command is `docker compose up` (there is no `--up` flag). Reviewers should get from a clone or a zip download to a running app in a few minutes, with no accounts, no paid services, and nothing except Docker installed on the host.

---

## 1. Prerequisites

### 1.1 Required to run the demo (reviewers)

**The only thing needed on the host is Docker.** That means Docker Desktop, or Docker Engine 24+ with Compose v2 (the `docker compose` plugin, bundled with Desktop). No Python, no Node.js, no Angular CLI, no MySQL, and no other stack component should be installed on the machine. MySQL, the FastAPI backend and the Angular UI all build and run inside Compose. MySQL is the official `mysql:8` (or `mysql:8.4`) image, with a healthcheck and a named volume; it is never installed on the host and its port is not published in the demo compose file.

Git is optional. You can `git clone` the public repository, or download the ZIP from GitHub and unzip it. Either way, the next command is `docker compose up --build`.

| Dependency | Version | Purpose |
|---|---|---|
| Docker Desktop, or Docker Engine 24+ with Compose v2 | Engine 24+ / Compose 2.20+ | Builds and runs MySQL, the API and the web UI. Compose v2 is bundled with Docker Desktop. |

No API keys, cloud accounts or paid services. Compose already carries laptop-safe defaults (`${VAR:-default}`), so a `.env` file is not required. Create one only if you want to override a default (see §4).

Optional: 2 GB of free RAM is comfortable (MySQL 8 + the API + nginx). The mock week is ~20,000 readings, so disk use is small.

### 1.2 Optional: host tools for local development

You do **not** need these to run, develop or test the app. The supported path is container-only: `docker compose up`, hot reload via `docker-compose.dev.yml`, and `docker compose run --rm api pytest` (see §7 and §8). Install the tools below only if you prefer to run the API or the Angular dev server directly on the host.

| Dependency | Version | Purpose |
|---|---|---|
| Git | 2.40+ | Optional even for reviewers: clone instead of downloading the ZIP |
| Python | 3.12 | Host-side backend (FastAPI, parser, rules engine) |
| uv (or pip + venv) | latest | Python dependency management on the host |
| Node.js | 20 LTS | Host-side Angular CLI, `ng serve`, production build |
| Angular CLI | matching the project (`ng version`) | Scaffolding and the host dev server |
| pnpm or npm | pnpm 9+ / npm 10+ | Frontend package manager if you work on the host (pick one and use it consistently) |
| MySQL client | 8.x | Optional: inspect the database if you temporarily publish `:3306` in the dev override. Do not install a host MySQL server; the database is the Compose service. |
| Make | any | Optional: shortcut commands (the Makefile itself shells out to `docker compose`) |

### 1.3 Main libraries (installed automatically, inside the images)

**Backend (`backend/pyproject.toml`)**

- `fastapi`, `uvicorn[standard]`: HTTP API and (in dev) hot reload
- `pydantic` v2, `pydantic-settings`: request/response schemas and env config
- `sqlalchemy` 2.x: ORM and query layer, sync engine
- `alembic`: schema migrations, applied automatically on API startup
- `pymysql`: MySQL driver
- `python-multipart`: multipart file uploads
- Python stdlib `csv`, `io`, `datetime`, `zoneinfo`, `hashlib`, `re`: parsing, timezones, file hashes
- `structlog` (or stdlib `logging`): structured request and import logs
- Dev: `pytest`, `pytest-asyncio` (only if any async tests appear), `httpx`, `ruff`, `mypy`

**Why `pymysql`, not `mysqlclient` or `asyncmy`:** `pymysql` is pure Python, so the API image does not need `libmysqlclient` or a compiler. Throughput is not a concern — Summer uploads one file at a time, roughly 700 rows, once a week per logger. `mysqlclient` is faster but adds native build dependencies for no practical gain here. `asyncmy` would force the whole data layer onto async SQLAlchemy, which is more moving parts than a 48-hour take-home needs. FastAPI `def` endpoints already run in a thread pool, so a sync `Session` is the straightforward fit.

**Why the stdlib `csv` module, not pandas:** the files are tiny (two columns, at most a few thousand rows) and messy in ways pandas does not help with: two or three metadata lines before the header, comma / semicolon / tab delimiters, reversed `Temp,Time` columns, `ERR` in the temperature cell, and mixed date formats. An explicit parser is easier to test and has no extra dependency. pandas would also try to type-infer `ERR` and mixed dates, which we would then have to undo.

**Frontend (`frontend/package.json`)**

- Angular (current CLI, 19 or the version `ng new` scaffolds), TypeScript
- `@angular/material`, `@angular/cdk`, `@angular/animations`: mobile-first layout, cards, table, toolbar, dialog, form fields
- `@angular/router`, `@angular/forms`, `@angular/common/http`
- `ngx-echarts` and `echarts`: fridge-detail chart (5°C reference line, visible gaps, spike markers)
- The browser tab and app toolbar title is **Squanchy Kitchens**
- Dev: the CLI default unit-test runner, ESLint, the CLI e2e option only if time remains

---

## 2. Quick start (demo mode)

```bash
git clone <repo-url> squanchy-kitchens
cd squanchy-kitchens
docker compose up --build
```

No Git? Download the repository ZIP from GitHub, unzip it, `cd squanchy-kitchens`, and run the same `docker compose up --build`. There is no `.env` step. Defaults live in `docker-compose.yml` as `${VAR:-default}` and are enough for a laptop demo.

`--build` is optional after the first run; it is worth including the first time so the Angular image is built.

Open http://localhost:8080. The page title is Squanchy Kitchens.

On first start the API waits for MySQL (the `mysql` Compose service) to be healthy, runs Alembic migrations, and seeds the logger registry from `data/loggers.csv`. If `SEED_DEMO_DATA` is true (the Compose default), it also imports the week of mock logger files under `data/mock-logger-files/`, skipping any file whose SHA-256 is already stored. The dashboard should then show all twelve branches for week 2026-W38 (14–20 September 2026), including the three planted excursions.

To start with an empty readings table and upload files yourself:

```bash
SEED_DEMO_DATA=false docker compose up --build
```

Or, later, `make seed-demo` against a running stack (idempotent).

There is no `--up` flag. The Compose command is `docker compose up`.

---

## 3. Architecture

```
squanchy-kitchens/
├── docker-compose.yml            # name: squanchy-kitchens; baked-in ${VAR:-default} values
├── docker-compose.dev.yml        # dev overrides: hot reload, bind mounts; 3306 stays unpublished unless you opt in
├── .env.example                  # optional reference of overrides; not required to run
├── Makefile
├── README.md
├── NOTES.md                      # required by the assignment
├── squanchy-kitchens-development.md
├── data/
│   ├── loggers.csv               # registry seed (logger, branch, fridge, unit, dates)
│   ├── mock-logger-files/        # realistic raw exports + SCENARIOS.md + expected_excursions.json
│   └── expected_excursions.json  # golden oracle for the rules engine
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh             # alembic upgrade, seed registry, optional demo import, then uvicorn
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   ├── app/
│   │   ├── main.py               # FastAPI app factory
│   │   ├── config.py             # pydantic-settings
│   │   ├── api/                  # routers: health, uploads, dashboard, fridges, report, registry
│   │   ├── parsing/              # delimiter, headers, columns, datetimes, ERR
│   │   ├── normalize.py          # Asia/Jerusalem → UTC, unit from registry, assignment lookup
│   │   ├── ingest.py             # hash, store original, upsert readings, recompute excursions/gaps
│   │   ├── rules.py              # spikes vs excursions, gap detection
│   │   ├── storage/              # SQLAlchemy models, session, repositories
│   │   └── bootstrap.py          # registry seed + optional demo import
│   └── tests/
└── frontend/
    ├── Dockerfile                # multi-stage: node build → nginx
    ├── nginx.conf                # SPA + proxy /api → api:8000
    ├── proxy.conf.json           # used only by `ng serve` in development
    └── src/
        ├── index.html            # page title: Squanchy Kitchens
        ├── app/
        │   ├── dashboard/        # screen 1: green / amber / red fridge cards
        │   ├── fridge-detail/    # screen 2: chart with 5°C line and gaps
        │   ├── report/           # screen 3: inspector periods + CSV export
        │   ├── upload/           # dialog: file picker + logger dropdown
        │   └── registry/         # small admin: add or end a logger assignment
        └── styles.scss           # Material theme, mobile-first typography and spacing
```

### Services (`docker-compose.yml`)

Set `name: squanchy-kitchens` at the top of the compose file so project, volume and default container prefixes stay stable even if the directory is renamed after a zip download.

| Service | Image / container | Role |
|---|---|---|
| `mysql` | official `mysql:8` (or `mysql:8.4`), container `squanchy-kitchens-mysql` | Durable store. Named volume `mysql-data`. Healthcheck (`mysqladmin ping`) before anything else starts. **Port 3306 is not published** in the demo compose file, so a MySQL already running on the host cannot collide with it. The API reaches it on the Compose network as `mysql:3306`. |
| `api` | build `backend/Dockerfile`, image `squanchy-kitchens-api`, container `squanchy-kitchens-api` | FastAPI on `:8000`. `depends_on: mysql` with `condition: service_healthy`. Entrypoint runs migrations, seeds the registry, optionally imports demo files, then uvicorn. |
| `web` | build `frontend/Dockerfile`, image `squanchy-kitchens-web`, container `squanchy-kitchens-web` | Multi-stage: Node builds the Angular app, nginx serves it on `:8080` and proxies `/api` (and `/api/docs`) to `api:8000`. |

Suggested port mapping: host `8080` → `web:80`. Publishing `8000` (OpenAPI at http://localhost:8000/docs) is optional and useful while developing; it is not required for the demo. Do not publish MySQL's `3306` unless you are in the optional host-tools workflow (§8.2) and have explicitly opted in — a local MySQL on 3306 is a common conflict.

MySQL is started with `character-set-server=utf8mb4` and `collation-server=utf8mb4_unicode_ci` so names such as `Be'er Sheva` store cleanly. A named volume holds uploaded originals at `/data/uploads`.

### Upload pipeline

```mermaid
flowchart TD
  U[Summer picks a file and a logger] --> H{SHA-256 already stored?}
  H -- yes, identical file --> DoneAlready[Return already imported, no changes]
  H -- no --> P[Parse: sniff delimiter, skip metadata, detect columns]
  P --> V{Logger in registry?}
  V -- no, e.g. TL-9999 --> Reject[422 with a clear message, nothing else is affected]
  V -- yes --> N[Normalise each row]
  N --> N1[Parse timestamp as Asia/Jerusalem, including DST]
  N1 --> N2[Convert to UTC, keep the naive local time]
  N2 --> N3[Unit from the assignment, never guessed: F becomes C]
  N3 --> N4[ERR stays a sensor error: no value, no conversion]
  N4 --> N5[Sort by time, drop exact duplicate rows]
  N5 --> A[Resolve branch and fridge from logger_assignments at that timestamp]
  A --> S[Store the original file, insert the uploads row]
  S --> W[Idempotent upsert of readings on logger_id + ts_utc]
  W --> R[Delete and recompute excursions and gaps for that logger in the affected window]
  R --> OK[200 with a summary: imported, duplicates, ERR, gaps, excursions]
```

Re-uploading a *different* file that overlaps existing timestamps updates those readings (latest file wins) and recomputes excursions. The previous original is kept on disk; the new file is stored alongside it. That is intentional: the health ministry may ask what was uploaded when.

### Data model (MySQL 8)

Database name: `squanchy_kitchens` (Compose default).

- `branches` (id, name unique). Seeded from the registry file.
- `fridges` (id, branch_id, name, unique(branch_id, name)). "Dairy", "Walk-in", "Cream cakes", "Display 1", "Display 2".
- `loggers` (id, logger_code unique, e.g. `TL-0231`). The hardware identity, independent of where it sits.
- `logger_assignments` (id, logger_id, fridge_id, unit `C`\|`F`, assigned_from date, assigned_to date nullable). An empty / null `assigned_to` means the assignment is still current. Dates are calendar dates in Asia/Jerusalem. `assigned_to` is **inclusive of that local day**: TL-0417 belongs to the Tel Aviv walk-in through 2026-09-16 23:45, and to Display 2 from 2026-09-17 00:00. A logger may have several rows over time; they must not overlap.
- `uploads` (id, logger_id, original_filename, sha256 unique, stored_path, row_count, error_count, status, started_at, finished_at, note). The SHA-256 is of the raw bytes. The original file is kept for audit.
- `readings` (id, upload_id, logger_id, fridge_id, ts_local, ts_utc, raw_value, temp_c nullable, status `ok`\|`err`, unique(logger_id, ts_utc)). `raw_value` is exactly what was in the file (`38.3`, `ERR`, …). `temp_c` is the normalised Celsius value, or null when status is `err`. `fridge_id` is resolved at ingest from the assignment in force at `ts_local`, so a mid-week logger move splits one file across two fridges.
- `excursions` (id, fridge_id, logger_id, start_utc, end_utc, start_local, end_local, duration_minutes, peak_c, n_readings, is_open). Recomputed for the affected logger after every upload. `is_open` is true when the run has not yet returned to ≤ 5.0°C (the Rishon cream-cakes fridge this week).
- `gaps` (id, fridge_id, logger_id, start_utc, end_utc, start_local, end_local, duration_minutes). Also recomputed after each upload. A gap is a hole longer than the configured sample interval between two otherwise valid rows, or between the first/last row and the expected file window only if we choose to report leading/trailing holes — default is **between readings actually present in the data**, not "this file started on Wednesday".

Useful indexes: `readings(fridge_id, ts_utc)`, `excursions(fridge_id, start_utc)`, `gaps(fridge_id, start_utc)`, `logger_assignments(logger_id, assigned_from)`.

### API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness, database ping, app version |
| GET | `/api/loggers` | Registry: logger code, current (or all) assignments, unit |
| POST | `/api/loggers/{code}/assignments` | Start a new assignment (and close the previous one). Used when Summer moves a logger. |
| GET | `/api/branches` | Branches with fridge counts |
| GET | `/api/fridges` | Fridges, optional `?branch=` |
| POST | `/api/uploads` | Multipart: `file` + `logger_id`. Returns a parse/import summary. Unknown logger → `422`. Identical SHA-256 → `200` with `already_imported: true`. |
| GET | `/api/uploads` | Upload history (filename, logger, time, counts, status) |
| GET | `/api/dashboard` | Fridge cards for a period (`from`, `to`, optional `branch`). Colour, last temp, open excursion, gap/error counts. Default period: the latest week that has data. |
| GET | `/api/fridges/{id}/series` | Readings, gaps, spikes and excursions for the chart (`from`, `to`) |
| GET | `/api/report` | Inspector list: every excursion in the period, with start, end, duration, peak, reading count, branch, fridge, logger. Filters: `from`, `to`, `branch`, `fridge`. |
| GET | `/api/report.csv` | Same list as a CSV download. PDF export is optional and only if time remains. |

OpenAPI lives at `/api/docs`. The Angular app should not need any other backend.

---

## 4. Environment variables

All of these have defaults in `docker-compose.yml` via `${VAR:-default}`. **You do not need a `.env` file to run the app.** Drop a `.env` in the project root only to override a value (Compose loads it automatically). `.env.example` is a commented reference of the same defaults, not a step in the README.

Sketch of the compose defaults (not a required local file):

```yaml
name: squanchy-kitchens

services:
  mysql:
    image: mysql:8.4
    container_name: squanchy-kitchens-mysql
    environment:
      MYSQL_DATABASE: ${MYSQL_DATABASE:-squanchy_kitchens}
      MYSQL_USER: ${MYSQL_USER:-squanchy}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:-squanchy}
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-squanchy-root}
    # no "ports:" in the demo file — do not publish 3306
    volumes:
      - mysql-data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-usquanchy", "-psquanchy"]
      interval: 5s
      timeout: 5s
      retries: 20

  api:
    image: squanchy-kitchens-api
    container_name: squanchy-kitchens-api
    environment:
      APP_ENV: ${APP_ENV:-production}
      APP_TIMEZONE: ${APP_TIMEZONE:-Asia/Jerusalem}
      DATABASE_URL: ${DATABASE_URL:-mysql+pymysql://squanchy:squanchy@mysql:3306/squanchy_kitchens?charset=utf8mb4}
      ALERT_THRESHOLD_C: ${ALERT_THRESHOLD_C:-5.0}
      SAMPLE_INTERVAL_MINUTES: ${SAMPLE_INTERVAL_MINUTES:-15}
      MIN_EXCURSION_READINGS: ${MIN_EXCURSION_READINGS:-2}
      SEED_ON_STARTUP: ${SEED_ON_STARTUP:-true}
      SEED_DEMO_DATA: ${SEED_DEMO_DATA:-true}
      SEED_REGISTRY_FILE: /data/seed/loggers.csv
      SEED_DEMO_DIR: /data/seed/mock-logger-files
      UPLOAD_DIR: ${UPLOAD_DIR:-/data/uploads}
      MAX_UPLOAD_MB: ${MAX_UPLOAD_MB:-5}
```

The `web` service image is `squanchy-kitchens-web`, container `squanchy-kitchens-web`, publishing only `8080:80`.

To turn demo seeding off without a file: `SEED_DEMO_DATA=false docker compose up --build`. To inspect MySQL from the host (optional, not the default): add a `ports: ["3306:3306"]` override in `docker-compose.dev.yml` or a one-off compose file, and be aware this will clash with a MySQL already listening on the host's 3306.

If you ever change credentials after the named volume already exists, the old MySQL data directory still has the original users — `docker compose down -v` (this deletes data) and start again, or keep the original defaults.

---

## 5. Parsing and normalisation rules

Raw logger files contain **only time and temperature**. Branch and fridge are never in the file; they come from the registry. Summer picks the logger in the upload dialog (the filename, e.g. `TL-0231_2026-W38.csv`, can pre-fill the dropdown, but she must be able to override it).

The parser has to accept every format in `data/mock-logger-files/` and fail clearly on `TL-9999_2026-W38.csv` when that logger is not registered.

### 5.1 File shape

1. **Delimiter sniffing.** Read a sample of the first non-empty lines and sniff comma, semicolon or tab. `csv.Sniffer` is a reasonable start; also accept an explicit fallback that counts the three separators on the probable header line. Do not assume comma.
2. **Metadata / preamble.** Skip leading lines that are not a header and not a data row. Real examples: `Serial: TL-0231`, `Model: LogiTemp LT-1 (legacy)`, `Units: F`, `Device Serial:`, `Firmware:`. Stop skipping when a line looks like a header (`Date,Temperature`, `Temp,Time`, `timestamp,temp_c`, `Time;Temp`, `Time Stamp,Temperature (C)`, `Logged At,Temperature C`, `datetime,temperature`, …) or like the first data row.
3. **Column detection.** Identify the time column and the temperature column by header name first (`time`, `date`, `timestamp`, `logged at`, `datetime` vs `temp`, `temperature`). If the header is `Temp,Time`, the columns are reversed — do not assume left = time. If there is no header, guess from values (a parseable datetime vs a number / `ERR`).
4. **Blank lines** in the body are ignored.

### 5.2 Timestamps

Files carry **no timezone offset**. Interpret every timestamp as `Asia/Jerusalem` local time, then store UTC. Use stdlib `zoneinfo.ZoneInfo("Asia/Jerusalem")`, never a hardcoded `+03:00`. September 2026 is IDT (UTC+3); a January file would be IST (UTC+2). DST must be correct or the inspector's "when" will be wrong by an hour.

Accept at least:

- `YYYY-MM-DD HH:MM` and `YYYY-MM-DD HH:MM:SS`
- `YYYY-MM-DDTHH:MM:SS` (ISO 8601 `T`)
- `DD/MM/YYYY HH:MM` (Haifa / the sample table). This is day/month, not month/day — `14/09/2026` is 14 September.

After parsing, keep `ts_local` (naive local, or an aware local datetime) and `ts_utc`. The UI and the inspector report display local time. Comparisons and unique keys use UTC.

### 5.3 Units

**The unit comes from the logger assignment in the registry, not from the values and not from the file header.** TL-0231 is `unit=F`. 38.3 in that file is 38.3°F = 3.5°C, which is a healthy dairy fridge, not a disaster. A "values over 30 must be Fahrenheit" heuristic would work on this particular week and fail the first time a Celsius logger truly overheats, or the first time a Fahrenheit logger sits near freezing. The Haifa header `Units: F` is a useful cross-check: if the header and the registry disagree, warn in the import summary but still trust the registry.

Conversion: `temp_c = (raw - 32) * 5 / 9` when unit is `F`. Store `raw_value` as the original cell text. Store `temp_c` as a DECIMAL (recommended `DECIMAL(6,2)`) so the golden test can round peaks to one decimal without floating-point noise. Threshold comparisons use the stored Celsius value, strictly greater than `ALERT_THRESHOLD_C`.

### 5.4 `ERR` and bad cells

- `ERR` (any case) is a sensor error: `status=err`, `temp_c` null, `raw_value='ERR'`. Do not store 0, do not drop the row, do not convert it. It **breaks** an excursion run (see §6).
- Other non-numeric cells (`abc`, `NaN`, `null`, `??`, empty temperature) are also `err` (or a rejected row counted in the import summary). Prefer keeping a row when the timestamp is valid, so the chart can show a break rather than a silent hole.

### 5.5 Duplicates, order, unknown loggers, idempotency

- **Sort by timestamp** before any rule runs. TL-0417 writes `2026-09-14 05:45` *after* the 06:30 row. Out-of-order input is not an error.
- **Exact duplicates** (same logger, same timestamp, same value), as with TL-0512 at 06:15 (3.9 written twice), collapse to one reading. If the same timestamp arrives with a *different* value, the later upload wins and the import summary mentions the overwrite.
- **Unknown logger** (the unhappy-path file `TL-9999_2026-W38.csv`): reject the upload with `422` and a message such as *Logger TL-9999 is not in the registry. Add it under Logger registry (branch, fridge, unit, assigned from) and try again.* Parse nothing into `readings`. The rest of the dashboard is unchanged.
- **Idempotent re-upload:** if the SHA-256 of the bytes already exists in `uploads`, return success with `already_imported: true` and do not re-write readings or recompute twice. If Summer uploads a corrected file with a different hash, insert a new `uploads` row, upsert readings, recompute.

Pin the sample-table values from `data/mock-logger-files/SCENARIOS.md` (Haifa in Fahrenheit and `DD/MM/YYYY`, everyone else in °C) as parser fixtures. They must round-trip exactly.

---

## 6. Alert rules

Summer's words: a single jump from a door opening is fine; a fridge that is slowly warming up is not. The Ministry asks for periods above five degrees and how long they lasted.

These rules are the ones encoded in `data/expected_excursions.json`. Changing them is a product decision and should be written down in `NOTES.md`.

### 6.1 Excursions vs spikes

- Consider only `status=ok` readings, in UTC (or sorted local) order, for one logger.
- A reading is *above threshold* when `temp_c > ALERT_THRESHOLD_C` (default **strictly greater than 5.0**). 5.0 exactly is not an excursion.
- A run of **two or more consecutive** above-threshold readings is an **excursion** (an alert).
- A **single isolated** above-threshold reading is a **spike**, not an alert. It is still stored/returned so the chart can mark it, but it does not appear on the inspector report and does not turn a fridge card red.
- **`ERR` breaks a run.** It is not "above" or "below"; it starts a gap in the run. A reading above 5°C, then `ERR`, then another reading above 5°C, is two spikes (or two runs, each judged on its own length), not one excursion.
- **A gap longer than `SAMPLE_INTERVAL_MINUTES` (15) also breaks a run.** Do not join two warm readings across a two-hour hole.
- **Duration** is `(end − start)` in minutes, from the first to the last reading of the run, **not** until the first recovery reading. Ashdod TL-0901 is the fixture: 03:00–04:00 = 60 minutes, peak 7.4°C, five readings, recovered at 04:15. Rishon TL-0388 runs from 2026-09-14 06:15 through 2026-09-20 23:45 (still open at the end of the file).
- **Peak** is the maximum `temp_c` in the run, shown to one decimal place in the report.

`MIN_EXCURSION_READINGS=2` and `ALERT_THRESHOLD_C=5.0` and `SAMPLE_INTERVAL_MINUTES=15` live in the environment so we can change them without a code edit. The golden test pins the defaults.

### 6.2 Gaps (reported separately)

If two successive readings for the same logger (after sorting, ignoring exact duplicates) are more than 15 minutes apart, record a **gap** from the last reading before the hole to the first reading after it. Do not interpolate temperatures and do not draw a connecting line across the hole on the chart.

Fixtures:

- Jerusalem TL-0512: 06:15 then 08:30 — a 2 h 15 min gap (eight missing 15-minute slots).
- Beit Shemesh TL-1101: last reading 2026-09-18 22:00, next 2026-09-19 08:00 — 10 hours between flanking readings, both healthy, no excursion.

Gaps are a data-quality issue for Summer ("did the logger die, did the battery run out, or did it just not save?"). They are not Ministry "above five degrees" events.

### 6.3 Expected detections for the mock week

The machine-readable oracle is `data/expected_excursions.json`. After importing the mock files with default rules, the engine must produce exactly these three excursions (local times):

| Logger | Fridge | Start | End | Duration (min) | Peak °C | Readings |
|---|---|---|---|---|---|---|
| TL-0388 | Rishon LeZion / Cream cakes | 2026-09-14 06:15 | 2026-09-20 23:45 | 9690 | 11.5 | 647 |
| TL-0901 | Ashdod / Dairy | 2026-09-16 03:00 | 2026-09-16 04:00 | 60 | 7.4 | 5 |
| TL-0601 | Be'er Sheva / Dairy | 2026-09-16 13:45 | 2026-09-20 23:45 | 6360 | 9.4 | 425 |

Spikes that must **not** become alerts: TL-0417 at 2026-09-14 06:15 (9.4°C, the sample-table door opening), 2026-09-15 14:30, 2026-09-18 09:15, 2026-09-19 16:00; TL-0419 at 2026-09-16 11:00.

Haifa TL-0231 has four `ERR` rows and **no** excursion this week, once Fahrenheit is converted.

TL-0417's mid-week move is a registry fact, not a file fact: readings through 2026-09-16 23:45 belong to the Tel Aviv walk-in; from 2026-09-17 00:00 they belong to Display 2. The walk-in continues on TL-0420 from 2026-09-17 00:00 (that file starts on the 17th on purpose).

Every other logger is a healthy control and should produce no alerts, spikes, gaps, duplicates or sensor errors.

### 6.4 Fridge card colours (dashboard)

Summer looks at this on her phone, between branches, and wants to see "how every fridge is doing and where something is wrong." Colour is a decision she did not spell out; this is the rule to implement and write in `NOTES.md`:

| Colour | When |
|---|---|
| **Red** | The selected period has at least one excursion. If `is_open` is true (the latest reading is still above 5.0°C, as with Rishon cream cakes this week), the card also shows an "ongoing" badge — that is the fridge she should call about first. |
| **Amber** | No excursion, but the period has a gap or a sensor error. She cannot fully answer the inspector about this fridge until the hole is explained. |
| **Green** | Otherwise. Isolated spikes stay green: she said a door opening is fine. The card can still show a quiet "n spikes" footnote so the detail chart is not a surprise. |

Cards show: branch, fridge, current/last temperature in °C, last reading time, and a one-line reason ("ongoing 11.5°C since Mon 06:15", "gap 10 h on 18–19 Sep", "OK"). Tapping a card opens screen 2.

---

## 7. Testing

Tests are run **in containers**. Reviewers and day-to-day development do not need pytest, Node or Angular CLI on the host.

### 7.1 Backend (`pytest`, inside the `api` image)

- **Parser unit tests**, one fixture per format family: comma with `timestamp,temp_c`; reversed `Temp,Time`; semicolon `Time;Temp` with and without metadata; tab-separated; ISO `T` timestamps; Haifa metadata + `DD/MM/YYYY` + Fahrenheit + `ERR`. Assert delimiter, column order, skipped preamble, and exact sample-table pins.
- **Normalisation:** Asia/Jerusalem → UTC for a September timestamp (IDT, +3) and at least one winter date (IST, +2) so DST is not hardcoded. TL-0231 14/09/2026 06:00 / 38.3 → 3.5°C. `ERR` → `status=err`, `temp_c` is null.
- **Rules unit tests:** isolated spike vs two-reading excursion; `ERR` breaks a run; a >15 minute gap breaks a run; duration is end−start, not until recovery; 5.0 exactly is not above threshold.
- **Golden test:** import every mock file (except TL-9999) against a temporary database, then compare the resulting excursions to `expected_excursions.json` (logger, start, end, duration_minutes, peak_c to one decimal, n_readings). Also assert the known spikes are *not* in the excursion table, that TL-0231 produces no excursion, that TL-0512's duplicate collapsed and its gap was recorded, and that TL-0417 readings on 17 Sep sit on Display 2.
- **Unknown logger:** posting `TL-9999_2026-W38.csv` returns `422`, zero new readings.
- **Idempotency:** uploading the same file twice creates one `uploads` row (or a second call no-ops on the hash) and does not duplicate readings.
- **API tests** with `httpx` + FastAPI `TestClient` (or a pytest fixture against a test MySQL started as a Compose service): health, upload happy path, dashboard colours for Rishon (red, ongoing), Ashdod (red, recovered), Beit Shemesh (amber, gap), a healthy fridge (green), report list, CSV export, registry assignment change for a move.

For unit and golden tests that do not need a long-lived demo database, prefer an isolated MySQL (a `mysql` dependency in the same `compose run`, or a pytest fixture that talks to the already-healthy `mysql` service on a disposable schema). Document the exact fixture in the repo; the command a reviewer runs should still be one line.

### 7.2 Frontend (inside a Node/Angular image, not the nginx runtime stage)

- Card colour helper tests (pure functions: red / amber / green given a summary DTO).
- Upload dialog: submit disabled until both a file and a logger are chosen; filename `TL-0512_…` pre-selects that logger.
- A smoke test that the three routes render an empty state without a backend is enough if time is short. Do not block the submission on a heavy e2e harness.

### 7.3 How to run tests (container-only, default)

From the repo root, with only Docker on the host:

```bash
# backend, including parser, rules, golden oracle and API tests
docker compose run --rm api pytest

# frontend unit tests: use the dev/Node image, not the nginx stage
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --no-deps web pnpm test --no-watch
```

`make test` should wrap those two commands. The golden test needs the mock files mounted at the seed path (the demo compose file already does this; the dev override bind-mounts `./data` and `./backend` as well).

If the production `web` image is nginx-only, the dev compose file must define `web` as the Angular/Node dev-server image so the frontend test command has `pnpm` and the source tree. Alternatively, add a small `frontend-test` service (Node image, `profiles: [test]`) and run `docker compose --profile test run --rm frontend-test`. Pick one, wire it into `make test`, and document that path in the README — it has to work with Docker alone.

A full `docker compose up --build` + "does the dashboard show three red fridges for W38?" check is part of the release bar, not just unit tests.

Host-side `pytest` or `pnpm test` is an optional convenience for people who have already installed the §1.2 toolchain; it is not required and is not what `make test` should depend on.

---

## 8. Development mode

There is no LLM provider switch in this project. Development mode means hot reload and bind mounts, still inside Compose. **The default development path is container-only** — the same "only Docker on the host" rule as the demo. Host Python / Node / a published MySQL port are an optional alternative in §8.2.

### 8.1 Option A: develop in Docker with hot reload (recommended, no host toolchain)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

No `.env` file is required. `docker-compose.dev.yml` overrides:

- `api`: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`, `./backend` bind-mounted, `APP_ENV=development`. Image remains `squanchy-kitchens-api`.
- `web`: replaced by an Angular dev-server image (`ng serve --host 0.0.0.0 --port 4200 --proxy-config proxy.conf.json`) with `./frontend` bind-mounted, image `squanchy-kitchens-web-dev` (or the same service rebuilt from a dev target). This is also the image `make test` uses for frontend tests.
- `mysql`: stays on the Compose network only. **Do not publish `3306:3306` by default**, even in the dev file, so a host MySQL is not disturbed. If you want a local client, uncomment or add a `ports` override yourself.
- `SEED_DEMO_DATA` still defaults to true, so you can iterate on the same week of data.

Open http://localhost:4200. The page title is Squanchy Kitchens. `proxy.conf.json` sends `/api` to `http://api:8000` on the Compose network.

`make dev` should be this compose command. `make test` still works against this project: `docker compose run --rm api pytest` and the frontend test line in §7.3.

### 8.2 Option B: run API and UI on the host (optional)

Only if you already have (or want) the §1.2 tools. The database still comes from Compose — do not install MySQL on the host.

```bash
docker compose up mysql -d

cd backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
export APP_ENV=development
export DATABASE_URL=mysql+pymysql://squanchy:squanchy@127.0.0.1:3306/squanchy_kitchens?charset=utf8mb4
export UPLOAD_DIR=./var/uploads
alembic upgrade head
python -m app.bootstrap
uvicorn app.main:app --reload --port 8000

cd frontend
pnpm install
pnpm start          # ng serve on :4200, proxy /api → http://localhost:8000
```

This option **does** need MySQL published on the host. Use a one-off override, for example:

```bash
docker compose -f docker-compose.yml -f docker-compose.publish-mysql.yml up mysql -d
```

where the extra file contains only `services.mysql.ports: ["3306:3306"]`. If something on the host is already bound to 3306, pick another host port (`3307:3306`) and point `DATABASE_URL` at it. This extra file is not used by the demo or by Option A.

### 8.3 Useful commands (Makefile)

These should call `docker compose`, so they work with only Docker installed.

| Command | What it does |
|---|---|
| `make up` | Demo mode (`docker compose up --build`) |
| `make up-empty` | Demo mode with `SEED_DEMO_DATA=false` |
| `make dev` | Container-only dev mode with hot reload |
| `make seed-demo` | Import all mock logger files into a running stack (idempotent) |
| `make test` | `docker compose run --rm api pytest`, then the containerised frontend tests |
| `make lint` | `docker compose run --rm api ruff/mypy` and the frontend linter in the Node image |
| `make reset-db` | `docker compose down -v` then `up --build` — wipes the MySQL volume and uploads |
| `make fmt` | Formatters run inside the same images |

---

## 9. Troubleshooting checklist

- [ ] `docker compose up` fails on `mysql` healthcheck: wait a first-boot init (can take 30–60 s). If you previously started the stack with different credentials, the named volume still has the old users — `make reset-db` (deletes data).
- [ ] API exits on startup: `alembic upgrade` failed. `docker compose logs api`. The database name (`squanchy_kitchens`), user (`squanchy`) and charset must match the Compose defaults unless you overrode them.
- [ ] API starts but `/api/health` reports the database down: inside Compose the URL host must be `mysql`, not `localhost`. `localhost` is only for the optional host-tools path in §8.2, and only if you published 3306.
- [ ] Dashboard is empty after `up`: confirm the Compose default `SEED_DEMO_DATA=true` was not overridden, and `docker compose logs api` shows the demo import. Then `make seed-demo` or `make reset-db`.
- [ ] Haifa looks like 38°C / a red disaster: the unit is not being read from the registry. Check the TL-0231 assignment is `F` and the conversion ran.
- [ ] Tel Aviv walk-in goes dark after 16 Sep, or Display 2 has no history before 17 Sep: the assignment dates are being applied, or TL-0420 was not imported. Both are required for that fridge's full week.
- [ ] Re-upload duplicates every row: the unique key must be `(logger_id, ts_utc)`, and the SHA-256 short-circuit should fire on an identical file.
- [ ] `TL-9999` appears on the dashboard, or a failed upload breaks other fridges: the unknown-logger path must 422 without writing readings.
- [ ] Chart draws a straight line across 06:15–08:30 on Jerusalem Dairy: gaps must be returned by `/api/fridges/{id}/series` and the echarts series must use a break (no connecting line).
- [ ] Inspector times are off by three hours, or by one hour in winter: timestamps were treated as UTC or as a fixed offset instead of `ZoneInfo("Asia/Jerusalem")`.
- [ ] Frontend shows API errors / CORS: in demo mode the browser should only talk to nginx on `:8080` (`/api` proxied). In container-dev mode, `proxy.conf.json` must point at `http://api:8000`. Do not call `:8000` from the browser in production compose.
- [ ] `Be'er Sheva` mojibake: MySQL and the SQLAlchemy URL must use `utf8mb4`.
- [ ] Port 8080 already in use: stop the other process, or add a Compose override that maps another host port (`8081:80`) and document it. The demo file should keep 8080.
- [ ] Port 3306 conflict with a local MySQL: the demo and default dev compose files must **not** publish 3306. If you opted into §8.2 and published it, use a different host port or stop the host server.
- [ ] Compose file not found / old Compose v1: the command is `docker compose` (a space), not `docker-compose`, and not `docker compose --up`.
- [ ] `make test` fails looking for `pytest` or `pnpm` on the host: tests must run via `docker compose run`, not a local toolchain.

---

## 10. Actionable build plan (48-hour window)

A partial submission with a few decisions made well is better than half-finished features. The vertical slice to protect first: **parse one messy file, store it, show one red card, show the chart, export the inspector CSV.** Times are rough and include tests for that step.

1. [ ] **Scaffold (2 h).** Repo layout, `name: squanchy-kitchens` in `docker-compose.yml`, image/container names, `${VAR:-default}` so no `.env` is required, `backend/Dockerfile`, `frontend/Dockerfile` (multi-stage nginx), `docker-compose.dev.yml` (no published 3306 by default), `.env.example` as a reference only, `Makefile`, copy `loggers.csv`, mock files and `expected_excursions.json` into `data/`. Confirm MySQL becomes healthy and the API container can ping it, with Docker as the only host dependency.
2. [ ] **Schema and bootstrap (2–3 h).** SQLAlchemy models, first Alembic revision, entrypoint that waits for the DB and runs `alembic upgrade head`, seed of branches / fridges / loggers / assignments from `loggers.csv`. Registry API: list loggers, add an assignment. Database name `squanchy_kitchens`.
3. [ ] **Parser (4–5 h).** Delimiter sniffing, metadata skip, column detection (including `Temp,Time`), all date formats, `ERR`. Unit tests against real mock-file headers and the sample-table pins, run with `docker compose run --rm api pytest`. Do this before any UI work; the assignment is won or lost here.
4. [ ] **Normalise, upsert, store originals (2 h).** Timezone conversion, unit from the assignment, fridge resolution (TL-0417 move), SHA-256, file retention, unique `(logger_id, ts_utc)`. Tests for duplicates, out-of-order rows, unknown logger, idempotent re-upload.
5. [ ] **Rules engine (3 h).** Excursions, spikes, gaps. Golden test against `expected_excursions.json`. Do not start the report screen until this test is green.
6. [ ] **API (2–3 h).** `POST /api/uploads`, dashboard DTO (colour logic), fridge series, report and CSV. Manual check via `/api/docs`.
7. [ ] **Angular shell and upload (3 h).** Material, mobile-first layout, routing for the three screens, page title **Squanchy Kitchens**, upload dialog (file picker + logger dropdown, filename hint), basic error toasts.
8. [ ] **Dashboard (2–3 h).** Green / amber / red cards, defaulted to the latest week with data, branch filter, "ongoing" badge, tap through to detail.
9. [ ] **Fridge detail chart (3 h).** ngx-echarts: temperature series, a dashed 5°C line, visible gaps (broken line or a shaded band), spike markers, excursion bands, timezone-correct axis labels.
10. [ ] **Inspector report (2 h).** Table of excursions with start, end, duration, peak, branch, fridge, logger; filters; CSV export. PDF only if this finished early.
11. [ ] **Registry UI, empty/error/loading states, phone layout pass (2 h).** Summer must be able to record a logger move without editing SQL. Check a 390px-wide viewport for the three screens.
12. [ ] **Tests, seed path, lint (2 h).** `make test` (container-only), `make seed-demo`, fix golden-test drift if any peak rounding is off.
13. [ ] **Clean clone/zip path (1–2 h).** From a fresh directory, on a machine with only Docker: unzip or `git clone` → `docker compose up --build` (no `.env` copy) → open `:8080` → confirm three excursions and a green healthy fridge, no keys and no host MySQL/Python/Node required.
14. [ ] **README.md and NOTES.md (2 h).** README: Docker-only setup, clone-or-zip to running, architecture in a paragraph, how to upload, how to run tests in containers. NOTES: the skeleton in §11, filled in honestly. Leave planning notes (this file included) in the repo; the assignment asks for that.

If time runs out, submit after step 10 (or even after 8, with the report as a plain table and no chart polish) and say so in NOTES. Do not start email ingestion, auth, notifications, or a PDF exporter at the expense of the parser or the golden test.

---

## 11. NOTES.md skeleton

The assignment requires a short `NOTES.md` in the public repo. Bullets are fine. Fill this in at the end, with real numbers and real links into the repo (a commit hash, a test path, or a comment). Suggested starting point:

```markdown
# Notes

## Time spent
- Roughly N hours over the 48-hour window.
- Where it went: parsing and rules (…), API and data model (…), Angular screens (…), Docker/README (…).

## Decisions Summer didn't ask for, and why

- Logger registry with dated assignments, including unit (C/F) on the assignment.
  The raw files only have time and temperature. She already types logger, branch
  and fridge herself. Dated assignments are how we handle "we moved one of the
  Tel Aviv loggers into the new display fridge last week" without splitting
  files by hand. Unit lives here so Haifa is converted correctly and we never
  guess Fahrenheit from the magnitude of the number.
- An isolated reading strictly above 5.0°C is a spike, not an alert.
  Two or more consecutive readings are an excursion. She said a door-opening
  jump is fine and a slowly warming fridge is not. Duration is last minus first
  reading of the run, not until recovery. Threshold, sample interval and the
  2-reading minimum are env-configurable; defaults match the mock oracle.
- MySQL 8 in Docker Compose, rather than SQLite or a host-installed MySQL.
  Nothing in the email requires a server database, but the Ministry can ask
  about a random week in the past, and she will keep uploading every week.
  MySQL runs as a Compose service (official image, named volume) so a reviewer
  only needs Docker. The cost is a heavier stack than SQLite would have been;
  we accepted that for long-term retention. The database is not installed on
  the host, and 3306 is not published by default, to avoid clashing with a
  local MySQL.
- Original files are stored, with a SHA-256, and readings upsert on
  (logger, timestamp). Re-uploading the same file is a no-op. A corrected
  file updates readings and recomputes excursions. The inspector may ask
  what was uploaded, not only what the chart shows now.
- All timestamps stored in UTC, displayed in Asia/Jerusalem, including DST.
  The files have no offset. A fixed +3 would be wrong from the last Sunday
  of October.
- Fridge card colours: red = any excursion in the period (with an "ongoing"
  badge if it has not recovered); amber = no excursion but a gap or sensor
  error; green = otherwise, including isolated spikes.
- No email auto-ingestion and no LLM / agent workflow in this version.
  A file picker plus a logger dropdown is what she asked for ("upload the
  files and see, in one place…"). Reading her inbox would be a later
  convenience, not what lets her answer the inspector this week.
- A small registry screen so she can record a move herself, rather than
  only a seed file we control.

## Questions I would ask Summer before this goes live

- Is 5.0°C a strict upper limit for every fridge (dairy, cream cakes,
  walk-in, display), or do some units have a different threshold? Any freezers
  later?
- When a logger is moved, who updates the registry — only you, or also the
  branch manager? Should a file be rejected if its dates are not covered by
  any assignment?
- How long must we keep readings and original files for the Ministry?
- Should isolated door-opening spikes appear on the inspector export at all,
  for example as a footnote, or stay off that document entirely?
- If a fridge is mid-excursion when you look at your phone on a Wednesday,
  do you want a notification, or is the weekly upload still the working
  rhythm?
- Sometimes a manager will send a partial file and then a full one. Is
  "latest file wins on overlapping timestamps" the right merge, or should
  we keep both and flag the conflict?
- The Haifa logger is the only Fahrenheit device we know about. Are there
  others, and will new loggers ever ship with a different interval than
  15 minutes?

## What's not done, and what I would do with one more hour

- Not done: (e.g. PDF export, login, email ingestion, multi-week comparison,
  registry CSV import from the UI, automated notifications, …).
- One more hour: (pick one concrete improvement, e.g. "polish the chart gap
  shading and add a print stylesheet for the inspector page").

## AI tools

- One thing they got wrong or I rejected:
- How I caught it:
- Where in the repo you can see that (commit, test, or note):

## Approach (optional)
- Started from the email and the messy sample table, wrote the parser and
  the rules against generated mock files with a known oracle, then built
  the three screens on top of a stable API.
```

Keep the "AI tools" section honest and specific. A good example, if it happens, would be an assistant treating 38.3 on the Haifa logger as 38.3°C, or joining an excursion across an `ERR` or a two-hour gap, caught by the golden test in `backend/tests/test_excursions_golden.py` (or whatever path you actually use).

---

## 12. What this system is, and is not

Summer needs to finish Sunday's spreadsheet in minutes, on her phone, and answer the inspector with start, end and duration. The product is therefore:

1. A registry of which logger sits in which fridge, from when, in which unit.
2. An upload path that accepts the messy raw files as they actually come out of the devices.
3. A normalised history that will still be there when the Ministry asks about last month.
4. Three screens: a colour-coded dashboard, a fridge chart that does not lie across gaps, and an exportable excursion report.

It is not an inbox agent, not a chatbot, and not a general analytics suite. Those can wait.
