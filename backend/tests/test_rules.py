from datetime import datetime, timedelta
from decimal import Decimal

from app.rules import Point, analyze

T0 = datetime(2026, 9, 14, 6, 0)


def series(*temps, step=15, fridge=1, start=T0):
    """Build points from temps; None = ERR, "gap:N" skips N extra slots."""
    pts, t = [], start
    for v in temps:
        if isinstance(v, str) and v.startswith("gap:"):
            t += timedelta(minutes=step * int(v[4:]))
            continue
        pts.append(Point(t, t, None if v is None else Decimal(str(v)), fridge))
        t += timedelta(minutes=step)
    return pts


def test_isolated_reading_is_a_spike_not_an_excursion():
    a = analyze(series(4.0, 9.4, 4.3))
    assert a.excursions == []
    assert [float(s.temp_c) for s in a.spikes] == [9.4]


def test_two_consecutive_readings_are_an_excursion():
    a = analyze(series(4.0, 5.3, 6.8, 4.4))
    (e,) = a.excursions
    assert (e.n_readings, e.duration_minutes, e.peak_c, e.is_open) == (2, 15, Decimal("6.8"), False)
    assert a.spikes == []


def test_exactly_five_is_not_above():
    a = analyze(series(5.0, 5.0, 5.0))
    assert a.excursions == [] and a.spikes == []


def test_err_breaks_a_run():
    a = analyze(series(4.0, 6.0, None, 6.0, 4.0))
    assert a.excursions == []
    assert len(a.spikes) == 2


def test_gap_longer_than_interval_breaks_a_run_and_is_recorded():
    a = analyze(series(4.0, 6.0, "gap:7", 6.0, 4.0))
    assert a.excursions == []
    assert len(a.spikes) == 2
    (g,) = a.gaps
    assert g.duration_minutes == 120


def test_exactly_one_interval_is_not_a_gap():
    assert analyze(series(4.0, 4.0, 4.0)).gaps == []


def test_duration_is_first_to_last_reading_not_until_recovery():
    # Ashdod fixture: 03:00..04:00 above, 04:15 recovered -> 60 minutes, 5 readings.
    start = datetime(2026, 9, 16, 2, 45)
    a = analyze(series(3.8, 5.3, 6.8, 7.4, 6.1, 5.2, 4.4, start=start))
    (e,) = a.excursions
    assert e.start_local == datetime(2026, 9, 16, 3, 0)
    assert e.end_local == datetime(2026, 9, 16, 4, 0)
    assert (e.duration_minutes, e.n_readings, e.peak_c) == (60, 5, Decimal("7.4"))


def test_run_still_above_at_last_reading_is_open():
    (e,) = analyze(series(4.0, 6.0, 7.0)).excursions
    assert e.is_open


def test_logger_move_breaks_a_run():
    pts = series(6.0, fridge=1) + series(6.0, fridge=2, start=T0 + timedelta(minutes=15))
    a = analyze(pts)
    assert a.excursions == [] and len(a.spikes) == 2


def test_unsorted_input_is_sorted():
    pts = series(4.0, 6.0, 7.0, 4.0)
    a = analyze(list(reversed(pts)))
    assert len(a.excursions) == 1


def test_thresholds_are_configurable():
    a = analyze(series(4.0, 6.0, 4.0), threshold_c=5.0, min_readings=1)
    assert len(a.excursions) == 1
