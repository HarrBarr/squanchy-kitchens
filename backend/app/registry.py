"""Logger registry: which logger sits in which fridge, from when, in which unit."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.ingest import recompute_logger
from app.storage.models import Branch, Fridge, Logger, LoggerAssignment, Reading


class RegistryError(ValueError):
    pass


def get_or_create_branch(db: Session, name: str) -> Branch:
    name = name.strip()
    b = db.scalar(select(Branch).where(Branch.name == name))
    if b is None:
        b = Branch(name=name)
        db.add(b)
        db.flush()
    return b


def get_or_create_fridge(db: Session, branch_name: str, fridge_name: str) -> Fridge:
    b = get_or_create_branch(db, branch_name)
    fridge_name = fridge_name.strip()
    f = db.scalar(select(Fridge).where(Fridge.branch_id == b.id, Fridge.name == fridge_name))
    if f is None:
        f = Fridge(branch_id=b.id, name=fridge_name)
        db.add(f)
        db.flush()
    return f


def get_or_create_logger(db: Session, code: str) -> Logger:
    code = code.strip().upper()
    lg = db.scalar(
        select(Logger).where(Logger.logger_code == code).options(selectinload(Logger.assignments))
    )
    if lg is None:
        lg = Logger(logger_code=code)
        db.add(lg)
        db.flush()
    return lg


def _check_unit(unit: str) -> str:
    unit = unit.strip().upper()
    if unit not in ("C", "F"):
        raise RegistryError("Unit must be C or F.")
    return unit


def _overlaps(a_from: date, a_to: date | None, b_from: date, b_to: date | None) -> bool:
    return a_from <= (b_to or date.max) and b_from <= (a_to or date.max)


def add_assignment(
    db: Session,
    code: str,
    branch: str,
    fridge: str,
    unit: str,
    assigned_from: date,
    assigned_to: date | None = None,
) -> LoggerAssignment:
    """Start a new assignment. If the logger has a current (open-ended) assignment that
    started earlier, it is closed the day before ``assigned_from`` (the move)."""
    unit = _check_unit(unit)
    if assigned_to is not None and assigned_to < assigned_from:
        raise RegistryError("'Assigned to' must be on or after 'assigned from'.")
    lg = get_or_create_logger(db, code)
    db.refresh(lg, attribute_names=["assignments"])
    f = get_or_create_fridge(db, branch, fridge)

    for a in lg.assignments:
        if a.assigned_to is None and a.assigned_from < assigned_from:
            a.assigned_to = assigned_from - timedelta(days=1)
    for a in lg.assignments:
        if _overlaps(a.assigned_from, a.assigned_to, assigned_from, assigned_to):
            raise RegistryError(
                f"{lg.logger_code} is already assigned from {a.assigned_from}"
                f"{' to ' + str(a.assigned_to) if a.assigned_to else ''}; "
                "assignments of one logger must not overlap."
            )
    new = LoggerAssignment(
        logger_id=lg.id,
        fridge_id=f.id,
        unit=unit,
        assigned_from=assigned_from,
        assigned_to=assigned_to,
    )
    db.add(new)
    db.flush()
    return new


def reassign_readings(db: Session, settings: Settings, logger: Logger) -> None:
    """After a registry change, move already-imported readings to the fridge that the
    registry now says the logger was in, then recompute its excursions and gaps.
    (Units are not re-applied: changing a unit after import needs a re-upload.)"""
    db.refresh(logger, attribute_names=["assignments"])
    for a in logger.assignments:
        lo = datetime.combine(a.assigned_from, time.min)
        q = update(Reading).where(Reading.logger_id == logger.id, Reading.ts_local >= lo)
        if a.assigned_to is not None:
            hi = datetime.combine(a.assigned_to + timedelta(days=1), time.min)
            q = q.where(Reading.ts_local < hi)
        db.execute(q.values(fridge_id=a.fridge_id))
    db.flush()
    recompute_logger(db, settings, logger.id)


def seed_registry(db: Session, csv_text: str) -> int:
    """Idempotent registry seed from ``loggers.csv``
    (columns: logger_id,branch,fridge,unit,assigned_from,assigned_to)."""
    n = 0
    for row in csv.DictReader(io.StringIO(csv_text)):
        code = (row.get("logger_id") or "").strip().upper()
        if not code:
            continue
        lg = get_or_create_logger(db, code)
        f = get_or_create_fridge(db, row["branch"], row["fridge"])
        a_from = date.fromisoformat(row["assigned_from"].strip())
        a_to_raw = (row.get("assigned_to") or "").strip()
        a_to = date.fromisoformat(a_to_raw) if a_to_raw else None
        existing = db.scalar(
            select(LoggerAssignment).where(
                LoggerAssignment.logger_id == lg.id,
                LoggerAssignment.assigned_from == a_from,
            )
        )
        if existing is None:
            db.add(
                LoggerAssignment(
                    logger_id=lg.id,
                    fridge_id=f.id,
                    unit=_check_unit(row["unit"]),
                    assigned_from=a_from,
                    assigned_to=a_to,
                )
            )
            n += 1
    db.commit()
    return n
