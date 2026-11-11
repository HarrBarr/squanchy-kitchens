"""Upload pipeline: hash -> registry check -> parse -> normalise -> store -> upsert -> recompute.

See the flowchart in ``squanchy-kitchens-development.md`` §3.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.normalize import assignment_for, local_to_utc, to_celsius
from app.parsing import ParseError, parse_bytes
from app.rules import Analysis, Point, analyze
from app.storage.models import (
    ROLE_ADMIN,
    UPLOAD_ACTIVE,
    UPLOAD_VOIDED,
    Excursion,
    Fridge,
    Gap,
    Logger,
    LoggerAssignment,
    Reading,
    Upload,
    User,
)

LOGGER_CODE_RE = re.compile(r"TL-\d{3,6}", re.IGNORECASE)


class ImportRejected(Exception):
    """The upload cannot be imported; nothing was written. Maps to HTTP 422."""


class ImportForbidden(Exception):
    """The user may not upload this file (another branch's logger). Maps to HTTP 403."""


def logger_code_from_filename(filename: str) -> str | None:
    m = LOGGER_CODE_RE.search(filename or "")
    return m.group(0).upper() if m else None


@dataclass
class ImportSummary:
    logger: str
    filename: str
    sha256: str
    already_imported: bool = False
    upload_id: int | None = None
    rows_in_file: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicates: int = 0
    sensor_errors: int = 0
    rejected_lines: int = 0
    unassigned_rows: int = 0
    excursions: int = 0
    spikes: int = 0
    gaps: int = 0
    first_reading_local: datetime | None = None
    last_reading_local: datetime | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Row:
    ts_local: datetime
    ts_utc: datetime
    raw_value: str
    temp_c: object  # Decimal | None
    fridge_id: int
    line_no: int
    branch_id: int


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name)[:120] or "upload.csv"


def _load_logger(db: Session, code: str) -> Logger | None:
    return db.scalar(
        select(Logger)
        .where(Logger.logger_code == code)
        .options(selectinload(Logger.assignments).selectinload(LoggerAssignment.fridge))
    )


def import_file(
    db: Session,
    settings: Settings,
    filename: str,
    data: bytes,
    logger_code: str,
    user: User | None = None,
) -> ImportSummary:
    """Import one raw logger file. ``user`` is the uploader; ``None`` means a system import
    (startup seeding). A branch manager may only upload a file whose every reading belongs
    to their branch on that date; otherwise the whole file is refused (ImportForbidden)."""
    code = logger_code.strip().upper()
    sha = hashlib.sha256(data).hexdigest()
    summary = ImportSummary(logger=code, filename=filename, sha256=sha)
    is_manager = user is not None and user.role != ROLE_ADMIN

    # 1. Identical bytes already imported (and not voided): no-op. A voided file may be
    #    uploaded again; its hash no longer counts.
    existing = db.scalar(select(Upload).where(Upload.active_sha256 == sha))
    if (
        existing is not None
        and user is not None
        and is_manager
        and existing.branch_id != user.branch_id
    ):
        raise ImportForbidden(
            f"This file was already imported for another branch. Logger {code} is not "
            "assigned to your branch."
        )
    if existing is not None:
        summary.already_imported = True
        summary.upload_id = existing.id
        summary.rows_in_file = existing.row_count
        summary.sensor_errors = existing.error_count
        return summary

    # 2. The logger must be in the registry. Nothing is parsed into readings otherwise.
    logger = _load_logger(db, code)
    if logger is None:
        if is_manager:
            raise ImportRejected(
                f"Logger {code} is not in the registry. Ask Summer (admin) to add it to the "
                "Logger registry for your branch, then try again."
            )
        raise ImportRejected(
            f"Logger {code} is not in the registry. Add it under Logger registry "
            "(branch, fridge, unit, assigned from) and try again."
        )

    # 3. Parse. A file we cannot read at all is rejected the same way.
    try:
        parsed = parse_bytes(data)
    except ParseError as exc:
        raise ImportRejected(f"Could not read {filename}: {exc}") from exc

    summary.rows_in_file = len(parsed.rows)
    summary.rejected_lines = len(parsed.rejected)
    if parsed.rejected:
        sample = ", ".join(str(r.line_no) for r in parsed.rejected[:5])
        summary.warnings.append(
            f"{len(parsed.rejected)} line(s) without a readable timestamp were skipped "
            f"(line {sample}{'…' if len(parsed.rejected) > 5 else ''})."
        )

    # 4. Normalise: Asia/Jerusalem -> UTC, unit from the assignment, fridge at that time.
    tz = settings.tz
    rows: list[_Row] = []
    for pr in parsed.rows:
        a = assignment_for(logger.assignments, pr.ts_local.date())
        if a is None:
            summary.unassigned_rows += 1
            continue
        if parsed.declared_unit and parsed.declared_unit != a.unit:
            # Trust the registry, but say so once.
            msg = (
                f"File header says Units: {parsed.declared_unit} but the registry has "
                f"{code} in {a.unit}; using the registry."
            )
            if msg not in summary.warnings:
                summary.warnings.append(msg)
        temp_c = None if pr.value is None else to_celsius(pr.value, a.unit)
        rows.append(
            _Row(
                ts_local=pr.ts_local,
                ts_utc=local_to_utc(pr.ts_local, tz),
                raw_value=pr.raw_value,
                temp_c=temp_c,
                fridge_id=a.fridge_id,
                line_no=pr.line_no,
                branch_id=a.fridge.branch_id,
            )
        )
    # Branch managers: every reading must belong to their branch on its date. Refuse the
    # whole file otherwise; never import part of it.
    if is_manager:
        assert user is not None
        foreign = sum(1 for r in rows if r.branch_id != user.branch_id)
        if foreign or summary.unassigned_rows:
            raise ImportForbidden(
                f"Logger {code} is not assigned to your branch for "
                f"{foreign + summary.unassigned_rows} of the readings in {filename}. "
                "Nothing was imported. Pick one of your branch's loggers, or ask Summer to "
                "update the Logger registry."
            )
    if summary.unassigned_rows:
        summary.warnings.append(
            f"{summary.unassigned_rows} row(s) fall outside every assignment of {code} "
            "and were not imported. Check the dates in the Logger registry."
        )
    if not rows:
        raise ImportRejected(
            f"None of the rows in {filename} fall inside an assignment of {code}. "
            "Check the logger's dates in the Logger registry."
        )

    # 5. Sort by time (out-of-order input is normal) and collapse exact duplicates.
    rows.sort(key=lambda r: (r.ts_utc, r.line_no))
    deduped: dict[datetime, _Row] = {}
    for r in rows:
        prev = deduped.get(r.ts_utc)
        if prev is not None:
            if prev.raw_value == r.raw_value:
                summary.duplicates += 1
                continue
            summary.warnings.append(
                f"{r.ts_local:%Y-%m-%d %H:%M} appears twice with different values "
                f"({prev.raw_value} / {r.raw_value}); kept the later line."
            )
            summary.duplicates += 1
        deduped[r.ts_utc] = r
    clean = list(deduped.values())
    summary.sensor_errors = sum(1 for r in clean if r.temp_c is None)
    summary.first_reading_local = clean[0].ts_local
    summary.last_reading_local = clean[-1].ts_local

    # 6. Keep the original bytes for audit, then record the upload.
    now = datetime.now(UTC).replace(tzinfo=None)
    target_dir = Path(settings.upload_dir) / code
    target_dir.mkdir(parents=True, exist_ok=True)
    stored = target_dir / f"{now:%Y%m%dT%H%M%S}_{sha[:12]}_{_safe_name(filename)}"
    stored.write_bytes(data)

    branches = [r.branch_id for r in clean]
    upload = Upload(
        logger_id=logger.id,
        branch_id=max(set(branches), key=branches.count),
        original_filename=filename[:255],
        sha256=sha,
        active_sha256=sha,
        stored_path=str(stored),
        row_count=len(clean),
        error_count=summary.sensor_errors,
        status=UPLOAD_ACTIVE,
        started_at=now,
        uploaded_by=user.id if user else None,
    )
    db.add(upload)
    db.flush()
    summary.upload_id = upload.id

    # 7. Idempotent upsert on (logger_id, ts_utc). Latest file wins on a different value.
    lo, hi = clean[0].ts_utc, clean[-1].ts_utc
    current = {
        r.ts_utc: r
        for r in db.scalars(
            select(Reading).where(
                Reading.logger_id == logger.id, Reading.ts_utc >= lo, Reading.ts_utc <= hi
            )
        )
    }
    overwritten = 0
    for r in clean:
        old = current.get(r.ts_utc)
        if old is None:
            db.add(
                Reading(
                    upload_id=upload.id,
                    logger_id=logger.id,
                    fridge_id=r.fridge_id,
                    ts_local=r.ts_local,
                    ts_utc=r.ts_utc,
                    raw_value=r.raw_value,
                    temp_c=r.temp_c,
                    status="err" if r.temp_c is None else "ok",
                )
            )
            summary.inserted += 1
        elif old.is_voided or old.raw_value != r.raw_value or old.fridge_id != r.fridge_id:
            if old.raw_value != r.raw_value and not old.is_voided:
                overwritten += 1
            old.is_voided = False
            old.upload_id = upload.id
            old.fridge_id = r.fridge_id
            old.ts_local = r.ts_local
            old.raw_value = r.raw_value
            old.temp_c = r.temp_c  # type: ignore[assignment]
            old.status = "err" if r.temp_c is None else "ok"
            summary.updated += 1
        else:
            summary.unchanged += 1
    if overwritten:
        summary.warnings.append(
            f"{overwritten} reading(s) already stored from an earlier upload had a different "
            "value; this file's value now wins."
        )
    db.flush()

    # 8. Recompute excursions and gaps for this logger and report what touches this file.
    analysis = recompute_logger(db, settings, logger.id)
    summary.excursions = sum(
        1 for e in analysis.excursions if e.end_utc >= lo and e.start_utc <= hi
    )
    summary.gaps = sum(1 for g in analysis.gaps if g.end_utc >= lo and g.start_utc <= hi)
    summary.spikes = sum(1 for s in analysis.spikes if lo <= s.ts_utc <= hi)

    upload.finished_at = datetime.now(UTC).replace(tzinfo=None)
    upload.note = "; ".join(summary.warnings)[:2000] or None
    db.commit()
    return summary


def logger_points(db: Session, logger_id: int) -> list[Point]:
    rows = db.execute(
        select(Reading.ts_utc, Reading.ts_local, Reading.temp_c, Reading.fridge_id, Reading.status)
        .where(Reading.logger_id == logger_id, Reading.is_voided.is_(False))
        .order_by(Reading.ts_utc)
    ).all()
    return [
        Point(r.ts_utc, r.ts_local, r.temp_c if r.status == "ok" else None, r.fridge_id)
        for r in rows
    ]


def recompute_logger(db: Session, settings: Settings, logger_id: int) -> Analysis:
    """Delete and rebuild the excursions and gaps of one logger.

    The whole logger history is recomputed rather than a window: a run can span two weekly
    files, and a year of 15-minute readings is ~35k rows, which is cheap.
    """
    analysis = analyze(
        logger_points(db, logger_id),
        threshold_c=settings.alert_threshold_c,
        interval_minutes=settings.sample_interval_minutes,
        min_readings=settings.min_excursion_readings,
    )
    db.execute(delete(Excursion).where(Excursion.logger_id == logger_id))
    db.execute(delete(Gap).where(Gap.logger_id == logger_id))
    for e in analysis.excursions:
        db.add(
            Excursion(
                fridge_id=e.fridge_id,
                logger_id=logger_id,
                start_utc=e.start_utc,
                end_utc=e.end_utc,
                start_local=e.start_local,
                end_local=e.end_local,
                duration_minutes=e.duration_minutes,
                peak_c=e.peak_c,
                n_readings=e.n_readings,
                is_open=e.is_open,
            )
        )
    for g in analysis.gaps:
        db.add(
            Gap(
                fridge_id=g.fridge_id,
                logger_id=logger_id,
                start_utc=g.start_utc,
                end_utc=g.end_utc,
                start_local=g.start_local,
                end_local=g.end_local,
                duration_minutes=g.duration_minutes,
            )
        )
    db.flush()
    return analysis


# ---------- void (soft delete) ----------


def _rows_from_stored_file(settings: Settings, logger: Logger, path: str) -> dict[datetime, _Row]:
    """Re-read an earlier upload's original file, normalised the same way as at import."""
    try:
        parsed = parse_bytes(Path(path).read_bytes())
    except (OSError, ParseError):
        return {}
    out: dict[datetime, _Row] = {}
    for pr in parsed.rows:
        a = assignment_for(logger.assignments, pr.ts_local.date())
        if a is None:
            continue
        ts_utc = local_to_utc(pr.ts_local, settings.tz)
        out[ts_utc] = _Row(
            ts_local=pr.ts_local,
            ts_utc=ts_utc,
            raw_value=pr.raw_value,
            temp_c=None if pr.value is None else to_celsius(pr.value, a.unit),
            fridge_id=a.fridge_id,
            line_no=pr.line_no,
            branch_id=a.fridge.branch_id,
        )
    return out


@dataclass
class VoidSummary:
    hidden: int = 0
    restored: int = 0


def void_upload(
    db: Session, settings: Settings, upload: Upload, user: User, reason: str
) -> VoidSummary:
    """Soft-delete an upload. Nothing is physically deleted: the uploads row and the original
    file stay, and its readings stay in the table. For each reading this upload wrote:

    * if an earlier, non-voided upload of the same logger also covers that timestamp, the
      earlier value comes back (re-read from that upload's stored original file);
    * otherwise the reading is marked ``is_voided`` and disappears from every view.

    Excursions and gaps for the logger are then recomputed without it.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    upload.status = UPLOAD_VOIDED
    upload.active_sha256 = None
    upload.voided_by = user.id
    upload.voided_at = now
    upload.void_reason = reason

    logger = db.get(Logger, upload.logger_id)
    assert logger is not None
    db.refresh(logger, attribute_names=["assignments"])
    owned = list(db.scalars(select(Reading).where(Reading.upload_id == upload.id)))

    # Earlier candidates, oldest first, so the latest of them wins a timestamp.
    others = list(
        db.scalars(
            select(Upload)
            .where(
                Upload.logger_id == upload.logger_id,
                Upload.id != upload.id,
                Upload.status != UPLOAD_VOIDED,
            )
            .order_by(Upload.id)
        )
    )
    fallback: dict[datetime, tuple[int, _Row]] = {}
    if owned and others:
        for other in others:
            for ts, row in _rows_from_stored_file(settings, logger, other.stored_path).items():
                fallback[ts] = (other.id, row)

    result = VoidSummary()
    for reading in owned:
        hit = fallback.get(reading.ts_utc)
        if hit is None:
            reading.is_voided = True
            result.hidden += 1
            continue
        other_id, row = hit
        reading.upload_id = other_id
        reading.fridge_id = row.fridge_id
        reading.ts_local = row.ts_local
        reading.raw_value = row.raw_value
        reading.temp_c = row.temp_c  # type: ignore[assignment]
        reading.status = "err" if row.temp_c is None else "ok"
        reading.is_voided = False
        result.restored += 1
    db.flush()
    recompute_logger(db, settings, upload.logger_id)
    return result


def fridge_branch(db: Session, fridge_id: int) -> int | None:
    f = db.get(Fridge, fridge_id)
    return f.branch_id if f else None
