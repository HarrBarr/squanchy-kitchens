"""Period handling shared by the dashboard, the chart and the report.

A period is a pair of *local* calendar dates (Asia/Jerusalem), inclusive on both ends.
The default is the ISO week of the latest reading in the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.normalize import local_to_utc
from app.storage.models import Reading


@dataclass(frozen=True)
class Period:
    start: date  # inclusive, local
    end: date  # inclusive, local
    start_utc: datetime
    end_utc: datetime  # exclusive: local midnight after `end`, in UTC

    @property
    def label(self) -> str:
        iso = self.start.isocalendar()
        if self.start.weekday() == 0 and self.end == self.start + timedelta(days=6):
            return f"{iso.year}-W{iso.week:02d}"
        return f"{self.start:%d %b} – {self.end:%d %b %Y}"


def latest_week(db: Session, fridge_id: int | None = None) -> tuple[date, date] | None:
    q = select(func.max(Reading.ts_local))
    if fridge_id is not None:
        q = q.where(Reading.fridge_id == fridge_id)
    latest = db.scalar(q)
    if latest is None:
        return None
    monday = latest.date() - timedelta(days=latest.weekday())
    return monday, monday + timedelta(days=6)


def resolve_period(
    db: Session,
    settings: Settings,
    start: date | None,
    end: date | None,
    fridge_id: int | None = None,
) -> Period:
    if start is None and end is None:
        wk = latest_week(db, fridge_id) or latest_week(db)
        if wk is None:
            today = datetime.now(settings.tz).date()
            monday = today - timedelta(days=today.weekday())
            wk = (monday, monday + timedelta(days=6))
        start, end = wk
    elif start is None:
        assert end is not None
        start = end - timedelta(days=6)
    elif end is None:
        end = start + timedelta(days=6)
    if end < start:
        raise HTTPException(422, "'to' must be on or after 'from'.")
    tz = settings.tz
    return Period(
        start=start,
        end=end,
        start_utc=local_to_utc(datetime.combine(start, time.min), tz),
        end_utc=local_to_utc(datetime.combine(end + timedelta(days=1), time.min), tz),
    )


def fmt_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    days, rem = divmod(minutes, 24 * 60)
    hours, mins = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    if mins and not days:
        parts.append(f"{mins} min")
    return " ".join(parts) or "0 min"
