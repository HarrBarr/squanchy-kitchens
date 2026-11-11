"""Startup seeding: registry from ``loggers.csv``, then (optionally) the mock week.

python -m app.bootstrap            # registry + demo files if SEED_DEMO_DATA is true
python -m app.bootstrap --demo     # force the demo import (used by `make seed-demo`)
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.ingest import ImportRejected, import_file, logger_code_from_filename
from app.registry import seed_registry
from app.storage.session import get_sessionmaker

log = logging.getLogger("squanchy.bootstrap")


def seed_registry_file(db: Session, settings: Settings) -> int:
    path = Path(settings.seed_registry_file)
    if not path.exists():
        log.warning("registry seed file %s not found; skipping", path)
        return 0
    n = seed_registry(db, path.read_text(encoding="utf-8"))
    log.info("registry seed: %d new assignment(s) from %s", n, path)
    return n


def seed_demo_files(db: Session, settings: Settings) -> dict[str, str]:
    """Import every ``*.csv`` in the demo dir whose name carries a logger code. Identical
    files are skipped on their SHA-256, so this is safe to run again. Files whose logger is
    not in the registry (TL-9999, on purpose) are reported and skipped."""
    results: dict[str, str] = {}
    folder = Path(settings.seed_demo_dir)
    if not folder.is_dir():
        log.warning("demo dir %s not found; skipping", folder)
        return results
    for path in sorted(folder.glob("*.csv")):
        code = logger_code_from_filename(path.name)
        if code is None:
            continue
        try:
            s = import_file(db, settings, path.name, path.read_bytes(), code)
        except ImportRejected as exc:
            db.rollback()
            results[path.name] = f"rejected: {exc}"
            log.info("demo import %s rejected: %s", path.name, exc)
            continue
        status = (
            "already imported"
            if s.already_imported
            else (
                f"{s.inserted} new, {s.duplicates} dup, {s.sensor_errors} ERR, "
                f"{s.gaps} gap(s), {s.excursions} excursion(s)"
            )
        )
        results[path.name] = status
        log.info("demo import %s: %s", path.name, status)
    return results


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="import the demo files")
    args = parser.parse_args()
    settings = get_settings()
    with get_sessionmaker()() as db:
        seed_registry_file(db, settings)
        if args.demo or settings.seed_demo_data:
            seed_demo_files(db, settings)


if __name__ == "__main__":
    main()
