"""Alert rules: excursions vs spikes, and gaps. Pure functions, no database.

Rules (they match ``data/expected_excursions.json``; changing them is a product decision):

* Only valid readings count. A reading is *above* when ``temp_c > threshold`` (strictly;
  5.0 exactly is fine).
* ``min_readings`` (default 2) or more consecutive above-threshold readings are an
  **excursion**. Fewer (a door opening) is a **spike**: shown on the chart, never an alert.
* A sensor error breaks a run. So does a hole longer than the sample interval, and so does
  a logger moving to another fridge.
* Duration is last minus first reading of the run, not until the first recovery reading.
* A **gap** is two successive readings (any status) more than one interval apart.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class Point:
    ts_utc: datetime
    ts_local: datetime
    temp_c: Decimal | None  # None = sensor error
    fridge_id: int


@dataclass(frozen=True)
class Span:
    fridge_id: int
    start_utc: datetime
    end_utc: datetime
    start_local: datetime
    end_local: datetime

    @property
    def duration_minutes(self) -> int:
        return int((self.end_utc - self.start_utc).total_seconds() // 60)


@dataclass(frozen=True)
class ExcursionSpan(Span):
    peak_c: Decimal
    n_readings: int
    is_open: bool


@dataclass(frozen=True)
class Spike:
    fridge_id: int
    ts_utc: datetime
    ts_local: datetime
    temp_c: Decimal


@dataclass
class Analysis:
    excursions: list[ExcursionSpan] = field(default_factory=list)
    spikes: list[Spike] = field(default_factory=list)
    gaps: list[Span] = field(default_factory=list)


def _segments(points: Sequence[Point]) -> list[list[Point]]:
    """Split a logger's readings wherever it moved to another fridge."""
    segments: list[list[Point]] = []
    for p in points:
        if segments and segments[-1][-1].fridge_id == p.fridge_id:
            segments[-1].append(p)
        else:
            segments.append([p])
    return segments


def analyze(
    points: Sequence[Point],
    threshold_c: float | Decimal = Decimal("5.0"),
    interval_minutes: int = 15,
    min_readings: int = 2,
) -> Analysis:
    """Analyse one logger's readings. ``points`` need not be sorted."""
    threshold = Decimal(str(threshold_c))
    max_step = timedelta(minutes=interval_minutes)
    out = Analysis()

    for seg in _segments(sorted(points, key=lambda p: p.ts_utc)):
        run: list[Point] = []

        def close_run(is_open: bool, run: list[Point] = run) -> None:
            if not run:
                return
            if len(run) >= min_readings:
                out.excursions.append(
                    ExcursionSpan(
                        fridge_id=run[0].fridge_id,
                        start_utc=run[0].ts_utc,
                        end_utc=run[-1].ts_utc,
                        start_local=run[0].ts_local,
                        end_local=run[-1].ts_local,
                        peak_c=max(p.temp_c for p in run if p.temp_c is not None),
                        n_readings=len(run),
                        is_open=is_open,
                    )
                )
            else:
                out.spikes.extend(
                    Spike(p.fridge_id, p.ts_utc, p.ts_local, p.temp_c)
                    for p in run
                    if p.temp_c is not None
                )
            run.clear()

        prev: Point | None = None
        for p in seg:
            if prev is not None and p.ts_utc - prev.ts_utc > max_step:
                out.gaps.append(Span(p.fridge_id, prev.ts_utc, p.ts_utc, prev.ts_local, p.ts_local))
                close_run(is_open=False)
            if p.temp_c is None or p.temp_c <= threshold:
                close_run(is_open=False)
            else:
                run.append(p)
            prev = p
        # A run still going at the last reading has not recovered (yet): it is open.
        close_run(is_open=True)

    return out
