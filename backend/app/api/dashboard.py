"""Dashboard: one card per fridge, coloured red / amber / green (grey = no readings).

* red   - at least one excursion overlaps the period ("ongoing" badge if not recovered)
* amber - no excursion, but a gap or a sensor error in the period
* green - otherwise; isolated spikes stay green (a door opening is fine)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.period import Period, fmt_duration, resolve_period
from app.config import Settings, get_settings
from app.rules import Point, Spike, analyze
from app.storage.models import Branch, Excursion, Fridge, Gap, Logger, LoggerAssignment, Reading
from app.storage.session import get_db

router = APIRouter(prefix="/api", tags=["dashboard"])


class FridgeCard(BaseModel):
    fridge_id: int
    branch: str
    fridge: str
    loggers: list[str]
    colour: str  # red | amber | green | grey
    ongoing: bool
    reason: str
    last_temp_c: float | None
    last_reading_local: datetime | None
    excursion_count: int
    gap_count: int
    error_count: int
    spike_count: int
    peak_c: float | None


class DashboardOut(BaseModel):
    period_from: date
    period_to: date
    period_label: str
    threshold_c: float
    counts: dict[str, int]
    fridges: list[FridgeCard]


def period_spikes(
    db: Session, settings: Settings, period: Period, fridge_id: int | None = None
) -> list[tuple[int, Spike]]:
    """Spikes are not stored (they are not alerts); derive them from the readings. The window
    is padded so a run crossing the period edge is judged on its full length."""
    pad = timedelta(minutes=settings.sample_interval_minutes * settings.min_excursion_readings)
    q = select(
        Reading.logger_id,
        Reading.ts_utc,
        Reading.ts_local,
        Reading.temp_c,
        Reading.status,
        Reading.fridge_id,
    ).where(Reading.ts_utc >= period.start_utc - pad, Reading.ts_utc < period.end_utc + pad)
    if fridge_id is not None:
        q = q.where(Reading.fridge_id == fridge_id)
    by_logger: dict[int, list[Point]] = defaultdict(list)
    for r in db.execute(q):
        by_logger[r.logger_id].append(
            Point(r.ts_utc, r.ts_local, r.temp_c if r.status == "ok" else None, r.fridge_id)
        )
    out: list[tuple[int, Spike]] = []
    for logger_id, pts in by_logger.items():
        a = analyze(
            pts,
            settings.alert_threshold_c,
            settings.sample_interval_minutes,
            settings.min_excursion_readings,
        )
        out.extend(
            (logger_id, s) for s in a.spikes if period.start_utc <= s.ts_utc < period.end_utc
        )
    return out


def _f(x: Decimal | None) -> float | None:
    return None if x is None else float(x)


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    branch: str | None = Query(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DashboardOut:
    period = resolve_period(db, settings, from_, to)
    in_period = (Reading.ts_utc >= period.start_utc, Reading.ts_utc < period.end_utc)

    fq = select(Fridge).join(Branch).options(selectinload(Fridge.branch))
    if branch:
        fq = fq.where(Branch.name == branch)
    fridges = list(db.scalars(fq.order_by(Branch.name, Fridge.name)))

    # Loggers that fed each fridge in the period, else the current assignment.
    loggers: dict[int, set[str]] = defaultdict(set)
    for fid, code in db.execute(
        select(Reading.fridge_id, Logger.logger_code)
        .join(Logger, Logger.id == Reading.logger_id)
        .where(*in_period)
        .distinct()
    ):
        loggers[fid].add(code)
    for a in db.scalars(
        select(LoggerAssignment)
        .where(LoggerAssignment.assigned_to.is_(None))
        .options(selectinload(LoggerAssignment.logger))
    ):
        if not loggers[a.fridge_id]:
            loggers[a.fridge_id].add(a.logger.logger_code)

    last: dict[int, tuple[datetime, Decimal | None, str]] = {}
    errors: dict[int, int] = defaultdict(int)
    for fid, _ts_utc, ts_local, temp, status in db.execute(
        select(Reading.fridge_id, Reading.ts_utc, Reading.ts_local, Reading.temp_c, Reading.status)
        .where(*in_period)
        .order_by(Reading.ts_utc)
    ):
        last[fid] = (ts_local, temp, status)
        if status == "err":
            errors[fid] += 1

    excursions: dict[int, list[Excursion]] = defaultdict(list)
    for e in db.scalars(
        select(Excursion)
        .where(Excursion.start_utc < period.end_utc, Excursion.end_utc >= period.start_utc)
        .order_by(Excursion.start_utc)
    ):
        excursions[e.fridge_id].append(e)
    gaps: dict[int, list[Gap]] = defaultdict(list)
    for g in db.scalars(
        select(Gap)
        .where(Gap.start_utc < period.end_utc, Gap.end_utc > period.start_utc)
        .order_by(Gap.start_utc)
    ):
        gaps[g.fridge_id].append(g)
    spikes: dict[int, int] = defaultdict(int)
    for _, s in period_spikes(db, settings, period):
        spikes[s.fridge_id] += 1

    cards: list[FridgeCard] = []
    for f in fridges:
        exc, gp, err = excursions[f.id], gaps[f.id], errors[f.id]
        lst = last.get(f.id)
        ongoing = any(e.is_open for e in exc)
        peak = max((e.peak_c for e in exc), default=None)
        if exc:
            colour = "red"
            if ongoing:
                e = next(e for e in exc if e.is_open)
                reason = (
                    f"Ongoing {float(e.peak_c):.1f}°C peak since {e.start_local:%a %d %b %H:%M}"
                )
            else:
                e = max(exc, key=lambda x: x.peak_c)
                reason = (
                    f"{len(exc)} excursion{'s' if len(exc) > 1 else ''}: peak "
                    f"{float(e.peak_c):.1f}°C for {fmt_duration(e.duration_minutes)} on "
                    f"{e.start_local:%a %d %b %H:%M}"
                )
        elif gp or err:
            colour = "amber"
            bits = []
            if gp:
                g = max(gp, key=lambda x: x.duration_minutes)
                same_day = g.start_local.date() == g.end_local.date()
                when = (
                    f"{g.start_local:%d %b}"
                    if same_day
                    else f"{g.start_local:%d}–{g.end_local:%d %b}"
                )
                bits.append(f"Gap {fmt_duration(g.duration_minutes)} on {when}")
                if len(gp) > 1:
                    bits[-1] += f" (+{len(gp) - 1} more)"
            if err:
                bits.append(f"{err} sensor error{'s' if err > 1 else ''}")
            reason = " · ".join(bits)
        elif lst is None:
            colour, reason = "grey", "No readings in this period"
        else:
            colour, reason = "green", "OK"
        cards.append(
            FridgeCard(
                fridge_id=f.id,
                branch=f.branch.name,
                fridge=f.name,
                loggers=sorted(loggers[f.id]),
                colour=colour,
                ongoing=ongoing,
                reason=reason,
                last_temp_c=_f(lst[1]) if lst else None,
                last_reading_local=lst[0] if lst else None,
                excursion_count=len(exc),
                gap_count=len(gp),
                error_count=err,
                spike_count=spikes[f.id],
                peak_c=_f(peak),
            )
        )

    order = {"red": 0, "amber": 1, "grey": 2, "green": 3}
    cards.sort(key=lambda c: (order[c.colour], not c.ongoing, c.branch, c.fridge))
    counts = {k: sum(1 for c in cards if c.colour == k) for k in order}
    return DashboardOut(
        period_from=period.start,
        period_to=period.end,
        period_label=period.label,
        threshold_c=settings.alert_threshold_c,
        counts=counts,
        fridges=cards,
    )
