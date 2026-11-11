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
from app.storage.models import Excursion, Gap, Logger, Reading, Upload

LOGGER_CODE_RE = re.compile(r"TL-\d{3,6}", re.IGNORECASE)


class ImportRejected(Exception):
    """The upload cannot be imported; nothing was written. Maps to HTTP 422."""


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


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name)[:120] or "upload.csv"


def import_file(
    db: Session, settings: Settings, filename: str, data: bytes, logger_code: str
) -> ImportSummary:
    code = logger_code.strip().upper()
    sha = hashlib.sha256(data).hexdigest()
    summary = ImportSummary(logger=code, filename=filename, sha256=sha)

    # 1. Identical bytes were already imported: no-op.
    existing = db.scalar(select(Upload).where(Upload.sha256 == sha))
    if existing is not None:
        summary.already_imported = True
        summary.upload_id = existing.id
        summary.rows_in_file = existing.row_count
        summary.sensor_errors = existing.error_count
        return summary

    # 2. The logger must be in the registry. Nothing is parsed into readings otherwise.
    logger = db.scalar(
        select(Logger).where(Logger.logger_code == code).options(selectinload(Logger.assignments))
    )
    if logger is None:
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
            )
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

    upload = Upload(
        logger_id=logger.id,
        original_filename=filename[:255],
        sha256=sha,
        stored_path=str(stored),
        row_count=len(clean),
        error_count=summary.sensor_errors,
        status="imported",
        started_at=now,
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
        elif old.raw_value != r.raw_value or old.fridge_id != r.fridge_id:
            if old.raw_value != r.raw_value:
                overwritten += 1
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
        .where(Reading.logger_id == logger_id)
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
