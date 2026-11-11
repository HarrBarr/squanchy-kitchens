from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.normalize import assignment_for, local_to_utc, to_celsius, utc_to_local

TZ = ZoneInfo("Asia/Jerusalem")


def test_september_is_idt_plus_three():
    assert local_to_utc(datetime(2026, 9, 14, 6, 0), TZ) == datetime(2026, 9, 14, 3, 0)


def test_january_is_ist_plus_two():
    assert local_to_utc(datetime(2026, 1, 14, 6, 0), TZ) == datetime(2026, 1, 14, 4, 0)


def test_round_trip():
    ts = datetime(2026, 9, 20, 23, 45)
    assert utc_to_local(local_to_utc(ts, TZ), TZ) == ts


def test_haifa_fahrenheit_pin():
    assert to_celsius(Decimal("38.3"), "F") == Decimal("3.50")
    assert to_celsius(Decimal("39.0"), "F") == Decimal("3.89")


def test_celsius_is_untouched():
    assert to_celsius(Decimal("9.4"), "C") == Decimal("9.40")


def test_unknown_unit_rejected():
    with pytest.raises(ValueError):
        to_celsius(Decimal("1"), "K")


def test_assignment_to_is_inclusive_of_the_local_day():
    walk_in = SimpleNamespace(assigned_from=date(2026, 1, 1), assigned_to=date(2026, 9, 16), f=1)
    display = SimpleNamespace(assigned_from=date(2026, 9, 17), assigned_to=None, f=2)
    both = [walk_in, display]
    assert assignment_for(both, date(2026, 9, 16)) is walk_in
    assert assignment_for(both, date(2026, 9, 17)) is display
    assert assignment_for(both, date(2025, 12, 31)) is None
