#!/bin/sh
# Boot steps run only when starting the server (uvicorn). Anything else - `pytest`,
# `ruff`, `python -m app.bootstrap --demo` - is executed as-is.
set -e

if [ "$1" = "uvicorn" ]; then
    echo "entrypoint: waiting for the database..."
    python - <<'PY'
import sys, time
from sqlalchemy import create_engine, text
from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
for attempt in range(60):
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        print("entrypoint: database is up")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"entrypoint: database not ready ({exc.__class__.__name__}), retrying")
        time.sleep(2)
sys.exit("entrypoint: database never became reachable")
PY
    echo "entrypoint: alembic upgrade head"
    alembic upgrade head
    if [ "${SEED_ON_STARTUP:-true}" = "true" ]; then
        echo "entrypoint: seeding registry (and demo files if SEED_DEMO_DATA=true)"
        python -m app.bootstrap
    fi
fi

exec "$@"
