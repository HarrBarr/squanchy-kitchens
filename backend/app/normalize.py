"""Timezone, unit and assignment normalisation.

* Files carry no offset: every timestamp is Asia/Jerusalem wall-clock time, converted with
  ``zoneinfo`` so DST is right (IDT +3 in summer, IST +2 in winter). Never a fixed +03:00.
* The unit comes from the logger assignment in the registry. We never guess Fahrenheit from
  the size of the number.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

TWO_PLACES = Decimal("0.01")


def local_to_utc(ts_local: datetime, tz: ZoneInfo) -> datetime:
    """Naive local wall-clock time -> naive UTC. In the repeated autumn hour the first
    occurrence (fold=0, still summer time) is used; the files give us no way to tell."""
    return ts_local.replace(tzinfo=tz).astimezone(UTC).replace(tzinfo=None)


def utc_to_local(ts_utc: datetime, tz: ZoneInfo) -> datetime:
    return ts_utc.replace(tzinfo=UTC).astimezone(tz).replace(tzinfo=None)


def to_celsius(value: Decimal, unit: str) -> Decimal:
    """Convert a raw reading to Celsius, rounded to 2 dp (the stored DECIMAL(6,2))."""
    unit = unit.upper()
    if unit == "F":
        c = (value - 32) * 5 / Decimal(9)
    elif unit == "C":
        c = value
    else:
        raise ValueError(f"Unknown unit {unit!r}")
    return c.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class AssignmentLike(Protocol):
    assigned_from: date
    assigned_to: date | None


def assignment_for[A: AssignmentLike](assignments: Iterable[A], day: date) -> A | None:
    """The assignment in force on a local calendar day. ``assigned_to`` is inclusive."""
    for a in assignments:
        if a.assigned_from <= day and (a.assigned_to is None or day <= a.assigned_to):
            return a
    return None
