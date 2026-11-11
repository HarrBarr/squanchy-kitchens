"""Golden test: import the whole mock week, compare to data/expected_excursions.json."""

import json
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select

from app.config import Settings
from app.ingest import logger_points
from app.rules import analyze
from app.storage.models import Excursion, Fridge, Gap, Logger, Reading
from tests.conftest import DATA


def _fmt(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M")


def test_every_mock_file_imports_except_the_unknown_logger(week_db):
    res = week_db.week_results
    assert len(res) == 32
    assert res["TL-9999_2026-W38.csv"].startswith("rejected: Logger TL-9999")
    assert all(not v.startswith("rejected") for k, v in res.items() if "9999" not in k)


def test_excursions_match_the_oracle(week_db):
    expected = json.loads((DATA / "expected_excursions.json").read_text())["excursions"]
    got = []
    for e in week_db.scalars(select(Excursion)):
        f = week_db.get(Fridge, e.fridge_id)
        got.append(
            {
                "logger_id": week_db.get(Logger, e.logger_id).logger_code,
                "branch": f.branch.name,
                "fridge": f.name,
                "start": _fmt(e.start_local),
                "end": _fmt(e.end_local),
                "duration_minutes": e.duration_minutes,
                "peak_c": float(e.peak_c.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
                "n_readings": e.n_readings,
            }
        )
    key = lambda x: x["logger_id"]  # noqa: E731
    assert sorted(got, key=key) == sorted(expected, key=key)


def test_open_flags(week_db):
    open_by_logger = {
        week_db.get(Logger, e.logger_id).logger_code: e.is_open
        for e in week_db.scalars(select(Excursion))
    }
    assert open_by_logger == {"TL-0388": True, "TL-0601": True, "TL-0901": False}


def test_known_spikes_are_not_excursions(week_db):
    settings = Settings(database_url="unused")
    spikes = []
    for code in ("TL-0417", "TL-0419"):
        lg = week_db.scalar(select(Logger).where(Logger.logger_code == code))
        a = analyze(logger_points(week_db, lg.id), settings.alert_threshold_c)
        assert a.excursions == []
        spikes += [(code, _fmt(s.ts_local), float(s.temp_c)) for s in a.spikes]
    assert sorted(spikes) == sorted(
        [
            ("TL-0417", "2026-09-14 06:15", 9.4),
            ("TL-0417", "2026-09-15 14:30", 8.7),
            ("TL-0417", "2026-09-18 09:15", 8.2),
            ("TL-0417", "2026-09-19 16:00", 7.9),
            ("TL-0419", "2026-09-16 11:00", 8.5),
        ]
    )


def test_haifa_has_four_errors_and_no_excursion(week_db):
    lg = week_db.scalar(select(Logger).where(Logger.logger_code == "TL-0231"))
    rows = list(week_db.scalars(select(Reading).where(Reading.logger_id == lg.id)))
    assert sum(r.status == "err" for r in rows) == 4
    assert max(r.temp_c for r in rows if r.temp_c is not None) <= Decimal("5.0")
    assert not week_db.scalars(select(Excursion).where(Excursion.logger_id == lg.id)).all()


def test_gaps_are_exactly_jerusalem_and_beit_shemesh(week_db):
    gaps = sorted(
        (
            week_db.get(Logger, g.logger_id).logger_code,
            _fmt(g.start_local),
            _fmt(g.end_local),
            g.duration_minutes,
        )
        for g in week_db.scalars(select(Gap))
    )
    assert gaps == [
        ("TL-0512", "2026-09-14 06:15", "2026-09-14 08:30", 135),
        ("TL-1101", "2026-09-18 22:00", "2026-09-19 08:00", 600),
    ]


def test_tl0512_duplicate_collapsed(week_db):
    lg = week_db.scalar(select(Logger).where(Logger.logger_code == "TL-0512"))
    at = week_db.scalars(
        select(Reading).where(
            Reading.logger_id == lg.id, Reading.ts_local == datetime(2026, 9, 14, 6, 15)
        )
    ).all()
    assert len(at) == 1


def test_tl0417_readings_on_17_sep_sit_on_display_2(week_db):
    lg = week_db.scalar(select(Logger).where(Logger.logger_code == "TL-0417"))
    r = week_db.scalar(
        select(Reading).where(
            Reading.logger_id == lg.id, Reading.ts_local == datetime(2026, 9, 17, 6, 0)
        )
    )
    f = week_db.get(Fridge, r.fridge_id)
    assert (f.branch.name, f.name, r.temp_c) == ("Tel Aviv", "Display 2", Decimal("3.70"))
