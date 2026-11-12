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
- **Sign-in and roles:** Summer (admin) sees every branch; each branch manager uploads and
  exports only their own branch, and can flag a mistaken upload for Summer to void.

The UI follows the Simple To Work **"Northern lights"** brand: a night-sky background with
aurora glows and liquid-glass cards. Headings are Sora, body text Inter and data JetBrains
Mono, all self-hosted. The printed inspector report switches to dark ink on white paper.

There is no LLM and no agent workflow. Stack: FastAPI + SQLAlchemy + Alembic, MySQL 8,
Angular 22 + Angular Material + ECharts, all in Docker Compose.

## Run it (only Docker needed)

You need Docker Desktop, or Docker Engine 24+ with Compose v2. You do not need Python, Node
or MySQL on the host. **This repository contains no passwords or secrets**; see step 2.

### 1. Get the code

```bash
git clone https://github.com/HarrBarr/squanchy-kitchens.git
cd squanchy-kitchens
```

No Git? Download the ZIP from GitHub, unzip it and `cd` into the folder.

### 2. Add the env file you were given (optional)

If you received a file with the sign-in passwords (for example `reviewer.env`, attached to
an e-mail), save it in the `squanchy-kitchens` folder, next to `docker-compose.yml`, and
**rename it to exactly `.env`**, **before the first start**. Docker Compose only reads a file
with that name automatically. Rename it in your file manager, or from the `squanchy-kitchens`
folder:

```bash
mv ~/Downloads/reviewer.env .env
```

It holds the two sign-in passwords for your copy, and git ignores it:

```bash
ADMIN_PASSWORD=...
DEMO_MANAGER_PASSWORD=...
```

Without a `.env`, the app still starts: the first start generates random passwords and
prints them once (see step 4). `.env.example` lists every other optional setting.

### 3. Start it

```bash
docker compose up --build
```

Open **http://localhost:8080**. The first start takes a minute or two: it builds the images,
starts MySQL, runs the migrations, seeds the logger registry from `data/loggers.csv`,
creates the accounts, and imports one week of mock logger data from
`data/mock-logger-files/` (2026-W38, 14–20 Sep 2026). The app only listens on this computer
(`127.0.0.1`); other devices on the network cannot reach it.

### 4. Sign in

There is no public sign-up. The first start creates:

| Username | Role | Sees |
|---|---|---|
| `admin` | admin (Summer Smith) | every branch; reviews flagged uploads; manages users |
| `manager.haifa` | branch manager | Haifa |
| `manager.rishon` | branch manager | Rishon LeZion |
| `manager.telaviv` | branch manager | Tel Aviv |
| `manager.jerusalem` | branch manager | Jerusalem |
| `manager.beersheva` | branch manager | Be'er Sheva |
| `manager.netanya` | branch manager | Netanya |
| `manager.petah` | branch manager | Petah Tikva |
| `manager.ashdod` | branch manager | Ashdod |
| `manager.herzliya` | branch manager | Herzliya |
| `manager.beitshemesh` | branch manager | Beit Shemesh |
| `manager.kfarsaba` | branch manager | Kfar Saba |
| `manager.rehovot` | branch manager | Rehovot |

The branch managers share one password. The passwords are:

- **with a `.env`:** the `ADMIN_PASSWORD` and `DEMO_MANAGER_PASSWORD` in it;
- **without one:** generated on the first start and printed once, in the terminal running
  `docker compose up` and in the API log:

  ```bash
  docker compose logs api | grep -A 8 "sign-in credentials"
  ```

### If you started it before saving the `.env` file

No problem: the accounts were created with generated passwords. To switch to the ones in
your env file, save and rename it to `.env` as in step 2, then run the seeding script:

```bash
docker compose up -d                                                  # restarts the API so it reads .env
docker compose exec api python -m app.seed_users --reset-passwords    # sets the passwords from .env
```

The second command prints a summary table of the accounts it updated. The same two commands
recover a lost password (see [Seeding users yourself](#seeding-users-yourself)).

### Suggested walkthrough (about 5 minutes)

1. Sign in as `admin`. The W38 dashboard shows **three red fridges** (table below).
2. Open a red fridge to see its chart, then **Inspector report → CSV**.
3. Sign out and sign in as `manager.rishon`. Only Rishon LeZion is visible; asking the API
   for another branch returns `403`.
4. As the manager, upload a logger file (drag and drop works) and flag it as "uploaded by
   mistake" on the **Uploads** screen.
5. Sign back in as `admin`: **Review** shows the flag with a badge. Void it. The data
   disappears from the dashboard; the upload and its original file are kept for the audit
   trail.

The mock week, as the dashboard should show it:

| Fridge | What happened |
|---|---|
| Rishon LeZion / Cream cakes | Died Monday 06:15 and never recovered. **Ongoing**, peak 11.5°C |
| Be'er Sheva / Dairy | Slow two-day drift from Wednesday 13:45. **Ongoing**, peak 9.4°C |
| Ashdod / Dairy | Power cut Wednesday 03:00–04:00, 60 min, peak 7.4°C, recovered |

Three fridges are amber. Beit Shemesh Dairy has a 10-hour battery gap, Jerusalem Dairy a
2 h 15 min gap, and Haifa Dairy four `ERR` readings. Everything else is green, including the
Tel Aviv door-opening spikes.

### Other ways to run it

```bash
make test                                          # all tests, inside the containers
SEED_DEMO_DATA=false docker compose up --build     # start empty, upload files yourself (make up-empty)
docker compose down -v                             # start again from scratch (deletes the local data)
```

MySQL's port 3306 is **not** published, so it can't clash with a MySQL already on your
machine. The only published port is 8080, on `127.0.0.1`. The OpenAPI docs are at
http://localhost:8080/api/docs.

## Accounts and roles

The JWT signing secret is generated per install and kept in the `api-state` volume, unless
you set `JWT_SECRET`. Passwords are stored only as bcrypt hashes. Tokens last 8 h by default;
logging out drops the token in the browser. A forgotten password is reset by Summer on the
Users screen, which shows a one-time temporary password, or with the seeding script.
Nothing is e-mailed.

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
voided correction had overwritten come back from the earlier file.

### Seeding users yourself

The seeding script creates the accounts or changes their passwords, for example to hand
out your own passwords instead of generated ones:

```bash
make seed-users                                   # prompts for the two passwords (hidden)
make seed-users ARGS="--generate"                 # random passwords, printed once
make seed-users ARGS="--generate --reset-passwords --format env"   # new passwords as .env lines
# = docker compose exec api python -m app.seed_users [options]   (--help for all options)
```

It is idempotent: it creates whatever is missing and leaves existing users alone unless
`--reset-passwords` is given. Passwords come from `ADMIN_PASSWORD` / `DEMO_MANAGER_PASSWORD`,
from a hidden prompt, or are generated. They are never taken as command-line arguments
(those end up in shell history), never logged, and printed only once. Other options:
`--per-manager` (a different generated password per manager), `--must-change` (managers
choose their own at first sign-in), `--admin-only` and `--managers-only`.

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

- **Backend:** 113 pytest tests. They cover the parser (every format family and the
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
- **Frontend:** 48 Vitest tests in the Node `dev` image. They cover the card colour helper,
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

Every setting except the passwords and `JWT_SECRET` has a default in `docker-compose.yml`
(`${VAR:-default}`); those are generated when left empty (see [Run it](#run-it-only-docker-needed)).
`.env.example` lists every setting in case you want to override one. The alert rules are configurable:
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
