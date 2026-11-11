"""Startup seeding: registry from ``loggers.csv``, then (optionally) the mock week.

python -m app.bootstrap            # registry + demo files if SEED_DEMO_DATA is true
python -m app.bootstrap --demo     # force the demo import (used by `make seed-demo`)
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.ingest import ImportRejected, import_file, logger_code_from_filename
from app.registry import seed_registry
from app.seed_users import (
    BRANCH_MANAGERS,
    generate_password,
    seed_admin_user,
    seed_branch_managers,
)
from app.storage.models import (
    Fridge,
    LoggerAssignment,
    Reading,
    Upload,
    User,
)
from app.storage.session import get_sessionmaker

log = logging.getLogger("squanchy.bootstrap")

# Kept for compatibility; the list lives in app.seed_users.
DEMO_MANAGERS = BRANCH_MANAGERS


def seed_admin(db: Session, settings: Settings) -> User:
    return ensure_admin(db, settings)[0]


def ensure_admin(db: Session, settings: Settings) -> tuple[User, str | None]:
    """Create the admin if missing, from ADMIN_PASSWORD, or with a generated password
    (returned so it can be shown once). Never overwrites an existing admin's password, or a
    changed password would be reset on every container restart."""
    username = settings.admin_username.strip().lower()
    exists = db.scalar(select(User.id).where(User.username == username)) is not None
    generated = None
    password = settings.admin_password
    if not exists and not password:
        password = generated = generate_password()
    res = seed_admin_user(db, settings, password or "")  # password unused if the admin exists
    db.commit()
    if res.action == "created":
        log.info("created admin user %r", res.username)
    admin = db.scalar(select(User).where(User.username == res.username))
    assert admin is not None
    return admin, generated


def backfill_upload_branches(db: Session) -> int:
    """Uploads imported before uploads.branch_id existed: take the branch from the fridges
    their readings sit in, or else from the logger's latest assignment. Idempotent."""
    n = 0
    for u in db.scalars(select(Upload).where(Upload.branch_id.is_(None))):
        branch_id = db.scalar(
            select(Fridge.branch_id)
            .join(Reading, Reading.fridge_id == Fridge.id)
            .where(Reading.upload_id == u.id)
            .group_by(Fridge.branch_id)
            .order_by(func.count().desc())
            .limit(1)
        )
        if branch_id is None:
            branch_id = db.scalar(
                select(Fridge.branch_id)
                .join(LoggerAssignment, LoggerAssignment.fridge_id == Fridge.id)
                .where(LoggerAssignment.logger_id == u.logger_id)
                .order_by(LoggerAssignment.assigned_from.desc())
                .limit(1)
            )
        if branch_id is not None:
            u.branch_id = branch_id
            n += 1
    db.commit()
    if n:
        log.info("backfilled the branch of %d earlier upload(s)", n)
    return n


def missing_demo_managers(db: Session) -> list[str]:
    taken = set(db.scalars(select(User.username)))
    return [u for u in DEMO_MANAGERS.values() if u not in taken]


def seed_demo_managers(db: Session, settings: Settings, password: str | None = None) -> int:
    """One demo branch manager per branch (SEED_DEMO_DATA=true), sharing one password:
    ``password``, else DEMO_MANAGER_PASSWORD."""
    password = password or settings.demo_manager_password
    if not missing_demo_managers(db):
        return 0
    if not password:
        raise ValueError("no password for the demo branch managers")
    results = seed_branch_managers(db, password)
    db.commit()
    n = sum(1 for r in results if r.action == "created")
    if n:
        log.info("created %d demo branch manager(s)", n)
    return n


def seed_registry_file(db: Session, settings: Settings) -> int:
    path = Path(settings.seed_registry_file)
    if not path.exists():
        log.warning("registry seed file %s not found; skipping", path)
        return 0
    n = seed_registry(db, path.read_text(encoding="utf-8"))
    log.info("registry seed: %d new assignment(s) from %s", n, path)
    return n


def seed_demo_files(db: Session, settings: Settings, admin: User | None = None) -> dict[str, str]:
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
            s = import_file(db, settings, path.name, path.read_bytes(), code, user=admin)
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
    generated: dict[str, str] = {}
    with get_sessionmaker()() as db:
        seed_registry_file(db, settings)
        admin, admin_pw = ensure_admin(db, settings)
        if admin_pw:
            generated[admin.username] = admin_pw
        backfill_upload_branches(db)
        if args.demo or settings.seed_demo_data:
            manager_pw = settings.demo_manager_password
            if not manager_pw and missing_demo_managers(db):
                manager_pw = generated["branch managers"] = generate_password()
            seed_demo_managers(db, settings, manager_pw)
            seed_demo_files(db, settings, admin)
    if generated:
        print_generated_credentials(generated, settings)


def print_generated_credentials(generated: dict[str, str], settings: Settings) -> None:
    """First start without ADMIN_PASSWORD / DEMO_MANAGER_PASSWORD: show the generated
    passwords once (they are stored only as bcrypt hashes)."""
    lines = [
        "",
        "=" * 72,
        "  Squanchy Kitchens - sign-in credentials (generated, shown only once)",
        "-" * 72,
    ]
    for who, pw in generated.items():
        lines.append(f"  {who:<18} {pw}")
    if "branch managers" in generated:
        lines.append("  (managers: " + ", ".join(list(DEMO_MANAGERS.values())[:3]) + ", ...)")
    lines += [
        "-" * 72,
        "  To choose your own instead, set ADMIN_PASSWORD / DEMO_MANAGER_PASSWORD in .env,",
        '  or run: make seed-users ARGS="--reset-passwords"',
        "=" * 72,
        "",
    ]
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
