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

The UI follows the Simple To Work **"Northern lights"** brand: a night-sky background with
aurora glows and liquid-glass cards. Headings are Sora, body text Inter and data JetBrains
Mono, all self-hosted. The printed inspector report switches to dark ink on white paper.

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

Open **http://localhost:8080** and sign in (see [Sign-in](#sign-in-demo-accounts)). On the first start the API waits for MySQL, runs the
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

## Sign-in (demo accounts)

There is no public sign-up. On first start the API creates the admin, and with the default
`SEED_DEMO_DATA=true` it also creates one branch manager per branch:

| Username | Password | Role | Sees |
|---|---|---|---|
| `admin` | `admin2026#` | admin (Summer Smith) | every branch, users, review, audit log |
| `manager.rishon`, `manager.telaviv`, `manager.haifa`, `manager.jerusalem`, `manager.beersheva`, `manager.netanya`, `manager.petah`, `manager.ashdod`, `manager.herzliya`, `manager.beitshemesh`, `manager.kfarsaba`, `manager.rehovot` | `manager2026#` | branch manager | their own branch only |

**These credentials and the `JWT_SECRET` default are for a local demo only. They are
published in this public repository.** A real deployment must set `ADMIN_PASSWORD` and
`JWT_SECRET` (and `SEED_DEMO_DATA=false`) in the environment, and Summer must change her
password before any real Ministry data goes in. The sign-in page lists the demo logins only
while the stack runs on these defaults.

What each role can do (the API enforces all of it; the UI only hides what you cannot use):

| | admin | branch manager |
|---|---|---|
| Dashboard, fridge charts, inspector report and CSV export | all branches, or one | own branch only (another branch is `403`) |
| Upload a logger file | any logger | only loggers assigned to their branch on every date in the file; otherwise the whole file is refused |
| Flag an upload as "uploaded by mistake" | any | own uploads only |
| Dismiss a flag, void an upload | yes | no |
| Users (create, change branch, reset password, deactivate), logger registry changes, audit log | yes | no (registry read-only, own branch) |

Voiding is a soft delete: the file, its rows and the original upload stay on disk, the data
disappears from the dashboard, charts and reports, and excursions are recomputed. Readings a
voided correction had overwritten come back from the earlier file. Tokens are JWTs (8 h by
default). Logging out drops the token in the browser. A forgotten password is reset by Summer
on the Users screen, which shows a one-time temporary password. Nothing is e-mailed.

## Uploading a file

Click **Upload** and pick a raw export, or **drag the file** onto the dialog's drop zone or anywhere on the page, which opens the dialog with the file already chosen. Then confirm the logger. Only `.csv`, `.txt` and `.tsv` files are accepted, one per upload, because each file has to be matched to its logger. If the file name contains the
code, e.g. `TL-0512_2026-W38.csv`, the logger is pre-selected and you can change it. The
import summary lists new, duplicate and updated readings, sensor errors, gaps and
excursions, plus any warnings.

- An **identical file** (same SHA-256) is a no-op and returns "already imported".
- A **corrected file** updates the overlapping readings (the latest file wins) and the
  excursions are recomputed. Every original file is kept on disk for audit.
- An **unknown logger** (try `TL-9999_2026-W38.csv`) gets a 422 with a message pointing to
  the Logger registry. Nothing is written. Add the logger there and upload again.
- A **branch manager** uploading another branch's logger gets a 403. Nothing is imported.
- The **Uploads** screen lists every file, who uploaded it and its status. A manager can flag
  their own file as a mistake; Summer sees a badge on **Review** and can dismiss or void it.

## Tests (in containers)

```bash
make test
# = docker compose run --rm api pytest
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --no-deps web npx ng test --watch=false
```

- **Backend:** 98 pytest tests. They cover the parser (every format family and the
  sample-table pins), timezone/DST and °F conversion, the rules engine, ingest (duplicates,
  out-of-order rows, idempotency, unknown logger, the TL-0417 move) and the API (colours,
  report, CSV, registry). They also cover sign-in and roles (`backend/tests/test_auth.py`: cross-branch `403`s,
  upload ownership, flag/void, voiding a correction, forced password change, audit log). They
  also include the **golden test**
  [`backend/tests/test_excursions_golden.py`](backend/tests/test_excursions_golden.py), which
  imports the whole mock week and compares the result with
  [`data/expected_excursions.json`](data/expected_excursions.json).
  Inside Compose the tests create a throwaway schema `squanchy_kitchens_test` on the
  `mysql` service as root, migrate it with Alembic and drop it afterwards. The demo database
  is never touched. On a host without `TEST_DATABASE_URL`, the same tests run against a
  temporary SQLite file (`cd backend && pytest`).
- **Frontend:** 44 Vitest tests in the Node `dev` image. They cover the card colour helper,
  filename → logger, the upload dialog (submit stays disabled until a file and a logger are
  chosen), the chart breaking at gaps and `ERR`, empty-state smoke tests for each route, and
  auth (guards, the Bearer interceptor, admin vs manager navigation).

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

The full planning documents are
[`squanchy-kitchens-development.md`](squanchy-kitchens-development.md) and, for sign-in and
roles, [`squanchy-kitchens-auth.md`](squanchy-kitchens-auth.md). Decisions and open
questions are in [`NOTES.md`](NOTES.md). The mock data and its scenarios are in
[`data/mock-logger-files/SCENARIOS.md`](data/mock-logger-files/SCENARIOS.md).
