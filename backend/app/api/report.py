"""Inspector report: every excursion (not spikes) in the period, as JSON or CSV."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.period import Period, fmt_duration, resolve_period
from app.auth import BranchScope, audit, branch_scope, forbidden
from app.config import Settings, get_settings
from app.storage.models import Branch, Excursion, Fridge
from app.storage.session import get_db

router = APIRouter(prefix="/api", tags=["report"])


class ReportRow(BaseModel):
    id: int
    branch: str
    fridge: str
    fridge_id: int
    logger: str
    start_local: datetime
    end_local: datetime
    duration_minutes: int
    duration_label: str
    peak_c: float
    n_readings: int
    is_open: bool


class ReportOut(BaseModel):
    period_from: date
    period_to: date
    period_label: str
    timezone: str
    threshold_c: float
    rows: list[ReportRow]


def _peak_1dp(x: Decimal) -> float:
    return float(x.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _scoped_period(
    db: Session,
    settings: Settings,
    scope: BranchScope,
    from_: date | None,
    to: date | None,
    fridge: int | None,
) -> Period:
    if fridge is not None:
        f = db.get(Fridge, fridge)
        if f is None or not scope.allows_branch(f.branch_id):
            raise forbidden("This fridge belongs to another branch.")
    ids = None
    if scope.branch_id is not None:
        ids = list(db.scalars(select(Fridge.id).where(Fridge.branch_id == scope.branch_id)))
    return resolve_period(db, settings, from_, to, fridge_ids=ids)


def _rows(
    db: Session, period: Period, branch_id: int | None, fridge: int | None
) -> list[ReportRow]:
    q = (
        select(Excursion)
        .join(Fridge, Fridge.id == Excursion.fridge_id)
        .join(Branch, Branch.id == Fridge.branch_id)
        .where(Excursion.start_utc < period.end_utc, Excursion.end_utc >= period.start_utc)
        .options(
            selectinload(Excursion.fridge).selectinload(Fridge.branch),
            selectinload(Excursion.logger),
        )
        .order_by(Excursion.start_utc)
    )
    if branch_id is not None:
        q = q.where(Branch.id == branch_id)
    if fridge:
        q = q.where(Fridge.id == fridge)
    return [
        ReportRow(
            id=e.id,
            branch=e.fridge.branch.name,
            fridge=e.fridge.name,
            fridge_id=e.fridge_id,
            logger=e.logger.logger_code,
            start_local=e.start_local,
            end_local=e.end_local,
            duration_minutes=e.duration_minutes,
            duration_label=fmt_duration(e.duration_minutes),
            peak_c=_peak_1dp(e.peak_c),
            n_readings=e.n_readings,
            is_open=e.is_open,
        )
        for e in db.scalars(q)
    ]


@router.get("/report", response_model=ReportOut)
def report(
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    fridge: int | None = Query(None),
    scope: BranchScope = Depends(branch_scope),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReportOut:
    """Inspector list. Branch managers: their branch only; admins: one branch or all."""
    period = _scoped_period(db, settings, scope, from_, to, fridge)
    return ReportOut(
        period_from=period.start,
        period_to=period.end,
        period_label=period.label,
        timezone=settings.app_timezone,
        threshold_c=settings.alert_threshold_c,
        rows=_rows(db, period, scope.branch_id, fridge),
    )


@router.get("/report.csv")
def report_csv(
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    fridge: int | None = Query(None),
    scope: BranchScope = Depends(branch_scope),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """CSV export of the inspector list. Every export is written to the audit log."""
    period = _scoped_period(db, settings, scope, from_, to, fridge)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "Branch",
            "Fridge",
            "Logger",
            f"Start ({settings.app_timezone})",
            f"End ({settings.app_timezone})",
            "Duration (min)",
            "Duration",
            "Peak °C",
            "Readings above limit",
            "Status",
        ]
    )
    rows = _rows(db, period, scope.branch_id, fridge)
    audit(
        db,
        scope.user,
        "report.exported",
        "report",
        None,
        branch=scope.branch_name or "all branches",
        fridge_id=fridge,
        period_from=period.start.isoformat(),
        period_to=period.end.isoformat(),
        rows=len(rows),
        format="csv",
    )
    db.commit()
    for r in rows:
        w.writerow(
            [
                r.branch,
                r.fridge,
                r.logger,
                f"{r.start_local:%Y-%m-%d %H:%M}",
                f"{r.end_local:%Y-%m-%d %H:%M}",
                r.duration_minutes,
                r.duration_label,
                f"{r.peak_c:.1f}",
                r.n_readings,
                "ongoing at last reading" if r.is_open else "recovered",
            ]
        )
    name = f"squanchy-excursions_{period.start:%Y-%m-%d}_{period.end:%Y-%m-%d}.csv"
    # UTF-8 BOM so Excel shows "°C" and "Be'er Sheva" correctly.
    return StreamingResponse(
        iter(["﻿" + buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
