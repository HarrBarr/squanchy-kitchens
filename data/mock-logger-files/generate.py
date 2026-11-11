#!/usr/bin/env python3
"""Deterministic generator for Squanchy Bakery mock temperature-logger files.

Week of 2026-09-14 (ISO week 38), Asia/Jerusalem local time.
Readings every 15 minutes. Raw files contain only time and temperature
(plus, on some loggers, a short device header). Branch and fridge are
not in the files — they live in loggers.csv.

Re-run:

    python generate.py

All output is written next to this script. Randomness is seeded so the
same files are produced every time.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

SEED = 20260914
START = datetime(2026, 9, 14, 0, 0)
END = datetime(2026, 9, 20, 23, 45)
INTERVAL = timedelta(minutes=15)
WEEK_TAG = "2026-W38"
OUT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Formats. Summer said "the columns move around" and files "don't look quite
# the same from branch to branch". Each format is a realistic cheap-logger
# export flavour.
# ---------------------------------------------------------------------------

FORMATS: dict[str, dict] = {
    "csv_iso": {
        "desc": "CSV with header `timestamp,temp_c`; times as `YYYY-MM-DD HH:MM`; comma-separated.",
        "delimiter": ",",
        "headers": ["timestamp", "temp_c"],
        "time_fmt": "%Y-%m-%d %H:%M",
        "order": "time_temp",
        "preamble": False,
    },
    "reversed": {
        "desc": "CSV with reversed columns `Temp,Time`; times as `YYYY-MM-DD HH:MM`; comma-separated.",
        "delimiter": ",",
        "headers": ["Temp", "Time"],
        "time_fmt": "%Y-%m-%d %H:%M",
        "order": "temp_time",
        "preamble": False,
    },
    "meta_iso_t": {
        "desc": "Three metadata lines (`Serial`, `Model`, `Units`) then `datetime,temperature` with ISO 8601 `T` timestamps (`YYYY-MM-DDTHH:MM:SS`).",
        "delimiter": ",",
        "headers": ["datetime", "temperature"],
        "time_fmt": "%Y-%m-%dT%H:%M:%S",
        "order": "time_temp",
        "preamble": True,
    },
    "semicolon": {
        "desc": "Semicolon-delimited `time;temperature`; times as `YYYY-MM-DD HH:MM`.",
        "delimiter": ";",
        "headers": ["time", "temperature"],
        "time_fmt": "%Y-%m-%d %H:%M",
        "order": "time_temp",
        "preamble": False,
    },
    "meta_semicolon": {
        "desc": "Two-to-three metadata lines, then semicolon-delimited `Time;Temp`; times as `YYYY-MM-DD HH:MM`.",
        "delimiter": ";",
        "headers": ["Time", "Temp"],
        "time_fmt": "%Y-%m-%d %H:%M",
        "order": "time_temp",
        "preamble": True,
    },
    "iso_t": {
        "desc": "CSV with header `Time Stamp,Temperature (C)` and ISO 8601 `T` timestamps.",
        "delimiter": ",",
        "headers": ["Time Stamp", "Temperature (C)"],
        "time_fmt": "%Y-%m-%dT%H:%M:%S",
        "order": "time_temp",
        "preamble": False,
    },
    "tab": {
        "desc": "Tab-separated `timestamp\\ttemp`; times as `YYYY-MM-DD HH:MM`.",
        "delimiter": "\t",
        "headers": ["timestamp", "temp"],
        "time_fmt": "%Y-%m-%d %H:%M",
        "order": "time_temp",
        "preamble": False,
    },
    "verbose": {
        "desc": "CSV with header `Logged At,Temperature C`; times as `YYYY-MM-DD HH:MM`.",
        "delimiter": ",",
        "headers": ["Logged At", "Temperature C"],
        "time_fmt": "%Y-%m-%d %H:%M",
        "order": "time_temp",
        "preamble": False,
    },
    "haifa_legacy": {
        "desc": "Legacy LogiTemp LT-1 export: three metadata lines (`Serial`, `Model`, `Units: F`), header `Date,Temperature`, times as `DD/MM/YYYY HH:MM`, temperatures in Fahrenheit. `ERR` appears in the temperature column when the sensor fails to read.",
        "delimiter": ",",
        "headers": ["Date", "Temperature"],
        "time_fmt": "%d/%m/%Y %H:%M",
        "order": "time_temp",
        "preamble": True,
        "units": "F",
    },
}

ROTATING_FORMATS = [
    "csv_iso",
    "reversed",
    "meta_iso_t",
    "semicolon",
    "meta_semicolon",
    "iso_t",
    "tab",
    "verbose",
]


@dataclass
class Assignment:
    logger_id: str
    branch: str
    fridge: str
    unit: str  # "C" or "F"
    assigned_from: str  # YYYY-MM-DD
    assigned_to: str  # YYYY-MM-DD or ""
    model: str = "LogiTemp LT-2"


@dataclass
class LoggerSpec:
    logger_id: str
    format_key: str
    assignments: list[Assignment]
    baseline_c: float
    # Optional bounds for the file's time range (inclusive). None = full week.
    series_from: datetime | None = None
    series_to: datetime | None = None


def rng_for(key: str) -> random.Random:
    return random.Random(f"{SEED}:{key}")


def all_slots(start: datetime = START, end: datetime = END) -> list[datetime]:
    slots: list[datetime] = []
    t = start
    while t <= end:
        slots.append(t)
        t += INTERVAL
    return slots


def fmt_temp(value: float) -> str:
    return f"{value:.1f}"


def c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def daily_cycle(t: datetime) -> float:
    """Slight afternoon rise / pre-dawn dip, in °C."""
    hour = t.hour + t.minute / 60.0
    return 0.22 * math.sin((hour - 9.0) / 24.0 * 2.0 * math.pi)


def healthy_value(rng: random.Random, t: datetime, baseline: float, lo: float, hi: float) -> float:
    raw = baseline + daily_cycle(t) + rng.gauss(0.0, 0.10)
    return round(min(hi, max(lo, raw)), 1)


# ---------------------------------------------------------------------------
# Fleet: 12 branches, 2–4 fridges each, 31 loggers. Sample-table loggers
# keep their original IDs. One extra assignment row covers the Tel Aviv move.
# ---------------------------------------------------------------------------

def build_fleet() -> list[LoggerSpec]:
    # Explicit format overrides for the highlighted loggers; the rest rotate.
    overrides = {
        "TL-0512": "csv_iso",
        "TL-0417": "reversed",
        "TL-0231": "haifa_legacy",
        "TL-0388": "meta_iso_t",
        "TL-0601": "semicolon",
        "TL-0901": "meta_semicolon",
        "TL-1101": "iso_t",
        "TL-0420": "csv_iso",
        "TL-0419": "reversed",
        "TL-0513": "tab",
        "TL-0232": "verbose",
        "TL-0389": "meta_semicolon",
    }

    # (logger_id, branch, fridge, unit, assigned_from, assigned_to, baseline_c, model)
    # TL-0417 is added as two assignment rows below.
    rows: list[tuple] = [
        ("TL-0512", "Jerusalem", "Dairy", "C", "2026-01-01", "", 3.6, "LogiTemp LT-2"),
        ("TL-0513", "Jerusalem", "Walk-in", "C", "2026-01-01", "", 3.3, "LogiTemp LT-2"),
        ("TL-0514", "Jerusalem", "Display 1", "C", "2026-01-01", "", 3.9, "LogiTemp LT-3"),
        ("TL-0418", "Tel Aviv", "Cream cakes", "C", "2026-01-01", "", 3.8, "LogiTemp LT-2"),
        ("TL-0419", "Tel Aviv", "Display 1", "C", "2026-01-01", "", 3.9, "LogiTemp LT-3"),
        # Replacement clipped into the Tel Aviv walk-in after TL-0417 was moved.
        ("TL-0420", "Tel Aviv", "Walk-in", "C", "2026-09-17", "", 3.5, "LogiTemp LT-3"),
        ("TL-0231", "Haifa", "Dairy", "F", "2026-01-01", "", 3.6, "LogiTemp LT-1"),
        ("TL-0232", "Haifa", "Walk-in", "C", "2026-01-01", "", 3.4, "LogiTemp LT-2"),
        ("TL-0233", "Haifa", "Cream cakes", "C", "2026-01-01", "", 3.8, "LogiTemp LT-2"),
        ("TL-0388", "Rishon LeZion", "Cream cakes", "C", "2026-01-01", "", 4.0, "LogiTemp LT-2"),
        ("TL-0389", "Rishon LeZion", "Dairy", "C", "2026-01-01", "", 3.5, "LogiTemp LT-2"),
        ("TL-0390", "Rishon LeZion", "Walk-in", "C", "2026-01-01", "", 3.3, "LogiTemp LT-2"),
        ("TL-0601", "Be'er Sheva", "Dairy", "C", "2026-01-01", "", 3.5, "LogiTemp LT-2"),
        ("TL-0602", "Be'er Sheva", "Walk-in", "C", "2026-01-01", "", 3.2, "LogiTemp LT-2"),
        ("TL-0603", "Be'er Sheva", "Display 1", "C", "2026-01-01", "", 3.9, "LogiTemp LT-3"),
        ("TL-0701", "Netanya", "Dairy", "C", "2026-01-01", "", 3.6, "LogiTemp LT-2"),
        ("TL-0702", "Netanya", "Display 1", "C", "2026-01-01", "", 3.8, "LogiTemp LT-3"),
        ("TL-0801", "Petah Tikva", "Dairy", "C", "2026-01-01", "", 3.5, "LogiTemp LT-2"),
        ("TL-0802", "Petah Tikva", "Walk-in", "C", "2026-01-01", "", 3.3, "LogiTemp LT-2"),
        ("TL-0803", "Petah Tikva", "Cream cakes", "C", "2026-01-01", "", 3.9, "LogiTemp LT-2"),
        ("TL-0901", "Ashdod", "Dairy", "C", "2026-01-01", "", 3.6, "LogiTemp LT-2"),
        ("TL-0902", "Ashdod", "Walk-in", "C", "2026-01-01", "", 3.4, "LogiTemp LT-2"),
        ("TL-1001", "Herzliya", "Dairy", "C", "2026-01-01", "", 3.5, "LogiTemp LT-2"),
        ("TL-1002", "Herzliya", "Display 1", "C", "2026-01-01", "", 3.9, "LogiTemp LT-3"),
        ("TL-1101", "Beit Shemesh", "Dairy", "C", "2026-01-01", "", 3.6, "LogiTemp LT-2"),
        ("TL-1102", "Beit Shemesh", "Cream cakes", "C", "2026-01-01", "", 3.8, "LogiTemp LT-2"),
        ("TL-1201", "Kfar Saba", "Dairy", "C", "2026-01-01", "", 3.5, "LogiTemp LT-2"),
        ("TL-1202", "Kfar Saba", "Walk-in", "C", "2026-01-01", "", 3.3, "LogiTemp LT-2"),
        ("TL-1301", "Rehovot", "Dairy", "C", "2026-01-01", "", 3.6, "LogiTemp LT-2"),
        ("TL-1302", "Rehovot", "Display 1", "C", "2026-01-01", "", 3.8, "LogiTemp LT-3"),
    ]

    rotate_i = 0
    specs: dict[str, LoggerSpec] = {}
    for logger_id, branch, fridge, unit, a_from, a_to, baseline, model in rows:
        if logger_id in overrides:
            fmt = overrides[logger_id]
        else:
            fmt = ROTATING_FORMATS[rotate_i % len(ROTATING_FORMATS)]
            rotate_i += 1
        assignment = Assignment(logger_id, branch, fridge, unit, a_from, a_to, model)
        series_from = datetime(2026, 9, 17, 0, 0) if logger_id == "TL-0420" else None
        specs[logger_id] = LoggerSpec(
            logger_id=logger_id,
            format_key=fmt,
            assignments=[assignment],
            baseline_c=baseline,
            series_from=series_from,
        )

    # TL-0417 occupies the Tel Aviv walk-in until the end of 16 Sep, then
    # Display 2 from 17 Sep. One file covers the whole week.
    specs["TL-0417"] = LoggerSpec(
        logger_id="TL-0417",
        format_key=overrides["TL-0417"],
        assignments=[
            Assignment("TL-0417", "Tel Aviv", "Walk-in", "C", "2026-01-01", "2026-09-16", "LogiTemp LT-2"),
            Assignment("TL-0417", "Tel Aviv", "Display 2", "C", "2026-09-17", "", "LogiTemp LT-2"),
        ],
        baseline_c=3.8,
    )
    return list(specs.values())


# ---------------------------------------------------------------------------
# Series builders — start healthy, then plant scenario-specific traps.
# Values are stored in Celsius (float) or the string "ERR". Rounding to one
# decimal happens at generation time so files and the oracle agree.
# ---------------------------------------------------------------------------

Value = float | str  # float °C, or "ERR"


def base_healthy(spec: LoggerSpec) -> dict[datetime, Value]:
    rng = rng_for(spec.logger_id)
    start = spec.series_from or START
    end = spec.series_to or END
    # Display fridges sit a little warmer; walk-ins a little colder.
    lo, hi = 2.2, 4.6
    series: dict[datetime, Value] = {}
    for t in all_slots(start, end):
        series[t] = healthy_value(rng, t, spec.baseline_c, lo, hi)
    return series


def plant_jerusalem_dairy(series: dict[datetime, Value]) -> None:
    """TL-0512: sample-table pins, a duplicate at 06:15, and a 2h15m gap."""
    series[datetime(2026, 9, 14, 6, 0)] = 3.8
    series[datetime(2026, 9, 14, 6, 15)] = 3.9
    gap_start = datetime(2026, 9, 14, 6, 30)
    gap_end = datetime(2026, 9, 14, 8, 15)  # inclusive; next kept row is 08:30
    t = gap_start
    while t <= gap_end:
        series.pop(t, None)
        t += INTERVAL
    series[datetime(2026, 9, 14, 8, 30)] = 4.0


def plant_tel_aviv_0417(series: dict[datetime, Value]) -> None:
    """TL-0417: sample pins, door-opening spikes, slightly cooler Display 2 baseline after the move."""
    # Walk-in morning of the 14th — exact sample-table values.
    series[datetime(2026, 9, 14, 5, 45)] = 4.0
    series[datetime(2026, 9, 14, 6, 0)] = 4.1
    series[datetime(2026, 9, 14, 6, 15)] = 9.4  # isolated spike
    series[datetime(2026, 9, 14, 6, 30)] = 4.3

    # Further isolated door-opening spikes during the week.
    series[datetime(2026, 9, 15, 14, 30)] = 8.7
    series[datetime(2026, 9, 15, 14, 15)] = 4.1
    series[datetime(2026, 9, 15, 14, 45)] = 4.0
    series[datetime(2026, 9, 18, 9, 15)] = 8.2  # still Walk-in? No — 18th is Display 2
    series[datetime(2026, 9, 18, 9, 0)] = 3.8
    series[datetime(2026, 9, 18, 9, 30)] = 3.9
    series[datetime(2026, 9, 19, 16, 0)] = 7.9
    series[datetime(2026, 9, 19, 15, 45)] = 4.0
    series[datetime(2026, 9, 19, 16, 15)] = 3.8

    # From 17 Sep the logger is in Display 2 — slightly different baseline (~3.5–4.5).
    rng = rng_for("TL-0417-display2")
    t = datetime(2026, 9, 17, 0, 0)
    while t <= END:
        if t not in {
            datetime(2026, 9, 17, 6, 0),
            datetime(2026, 9, 18, 9, 0),
            datetime(2026, 9, 18, 9, 15),
            datetime(2026, 9, 18, 9, 30),
            datetime(2026, 9, 19, 15, 45),
            datetime(2026, 9, 19, 16, 0),
            datetime(2026, 9, 19, 16, 15),
        }:
            series[t] = healthy_value(rng, t, 3.9, 3.5, 4.5)
        t += INTERVAL
    series[datetime(2026, 9, 17, 6, 0)] = 3.7  # sample table


def plant_haifa_legacy(series: dict[datetime, Value]) -> None:
    """TL-0231: sample pins (as °C equivalents plus later F conversion) and a few ERRs."""
    # 38.3°F = 3.5°C, 39.0°F = 3.888...°C. Store the exact Fahrenheit-origin
    # Celsius so the written F values come out as 38.3 and 39.0.
    series[datetime(2026, 9, 14, 6, 0)] = f_to_c(38.3)
    series[datetime(2026, 9, 14, 6, 15)] = f_to_c(39.0)
    series[datetime(2026, 9, 14, 6, 30)] = "ERR"
    # A few more sensor errors scattered through the week.
    for err_at in (
        datetime(2026, 9, 15, 14, 30),
        datetime(2026, 9, 17, 3, 15),
        datetime(2026, 9, 19, 11, 0),
    ):
        series[err_at] = "ERR"


def plant_rishon_failure(series: dict[datetime, Value]) -> None:
    """TL-0388 Cream cakes: slow failure starting Monday morning (sample pins) then a plateau around 11°C."""
    # Subtle pre-failure drift still below 5°C.
    series[datetime(2026, 9, 14, 5, 0)] = 4.2
    series[datetime(2026, 9, 14, 5, 15)] = 4.3
    series[datetime(2026, 9, 14, 5, 30)] = 4.4
    series[datetime(2026, 9, 14, 5, 45)] = 4.5
    # Sample-table pins — excursion starts at 06:15.
    series[datetime(2026, 9, 14, 6, 0)] = 4.6
    series[datetime(2026, 9, 14, 6, 15)] = 5.4
    series[datetime(2026, 9, 14, 6, 30)] = 6.3
    series[datetime(2026, 9, 14, 6, 45)] = 7.1
    # Continue climbing toward kitchen ambient, then stay failed.
    ramp = {
        datetime(2026, 9, 14, 7, 0): 7.8,
        datetime(2026, 9, 14, 7, 15): 8.4,
        datetime(2026, 9, 14, 7, 30): 8.9,
        datetime(2026, 9, 14, 7, 45): 9.3,
        datetime(2026, 9, 14, 8, 0): 9.6,
        datetime(2026, 9, 14, 8, 15): 9.9,
        datetime(2026, 9, 14, 8, 30): 10.2,
        datetime(2026, 9, 14, 8, 45): 10.4,
        datetime(2026, 9, 14, 9, 0): 10.6,
        datetime(2026, 9, 14, 9, 15): 10.7,
        datetime(2026, 9, 14, 9, 30): 10.8,
        datetime(2026, 9, 14, 9, 45): 10.9,
        datetime(2026, 9, 14, 10, 0): 11.0,
    }
    series.update(ramp)
    rng = rng_for("TL-0388-failed")
    t = datetime(2026, 9, 14, 10, 15)
    while t <= END:
        series[t] = round(min(11.6, max(10.4, 11.0 + rng.gauss(0.0, 0.18))), 1)
        t += INTERVAL


def plant_beer_sheva_slow_death(series: dict[datetime, Value]) -> None:
    """TL-0601 Dairy: the 'Rishon dairy story' — a 2-day upward drift from 3.5°C to 9°C, then a plateau."""
    drift_start = datetime(2026, 9, 16, 0, 0)
    drift_end = datetime(2026, 9, 18, 0, 0)
    start_temp = 3.5
    end_temp = 9.0
    total = (drift_end - drift_start).total_seconds()
    rng = rng_for("TL-0601-drift")

    # Linear drift with no noise on the climb, so the crossing of 5.0°C is
    # clean (no isolated 5.1 followed by a 5.0). After the first reading
    # strictly above 5.0, every later value is clamped to stay there.
    t = drift_start
    crossed = False
    while t <= END:
        if t <= drift_end:
            frac = (t - drift_start).total_seconds() / total
            val = round(start_temp + (end_temp - start_temp) * frac, 1)
        else:
            val = round(min(9.4, max(8.7, 9.0 + rng.gauss(0.0, 0.12))), 1)
        if crossed:
            val = max(val, 5.1)
        if val > 5.0:
            crossed = True
        series[t] = val
        t += INTERVAL
    series[drift_start] = 3.5
    series[drift_end] = 9.0


def plant_ashdod_power_cut(series: dict[datetime, Value]) -> None:
    """TL-0901 Dairy: a 60-minute real excursion after a night-time power cut."""
    # Surrounding readings stay normal so this is a bounded event, not a drift.
    series[datetime(2026, 9, 16, 2, 45)] = 3.8
    series[datetime(2026, 9, 16, 3, 0)] = 5.3
    series[datetime(2026, 9, 16, 3, 15)] = 6.8
    series[datetime(2026, 9, 16, 3, 30)] = 7.4
    series[datetime(2026, 9, 16, 3, 45)] = 6.1
    series[datetime(2026, 9, 16, 4, 0)] = 5.2
    series[datetime(2026, 9, 16, 4, 15)] = 4.4


def plant_beit_shemesh_gap(series: dict[datetime, Value]) -> None:
    """TL-1101 Dairy: ~10-hour gap (battery died) from 18 Sep 22:15 through 19 Sep 07:45."""
    t = datetime(2026, 9, 18, 22, 15)
    end_gap = datetime(2026, 9, 19, 7, 45)
    while t <= end_gap:
        series.pop(t, None)
        t += INTERVAL


def plant_display1_spike(series: dict[datetime, Value]) -> None:
    """TL-0419 Tel Aviv Display 1: one isolated door-opening spike, to show they are not unique to TL-0417."""
    series[datetime(2026, 9, 16, 11, 0)] = 8.5
    series[datetime(2026, 9, 16, 10, 45)] = 3.9
    series[datetime(2026, 9, 16, 11, 15)] = 4.0


def build_series(spec: LoggerSpec) -> dict[datetime, Value]:
    series = base_healthy(spec)
    if spec.logger_id == "TL-0512":
        plant_jerusalem_dairy(series)
    elif spec.logger_id == "TL-0417":
        plant_tel_aviv_0417(series)
    elif spec.logger_id == "TL-0231":
        plant_haifa_legacy(series)
    elif spec.logger_id == "TL-0388":
        plant_rishon_failure(series)
    elif spec.logger_id == "TL-0601":
        plant_beer_sheva_slow_death(series)
    elif spec.logger_id == "TL-0901":
        plant_ashdod_power_cut(series)
    elif spec.logger_id == "TL-1101":
        plant_beit_shemesh_gap(series)
    elif spec.logger_id == "TL-0419":
        plant_display1_spike(series)
    return series


# ---------------------------------------------------------------------------
# Row ordering quirks applied at write time (not in the clean series).
# ---------------------------------------------------------------------------

def rows_for_write(spec: LoggerSpec, series: dict[datetime, Value]) -> list[tuple[datetime, Value]]:
    rows = sorted(series.items(), key=lambda kv: kv[0])
    if spec.logger_id == "TL-0512":
        # Duplicate the 06:15 row, immediately after the first copy.
        out: list[tuple[datetime, Value]] = []
        for t, v in rows:
            out.append((t, v))
            if t == datetime(2026, 9, 14, 6, 15):
                out.append((t, v))
        return out
    if spec.logger_id == "TL-0417":
        # Sample-table order: 05:45 is pasted after 06:30.
        displaced = datetime(2026, 9, 14, 5, 45)
        after = datetime(2026, 9, 14, 6, 30)
        moved = None
        out = []
        for t, v in rows:
            if t == displaced:
                moved = (t, v)
                continue
            out.append((t, v))
            if t == after and moved is not None:
                out.append(moved)
                moved = None
        if moved is not None:
            out.append(moved)
        return out
    return rows


def current_assignment(spec: LoggerSpec, t: datetime) -> Assignment:
    """Match a reading to the logger-to-fridge assignment in force at time t."""
    for a in spec.assignments:
        start = datetime.fromisoformat(a.assigned_from)
        end = (
            datetime.fromisoformat(a.assigned_to) + timedelta(days=1) - timedelta(seconds=1)
            if a.assigned_to
            else datetime.max
        )
        if start <= t <= end:
            return a
    return spec.assignments[-1]


# ---------------------------------------------------------------------------
# Excursion oracle. An excursion is two or more consecutive valid readings
# strictly above 5.0°C. A single isolated reading above 5°C is a spike.
# Duration is (last_reading - first_reading) in minutes.
# Temperatures used for the rule are Celsius, after converting Fahrenheit
# and dropping ERR / invalid values. Duplicate timestamps keep the first.
# ---------------------------------------------------------------------------

THRESHOLD_C = 5.0


def clean_celsius_series(spec: LoggerSpec, series: dict[datetime, Value]) -> list[tuple[datetime, float]]:
    unit = spec.assignments[0].unit
    cleaned: list[tuple[datetime, float]] = []
    for t in sorted(series):
        v = series[t]
        if v == "ERR":
            continue
        assert isinstance(v, float)
        c = v  # already stored in °C, even for the Haifa logger
        # For Haifa, the *written* value is Fahrenheit rounded to 1 decimal,
        # so re-derive Celsius from that written figure to match what a
        # parser would see after converting the file.
        if unit == "F":
            written_f = round(c_to_f(v), 1)
            c = f_to_c(written_f)
        else:
            c = round(v, 1)
        cleaned.append((t, c))
    return cleaned


@dataclass
class Event:
    logger_id: str
    branch: str
    fridge: str
    kind: str  # alert | spike-ignored | gap | sensor error | duplicate | out-of-order
    start: datetime
    end: datetime | None
    detail: str
    peak_c: float | None = None
    duration_minutes: int | None = None
    n_readings: int | None = None


def detect_runs(cleaned: list[tuple[datetime, float]]) -> list[tuple[datetime, datetime, float, int, bool]]:
    """Return runs of consecutive readings > 5.0°C.

    Each tuple is (start, end, peak_c, n_readings, is_spike).
    Consecutive means successive *present* readings, but a time gap of
    more than 15 minutes breaks a run (a missing period is not treated
    as "still above 5").
    """
    runs: list[tuple[datetime, datetime, float, int, bool]] = []
    run: list[tuple[datetime, float]] = []

    def close() -> None:
        if not run:
            return
        start, end = run[0][0], run[-1][0]
        peak = max(v for _, v in run)
        n = len(run)
        runs.append((start, end, peak, n, n == 1))
        run.clear()

    prev: datetime | None = None
    for t, c in cleaned:
        if prev is not None and (t - prev) > INTERVAL:
            close()
        if c > THRESHOLD_C:
            run.append((t, c))
        else:
            close()
        prev = t
    close()
    return runs


def find_gaps(slots_expected: list[datetime], present: set[datetime]) -> list[tuple[datetime, datetime, int]]:
    """Inclusive missing ranges, plus the number of missing slots."""
    gaps: list[tuple[datetime, datetime, int]] = []
    missing: list[datetime] = [t for t in slots_expected if t not in present]
    if not missing:
        return gaps
    start = prev = missing[0]
    count = 1
    for t in missing[1:]:
        if t == prev + INTERVAL:
            prev = t
            count += 1
        else:
            gaps.append((start, prev, count))
            start = prev = t
            count = 1
    gaps.append((start, prev, count))
    return gaps


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def preamble_lines(spec: LoggerSpec) -> list[str]:
    model = spec.assignments[0].model
    unit = spec.assignments[0].unit
    if spec.format_key == "haifa_legacy":
        return [
            f"Serial: {spec.logger_id}",
            f"Model: {model} (legacy)",
            f"Units: {unit}",
        ]
    if spec.format_key == "meta_iso_t":
        return [
            f"Serial: {spec.logger_id}",
            f"Model: {model}",
            f"Units: {unit}",
        ]
    if spec.format_key == "meta_semicolon":
        return [
            f"Device Serial: {spec.logger_id}",
            "Firmware: 2.1.4",
            f"Units: {unit}",
        ]
    return []


def format_value(spec: LoggerSpec, value: Value) -> str:
    if value == "ERR":
        return "ERR"
    assert isinstance(value, float)
    if spec.assignments[0].unit == "F":
        # Preserve exact tenths for the sample-table pins by converting
        # the stored (possibly unrounded) Celsius and rounding once.
        return fmt_temp(round(c_to_f(value), 1))
    return fmt_temp(value)


def write_logger_file(spec: LoggerSpec, series: dict[datetime, Value]) -> Path:
    fmt = FORMATS[spec.format_key]
    path = OUT / f"{spec.logger_id}_{WEEK_TAG}.csv"
    rows = rows_for_write(spec, series)
    lines: list[str] = []
    if fmt["preamble"]:
        lines.extend(preamble_lines(spec))
    lines.append(fmt["delimiter"].join(fmt["headers"]))
    for t, v in rows:
        time_s = t.strftime(fmt["time_fmt"])
        val_s = format_value(spec, v)
        if fmt["order"] == "temp_time":
            parts = [val_s, time_s]
        else:
            parts = [time_s, val_s]
        lines.append(fmt["delimiter"].join(parts))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_corrupt_file() -> Path:
    """Unhappy-path file: mixed garbage, blank lines, non-numeric temps.

    Not in the registry. The importer should reject it (or accept only the
    clearly valid rows) without crashing.
    """
    path = OUT / f"TL-9999_{WEEK_TAG}.csv"
    path.write_text(
        "\n".join(
            [
                "CoolTrace data export",
                "THIS FILE MAY BE INCOMPLETE",
                "",
                "Time,Temp",
                "2026-09-14 00:00,3.2",
                "",
                "not a valid line",
                "2026-09-14 00:15,abc",
                "2026-09-14 00:30,",
                "2026-09-14 00:45,4.1",
                ";;;;",
                "ERROR: buffer overflow at offset 0x1a3f",
                "2026-09-14 01:00",
                "NaN",
                "14/09/2026 01:15,3.9",
                "2026-09-14T01:30:00,??",
                "2026-09-14 01:45,null",
                "",
                "end of dump",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def write_registry(specs: list[LoggerSpec]) -> Path:
    path = OUT / "loggers.csv"
    lines = ["logger_id,branch,fridge,unit,assigned_from,assigned_to"]
    # Stable order: by first assigned_from, then logger id, then assigned_from.
    assignments: list[Assignment] = []
    for s in specs:
        assignments.extend(s.assignments)
    assignments.sort(key=lambda a: (a.logger_id, a.assigned_from))
    for a in assignments:
        lines.append(
            ",".join([a.logger_id, a.branch, a.fridge, a.unit, a.assigned_from, a.assigned_to])
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def ts(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M")


def write_excursions_json(excursions: list[Event]) -> Path:
    path = OUT / "expected_excursions.json"
    payload = {
        "threshold_c": THRESHOLD_C,
        "rule": (
            "An excursion is two or more consecutive valid readings strictly "
            "above 5.0°C. A single isolated reading above 5.0°C surrounded by "
            "normal (or missing-boundary) readings is a spike, not an alert. "
            "ERR and other invalid values are skipped and break a run. "
            "A gap longer than the 15-minute sampling interval also breaks a run. "
            "Duration is (end - start) in minutes, i.e. from the first to the "
            "last consecutive reading above the threshold, not until the first "
            "reading back at or below 5.0. Times are Asia/Jerusalem local, "
            "with no timezone offset. Fahrenheit loggers are converted to °C "
            "from the value as it appears in the file (one decimal place)."
        ),
        "excursions": [
            {
                "logger_id": e.logger_id,
                "branch": e.branch,
                "fridge": e.fridge,
                "start": ts(e.start),
                "end": ts(e.end) if e.end else None,
                "duration_minutes": e.duration_minutes,
                "peak_c": e.peak_c,
                "n_readings": e.n_readings,
            }
            for e in excursions
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def write_scenarios_md(
    specs: list[LoggerSpec],
    series_by_id: dict[str, dict[datetime, Value]],
    events: list[Event],
    excursions: list[Event],
    spikes: list[Event],
) -> Path:
    path = OUT / "SCENARIOS.md"
    specs_by_id = {s.logger_id: s for s in specs}

    def fmt_assign(s: LoggerSpec) -> str:
        bits = []
        for a in s.assignments:
            until = a.assigned_to if a.assigned_to else "present"
            bits.append(f"{a.branch} / {a.fridge} ({a.assigned_from} → {until}, unit {a.unit})")
        return "; ".join(bits)

    lines: list[str] = []
    a = lines.append
    a("# Squanchy Bakery — mock logger files, scenarios and test oracle")
    a("")
    a("Generated by `generate.py` (seed `20260914`). Re-run with `python generate.py`.")
    a("")
    a("## Conventions")
    a("")
    a("- **Week:** 2026-09-14 00:00 to 2026-09-20 23:45 inclusive, 15-minute interval (672 slots in a complete file).")
    a("- **Timezone:** Asia/Jerusalem local time (IDT, UTC+3 in September). Files contain no timezone offset.")
    a("- **ISO week:** 2026-W38, which starts on Monday 14 September 2026.")
    a("- **Threshold:** food-safety limit is 5.0°C. Healthy fridges hover around 2.0–4.6°C with a small daily cycle and noise.")
    a("- **Raw files** contain only time and temperature. Some also have two or three device header lines (`Serial`, `Model`, `Units`). Branch and fridge are **not** in the file; they come from `loggers.csv`.")
    a("- **Excursion rule** (see `expected_excursions.json` for the computed list): an *alert* is two or more consecutive valid readings strictly above 5.0°C. A single isolated reading above 5.0°C is a *spike-ignored*. `ERR` skips and breaks a run. A gap longer than 15 minutes also breaks a run. Duration is `(end − start)` in minutes (first to last reading of the run), not until the first recovery reading.")
    a("- **Logger moves:** a reading belongs to the fridge the logger was assigned to at that timestamp. TL-0417 is the worked example.")
    a("")
    a("## Choices worth knowing")
    a("")
    a("- After TL-0417 was moved out of the Tel Aviv walk-in at the end of 16 Sep, a replacement logger **TL-0420** was clipped into that walk-in from 2026-09-17 00:00. Its file starts on that date. Without this, the walk-in would have a week of history and then go dark — realistic, but unhelpful for an inspector asking about that fridge after the 16th.")
    a("- Haifa TL-0231 is marked `unit=F` in the registry rather than auto-detected from values over 30. The file header also says `Units: F`. The generator stores the series in °C and converts on write, so 38.3°F / 39.0°F come out exact.")
    a("- One unhappy-path file, `TL-9999_2026-W38.csv`, is deliberately not in the registry.")
    a("- Twelve branches, all real Israeli cities, 2–4 fridges each. No freezers.")
    a("")
    a("## Registry")
    a("")
    a("See `loggers.csv`. Columns: `logger_id,branch,fridge,unit,assigned_from,assigned_to`.")
    a("An empty `assigned_to` means the assignment is still current. TL-0417 has two rows:")
    a("")
    a("| logger_id | branch | fridge | unit | assigned_from | assigned_to |")
    a("|---|---|---|---|---|---|")
    a("| TL-0417 | Tel Aviv | Walk-in | C | 2026-01-01 | 2026-09-16 |")
    a("| TL-0417 | Tel Aviv | Display 2 | C | 2026-09-17 | *(open)* |")
    a("")
    a("TL-0231 is the only Fahrenheit logger (`unit=F`). TL-0420 is assigned to Tel Aviv / Walk-in from 2026-09-17.")
    a("")
    a("## File inventory")
    a("")
    a("| File | Logger | Assignment | Format quirks |")
    a("|---|---|---|---|")
    for s in sorted(specs, key=lambda x: x.logger_id):
        fmt = FORMATS[s.format_key]
        fname = f"{s.logger_id}_{WEEK_TAG}.csv"
        a(f"| `{fname}` | {s.logger_id} | {fmt_assign(s)} | {fmt['desc']} |")
    a(f"| `TL-9999_{WEEK_TAG}.csv` | TL-9999 *(not in registry)* | — | Intentionally broken export: preamble junk, blank lines, non-numeric temps (`abc`, `NaN`, `null`, `??`), a row with no temperature, mixed date formats, garbage text. Unhappy-path test. |")
    a("")
    a("## Planted anomalies (test oracle)")
    a("")
    a("Expected detection labels: `alert`, `spike-ignored`, `gap`, `sensor error`, `duplicate`, `out-of-order`.")
    a("")

    a("### 1. Jerusalem TL-0512 — Dairy")
    a("")
    a("Format: `timestamp,temp_c` / `YYYY-MM-DD HH:MM`.")
    a("")
    a("| Time (14 Sep) | Temp °C | Expected detection |")
    a("|---|---|---|")
    a("| 2026-09-14 06:00 | 3.8 | Fine (sample-table pin). |")
    a("| 2026-09-14 06:15 | 3.9 | Fine, but the row is written **twice** back-to-back. Detection: `duplicate`. |")
    a("| 2026-09-14 06:30 – 08:15 | *(no rows)* | `gap` of 2 h 15 min (8 missing slots). Do not interpolate a line across it. Next reading is 08:30. |")
    a("| 2026-09-14 08:30 | 4.0 | Fine (sample-table pin). |")
    a("")
    a("The duplicate is identical (same timestamp, same 3.9). The importer should keep one reading, not treat it as two samples.")
    a("")

    a("### 2. Tel Aviv TL-0417 — Walk-in, then Display 2")
    a("")
    a("Format: reversed columns `Temp,Time`. One file covers the whole week. The move is **not** in the file; it is a registry fact.")
    a("")
    a("| Time | Temp °C | Fridge at that time | Expected detection |")
    a("|---|---|---|---|")
    a("| 2026-09-14 05:45 | 4.0 | Walk-in | Fine, but the row is written **after** the 06:30 row (`out-of-order`). Importer must sort by time. |")
    a("| 2026-09-14 06:00 | 4.1 | Walk-in | Fine (sample-table pin). |")
    a("| 2026-09-14 06:15 | 9.4 | Walk-in | `spike-ignored` — single isolated door-opening, back to 4.3 at 06:30. |")
    a("| 2026-09-14 06:30 | 4.3 | Walk-in | Fine (sample-table pin). |")
    a("| 2026-09-15 14:30 | 8.7 | Walk-in | `spike-ignored` (surrounded by 4.1 / 4.0). |")
    a("| 2026-09-17 06:00 | 3.7 | **Display 2** | Fine (sample-table pin). From 2026-09-17 00:00 the baseline is a display-fridge range (~3.5–4.5°C). |")
    a("| 2026-09-18 09:15 | 8.2 | Display 2 | `spike-ignored` (surrounded by 3.8 / 3.9). |")
    a("| 2026-09-19 16:00 | 7.9 | Display 2 | `spike-ignored` (surrounded by 4.0 / 3.8). |")
    a("")
    a("Walk-in readings on this logger stop at 2026-09-16 23:45. From 2026-09-17 00:00 they belong to Display 2. The Tel Aviv walk-in is then covered by **TL-0420**.")
    a("")

    a("### 3. Haifa TL-0231 — Dairy (legacy, Fahrenheit)")
    a("")
    a("Format: metadata header + `Date,Temperature` + `DD/MM/YYYY HH:MM` + Fahrenheit + occasional `ERR`.")
    a("")
    a("| Time | Value in file | Equivalent °C | Expected detection |")
    a("|---|---|---|---|")
    a("| 14/09/2026 06:00 | 38.3 | 3.5 | Fine — **not** a disaster. Convert F→C. (Sample-table pin.) |")
    a("| 14/09/2026 06:15 | 39.0 | 3.89 | Fine. (Sample-table pin.) |")
    a("| 14/09/2026 06:30 | ERR | — | `sensor error`. Do not treat as 0, do not drop silently, do not convert. Breaks any excursion run. |")
    a("| 15/09/2026 14:30 | ERR | — | `sensor error`. |")
    a("| 17/09/2026 03:15 | ERR | — | `sensor error`. |")
    a("| 19/09/2026 11:00 | ERR | — | `sensor error`. |")
    a("")
    a("All other readings are in the roughly 37–40°F band (about 2.8–4.4°C) and should stay below the 5°C threshold once converted. There is **no** alert on this logger this week.")
    a("")

    a("### 4. Rishon LeZion TL-0388 — Cream cakes (slow failure, sample pins)")
    a("")
    a("Format: three metadata lines, then `datetime,temperature` with ISO 8601 `T` timestamps.")
    a("")
    a("| Time | Temp °C | Expected detection |")
    a("|---|---|---|---|")
    a("| 2026-09-14 05:00–05:45 | 4.2, 4.3, 4.4, 4.5 | Subtle pre-failure drift, still at or below 5.0 — no alert yet. |")
    a("| 2026-09-14 06:00 | 4.6 | Fine (sample-table pin), last reading at or below 5.0. |")
    a("| 2026-09-14 06:15 | 5.4 | Excursion starts (sample-table pin). |")
    a("| 2026-09-14 06:30 | 6.3 | Still climbing (sample-table pin). |")
    a("| 2026-09-14 06:45 | 7.1 | Still climbing (sample-table pin). |")
    a("| 2026-09-14 07:00 → 10:00 | 7.8 → 11.0 | Continues toward kitchen ambient. |")
    a("| 2026-09-14 10:15 → 2026-09-20 23:45 | ~10.4–11.6 | Failed plateau for the rest of the week. |")
    a("")
    a("Expected detection: one `alert` from **2026-09-14 06:15** through **2026-09-20 23:45**. Peak is the maximum of the plateau (~11.6°C). This is the inspector-report centrepiece for this week — a fridge that died on Monday morning and was never recovered.")
    a("")

    a("### 5. Be'er Sheva TL-0601 — Dairy (two-day slow death, 'Rishon dairy story')")
    a("")
    a("Format: semicolon-delimited `time;temperature`.")
    a("")
    a("Healthy around 3.5°C until 2026-09-16 00:00, then a linear drift to 9.0°C at 2026-09-18 00:00, then a plateau around 8.7–9.4°C for the rest of the week. The excursion starts at the first reading that rounds strictly above 5.0°C (see `expected_excursions.json` for the exact start, end, duration and peak — computed from the written values, not by hand).")
    a("")
    a("Expected detection: one `alert` covering the drift-and-plateau period. This is the slow failure Summer said nobody noticed last month; it is planted here on a different branch so the cream-cakes collapse and the two-day dairy drift can be tested independently.")
    a("")

    a("### 6. Ashdod TL-0901 — Dairy (short real excursion, power cut)")
    a("")
    a("Format: metadata lines, then semicolon-delimited `Time;Temp`.")
    a("")
    a("| Time | Temp °C | Expected detection |")
    a("|---|---|---|")
    a("| 2026-09-16 02:45 | 3.8 | Fine. |")
    a("| 2026-09-16 03:00 | 5.3 | Excursion starts. |")
    a("| 2026-09-16 03:15 | 6.8 |  |")
    a("| 2026-09-16 03:30 | 7.4 | Peak. |")
    a("| 2026-09-16 03:45 | 6.1 |  |")
    a("| 2026-09-16 04:00 | 5.2 | Last reading above 5.0. |")
    a("| 2026-09-16 04:15 | 4.4 | Recovered. |")
    a("")
    a("Expected detection: one `alert`, start **2026-09-16 03:00**, end **2026-09-16 04:00**, duration **60 minutes**, peak **7.4°C**, 5 readings. This is the fixture for a min-duration rule: it is long enough to be a real excursion, unlike a single door-opening spike.")
    a("")

    a("### 7. Beit Shemesh TL-1101 — Dairy (battery-died gap)")
    a("")
    a("Format: `Time Stamp,Temperature (C)` with ISO 8601 `T` timestamps.")
    a("")
    a("Last reading before the gap: **2026-09-18 22:00**. Next reading: **2026-09-19 08:00**. Missing slots: 2026-09-18 22:15 through 2026-09-19 07:45 inclusive (39 slots, 9 h 45 min of missing samples; 10 hours between the flanking readings).")
    a("")
    a("Expected detection: `gap`. Show it as missing data, do not connect the chart across it, do not invent temperatures. The flanking readings are healthy and there is no excursion.")
    a("")

    a("### 8. Tel Aviv TL-0419 — Display 1 (extra door-opening spike)")
    a("")
    a("Format: reversed columns `Temp,Time`.")
    a("")
    a("| Time | Temp °C | Expected detection |")
    a("|---|---|---|")
    a("| 2026-09-16 10:45 | 3.9 | Fine. |")
    a("| 2026-09-16 11:00 | 8.5 | `spike-ignored`. |")
    a("| 2026-09-16 11:15 | 4.0 | Fine. |")
    a("")

    a("### 9. Unhappy-path file — TL-9999")
    a("")
    a(f"`TL-9999_{WEEK_TAG}.csv` is not in `loggers.csv`. It contains junk preamble, blank lines, non-numeric temperatures, a timestamp with no value, mixed date formats and garbage text, mixed in with two or three rows that happen to look valid. Expected behaviour: the importer reports a parse error (or imports only valid rows and flags the rest) and the rest of the mailbox/dashboard is unaffected.")
    a("")

    a("## Expected excursions (computed)")
    a("")
    a("Full machine-readable oracle: `expected_excursions.json`. Summary:")
    a("")
    a("| Logger | Fridge | Start | End | Duration (min) | Peak °C | Readings |")
    a("|---|---|---|---|---|---|---|")
    for e in excursions:
        a(
            f"| {e.logger_id} | {e.branch} / {e.fridge} | {ts(e.start)} | {ts(e.end) if e.end else ''} | "
            f"{e.duration_minutes} | {e.peak_c:.1f} | {e.n_readings} |"
        )
    if not excursions:
        a("| *(none — generator bug)* | | | | | | |")
    a("")
    a("Spikes excluded from that list (expected `spike-ignored`):")
    a("")
    a("| Logger | Fridge | Time | Peak °C |")
    a("|---|---|---|---|")
    for e in spikes:
        a(f"| {e.logger_id} | {e.branch} / {e.fridge} | {ts(e.start)} | {e.peak_c:.1f} |")
    a("")
    a("## Healthy controls")
    a("")
    a("Every other logger is a quiet control: small daily cycle and Gaussian noise, clamped so that rounded values stay at or below 4.6°C. They should produce **no** alerts, spikes, gaps, duplicates or sensor errors. Use them as negatives in tests.")
    a("")
    a("## Sample-table cross-check")
    a("")
    a("These values must appear exactly (Haifa in Fahrenheit / `DD/MM/YYYY`, everyone else in °C):")
    a("")
    a("| Logger | Time | Value in file |")
    a("|---|---|---|")
    a("| TL-0512 | 2026-09-14 06:00 | 3.8 |")
    a("| TL-0417 | 2026-09-14 06:00 | 4.1 |")
    a("| TL-0231 | 14/09/2026 06:00 | 38.3 |")
    a("| TL-0512 | 2026-09-14 06:15 | 3.9 *(twice)* |")
    a("| TL-0417 | 2026-09-14 06:15 | 9.4 |")
    a("| TL-0388 | 2026-09-14 06:00 | 4.6 |")
    a("| TL-0417 | 2026-09-14 06:30 | 4.3 |")
    a("| TL-0231 | 14/09/2026 06:15 | 39.0 |")
    a("| TL-0388 | 2026-09-14 06:15 | 5.4 |")
    a("| TL-0417 | 2026-09-14 05:45 | 4.0 *(written after 06:30)* |")
    a("| TL-0388 | 2026-09-14 06:30 | 6.3 |")
    a("| TL-0231 | 14/09/2026 06:30 | ERR |")
    a("| TL-0388 | 2026-09-14 06:45 | 7.1 |")
    a("| TL-0512 | 2026-09-14 08:30 | 4.0 |")
    a("| TL-0417 | 2026-09-17 06:00 | 3.7 |")
    a("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Verification against the sample table and the planted traps
# ---------------------------------------------------------------------------

def read_text(logger_id: str) -> str:
    return (OUT / f"{logger_id}_{WEEK_TAG}.csv").read_text(encoding="utf-8")


def count_substr(hay: str, needle: str) -> int:
    return hay.count(needle)


def verify(specs: list[LoggerSpec], series_by_id: dict[str, dict[datetime, Value]], excursions: list[Event], spikes: list[Event]) -> None:
    # --- Sample-table exact strings in the written files --------------------
    j = read_text("TL-0512")
    assert "2026-09-14 06:00,3.8" in j
    assert count_substr(j, "2026-09-14 06:15,3.9") == 2, count_substr(j, "2026-09-14 06:15,3.9")
    assert "2026-09-14 08:30,4.0" in j
    assert "2026-09-14 06:30" not in j
    assert "2026-09-14 07:00" not in j
    assert "2026-09-14 08:15" not in j

    tlv = read_text("TL-0417")
    # Reversed columns: Temp,Time
    assert "4.1,2026-09-14 06:00" in tlv
    assert "9.4,2026-09-14 06:15" in tlv
    assert "4.3,2026-09-14 06:30" in tlv
    assert "4.0,2026-09-14 05:45" in tlv
    assert "3.7,2026-09-17 06:00" in tlv
    pos_0545 = tlv.index("4.0,2026-09-14 05:45")
    pos_0615 = tlv.index("9.4,2026-09-14 06:15")
    pos_0630 = tlv.index("4.3,2026-09-14 06:30")
    assert pos_0615 < pos_0630 < pos_0545, "05:45 must be written after 06:30"

    haifa = read_text("TL-0231")
    assert "14/09/2026 06:00,38.3" in haifa
    assert "14/09/2026 06:15,39.0" in haifa
    assert "14/09/2026 06:30,ERR" in haifa
    assert "Units: F" in haifa
    # Must not have the Celsius lookalikes at those pins
    assert "14/09/2026 06:00,3.8" not in haifa

    rishon = read_text("TL-0388")
    assert "2026-09-14T06:00:00,4.6" in rishon
    assert "2026-09-14T06:15:00,5.4" in rishon
    assert "2026-09-14T06:30:00,6.3" in rishon
    assert "2026-09-14T06:45:00,7.1" in rishon

    ashdod = read_text("TL-0901")
    assert "2026-09-16 03:00;5.3" in ashdod
    assert "2026-09-16 03:30;7.4" in ashdod
    assert "2026-09-16 04:00;5.2" in ashdod

    # --- Gaps present in the series ----------------------------------------
    s512 = series_by_id["TL-0512"]
    assert datetime(2026, 9, 14, 6, 15) in s512
    assert datetime(2026, 9, 14, 6, 30) not in s512
    assert datetime(2026, 9, 14, 8, 15) not in s512
    assert datetime(2026, 9, 14, 8, 30) in s512

    s1101 = series_by_id["TL-1101"]
    assert datetime(2026, 9, 18, 22, 0) in s1101
    assert datetime(2026, 9, 18, 22, 15) not in s1101
    assert datetime(2026, 9, 19, 7, 45) not in s1101
    assert datetime(2026, 9, 19, 8, 0) in s1101

    # --- Registry ----------------------------------------------------------
    reg = (OUT / "loggers.csv").read_text(encoding="utf-8")
    assert "TL-0417,Tel Aviv,Walk-in,C,2026-01-01,2026-09-16" in reg
    assert "TL-0417,Tel Aviv,Display 2,C,2026-09-17," in reg
    assert "TL-0231,Haifa,Dairy,F,2026-01-01," in reg
    assert "TL-0420,Tel Aviv,Walk-in,C,2026-09-17," in reg
    assert "TL-9999" not in reg

    # --- Oracle: expected spikes and alerts --------------------------------
    spike_keys = {(e.logger_id, ts(e.start)) for e in spikes}
    expected_spikes = {
        ("TL-0417", "2026-09-14 06:15"),
        ("TL-0417", "2026-09-15 14:30"),
        ("TL-0417", "2026-09-18 09:15"),
        ("TL-0417", "2026-09-19 16:00"),
        ("TL-0419", "2026-09-16 11:00"),
    }
    assert spike_keys == expected_spikes, f"spikes mismatch:\n got {sorted(spike_keys)}\n want {sorted(expected_spikes)}"

    alerts_by_logger = {e.logger_id: e for e in excursions}
    assert set(alerts_by_logger) >= {"TL-0388", "TL-0601", "TL-0901"}
    e388 = alerts_by_logger["TL-0388"]
    assert ts(e388.start) == "2026-09-14 06:15", ts(e388.start)
    assert ts(e388.end) == "2026-09-20 23:45", ts(e388.end)
    e901 = alerts_by_logger["TL-0901"]
    assert ts(e901.start) == "2026-09-16 03:00"
    assert ts(e901.end) == "2026-09-16 04:00"
    assert e901.duration_minutes == 60
    assert e901.peak_c == 7.4
    e601 = alerts_by_logger["TL-0601"]
    assert e601.start >= datetime(2026, 9, 16, 0, 0)
    assert e601.start <= datetime(2026, 9, 16, 16, 0)
    assert ts(e601.end) >= "2026-09-20 23:45" or e601.end == datetime(2026, 9, 20, 23, 45)
    assert e601.peak_c is not None and e601.peak_c >= 9.0

    # No alert on Haifa (Fahrenheit must have been converted).
    assert "TL-0231" not in alerts_by_logger
    assert "TL-0512" not in alerts_by_logger

    # File counts: 31 real loggers + 1 corrupt.
    logger_files = list(OUT.glob("TL-*_2026-W38.csv"))
    assert len(logger_files) == 32, len(logger_files)

    # TL-0420 starts on the 17th.
    t420 = read_text("TL-0420")
    assert "2026-09-16" not in t420
    assert "2026-09-17 00:00" in t420

    print("Verification passed.")


def collect_events(
    specs: list[LoggerSpec],
    series_by_id: dict[str, dict[datetime, Value]],
) -> tuple[list[Event], list[Event], list[Event]]:
    events: list[Event] = []
    excursions: list[Event] = []
    spikes: list[Event] = []
    for spec in specs:
        series = series_by_id[spec.logger_id]
        cleaned = clean_celsius_series(spec, series)
        start = spec.series_from or START
        end = spec.series_to or END
        gaps = find_gaps(all_slots(start, end), set(series))
        for g_start, g_end, n in gaps:
            a0 = current_assignment(spec, g_start - INTERVAL if g_start > start else g_start)
            hours = n * 15 / 60.0
            events.append(
                Event(
                    spec.logger_id,
                    a0.branch,
                    a0.fridge,
                    "gap",
                    g_start,
                    g_end,
                    f"{n} missing slots ({hours:g} h of samples); flanking interval "
                    f"{ts(g_start - INTERVAL) if g_start > start else 'start'} → "
                    f"{ts(g_end + INTERVAL) if g_end < end else 'end'}.",
                    n_readings=n,
                    duration_minutes=int((g_end - g_start).total_seconds() / 60) + 15,
                )
            )
        for t, v in series.items():
            if v == "ERR":
                a0 = current_assignment(spec, t)
                events.append(
                    Event(spec.logger_id, a0.branch, a0.fridge, "sensor error", t, t, "ERR in temperature column.")
                )
        for start_t, end_t, peak, n, is_spike in detect_runs(cleaned):
            a0 = current_assignment(spec, start_t)
            duration = int((end_t - start_t).total_seconds() / 60)
            ev = Event(
                spec.logger_id,
                a0.branch,
                a0.fridge,
                "spike-ignored" if is_spike else "alert",
                start_t,
                end_t,
                "isolated reading above 5.0°C" if is_spike else "consecutive readings above 5.0°C",
                peak_c=round(peak, 1),
                duration_minutes=duration,
                n_readings=n,
            )
            events.append(ev)
            if is_spike:
                spikes.append(ev)
            else:
                excursions.append(ev)

    excursions.sort(key=lambda e: (e.start, e.logger_id))
    spikes.sort(key=lambda e: (e.start, e.logger_id))
    return events, excursions, spikes


def clean_previous_outputs() -> None:
    for p in OUT.glob("TL-*_2026-W38.csv"):
        p.unlink()
    for name in ("loggers.csv", "SCENARIOS.md", "expected_excursions.json"):
        q = OUT / name
        if q.exists() and q.name != "generate.py":
            q.unlink()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    clean_previous_outputs()
    specs = build_fleet()
    # Include TL-0417 which was inserted into the dict-based builder.
    assert any(s.logger_id == "TL-0417" for s in specs)
    series_by_id: dict[str, dict[datetime, Value]] = {}
    for spec in specs:
        series_by_id[spec.logger_id] = build_series(spec)
        write_logger_file(spec, series_by_id[spec.logger_id])
    write_corrupt_file()
    write_registry(specs)
    events, excursions, spikes = collect_events(specs, series_by_id)
    write_excursions_json(excursions)
    write_scenarios_md(specs, series_by_id, events, excursions, spikes)
    verify(specs, series_by_id, excursions, spikes)
    n_real = len(specs)
    n_files = len(list(OUT.glob("TL-*_2026-W38.csv")))
    print(f"Wrote {n_real} logger series + 1 corrupt file ({n_files} CSV exports).")
    print(f"Excursions: {len(excursions)}; spikes: {len(spikes)}.")
    for e in excursions:
        print(f"  ALERT {e.logger_id} {e.branch}/{e.fridge} {ts(e.start)} → {ts(e.end)} "
              f"({e.duration_minutes} min, peak {e.peak_c}°C, n={e.n_readings})")
    for e in spikes:
        print(f"  SPIKE {e.logger_id} {e.branch}/{e.fridge} {ts(e.start)} {e.peak_c}°C")


if __name__ == "__main__":
    main()
