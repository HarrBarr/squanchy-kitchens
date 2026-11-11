from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dashboard import period_spikes
from app.api.period import resolve_period
from app.config import Settings, get_settings
from app.storage.models import Excursion, Fridge, Gap, Logger, Reading
from app.storage.session import get_db

router = APIRouter(prefix="/api", tags=["fridges"])


class SeriesPoint(BaseModel):
    ts_local: datetime
    temp_c: float | None
    status: str
    raw_value: str
    logger: str


class SpanOut(BaseModel):
    start_local: datetime
    end_local: datetime
    duration_minutes: int
    logger: str


class ExcursionOut(SpanOut):
    peak_c: float
    n_readings: int
    is_open: bool


class SpikeOut(BaseModel):
    ts_local: datetime
    temp_c: float
    logger: str


class SeriesOut(BaseModel):
    fridge_id: int
    branch: str
    fridge: str
    period_from: date
    period_to: date
    period_label: str
    threshold_c: float
    sample_interval_minutes: int
    readings: list[SeriesPoint]
    gaps: list[SpanOut]
    excursions: list[ExcursionOut]
    spikes: list[SpikeOut]


@router.get("/fridges/{fridge_id}/series", response_model=SeriesOut)
def fridge_series(
    fridge_id: int,
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SeriesOut:
    fridge = db.scalar(
        select(Fridge).where(Fridge.id == fridge_id).options(selectinload(Fridge.branch))
    )
    if fridge is None:
        raise HTTPException(404, "Fridge not found.")
    period = resolve_period(db, settings, from_, to, fridge_id=fridge_id)
    codes: dict[int, str] = {i: c for i, c in db.execute(select(Logger.id, Logger.logger_code))}

    readings = [
        SeriesPoint(
            ts_local=r.ts_local,
            temp_c=None if r.temp_c is None else float(r.temp_c),
            status=r.status,
            raw_value=r.raw_value,
            logger=codes[r.logger_id],
        )
        for r in db.scalars(
            select(Reading)
            .where(
                Reading.fridge_id == fridge_id,
                Reading.ts_utc >= period.start_utc,
                Reading.ts_utc < period.end_utc,
            )
            .order_by(Reading.ts_utc)
        )
    ]
    gaps = [
        SpanOut(
            start_local=g.start_local,
            end_local=g.end_local,
            duration_minutes=g.duration_minutes,
            logger=codes[g.logger_id],
        )
        for g in db.scalars(
            select(Gap)
            .where(
                Gap.fridge_id == fridge_id,
                Gap.start_utc < period.end_utc,
                Gap.end_utc > period.start_utc,
            )
            .order_by(Gap.start_utc)
        )
    ]
    excursions = [
        ExcursionOut(
            start_local=e.start_local,
            end_local=e.end_local,
            duration_minutes=e.duration_minutes,
            logger=codes[e.logger_id],
            peak_c=float(e.peak_c),
            n_readings=e.n_readings,
            is_open=e.is_open,
        )
        for e in db.scalars(
            select(Excursion)
            .where(
                Excursion.fridge_id == fridge_id,
                Excursion.start_utc < period.end_utc,
                Excursion.end_utc >= period.start_utc,
            )
            .order_by(Excursion.start_utc)
        )
    ]
    spikes = [
        SpikeOut(ts_local=s.ts_local, temp_c=float(s.temp_c), logger=codes[lid])
        for lid, s in sorted(
            period_spikes(db, settings, period, fridge_id), key=lambda x: x[1].ts_utc
        )
    ]
    return SeriesOut(
        fridge_id=fridge.id,
        branch=fridge.branch.name,
        fridge=fridge.name,
        period_from=period.start,
        period_to=period.end,
        period_label=period.label,
        threshold_c=settings.alert_threshold_c,
        sample_interval_minutes=settings.sample_interval_minutes,
        readings=readings,
        gaps=gaps,
        excursions=excursions,
        spikes=spikes,
    )
