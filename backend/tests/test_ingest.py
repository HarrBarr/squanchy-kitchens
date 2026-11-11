from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.ingest import ImportRejected, import_file
from app.storage.models import Fridge, Logger, Reading, Upload
from tests.conftest import MOCK, import_mock


def readings(db, code):
    lg = db.scalar(select(Logger).where(Logger.logger_code == code))
    return list(
        db.scalars(select(Reading).where(Reading.logger_id == lg.id).order_by(Reading.ts_utc))
    )


def test_unknown_logger_is_rejected_and_writes_nothing(db, settings):
    with pytest.raises(ImportRejected, match="TL-9999 is not in the registry"):
        import_mock(db, settings, "TL-9999_2026-W38.csv")
    db.rollback()
    assert db.scalar(select(func.count(Reading.id))) == 0
    assert db.scalar(select(func.count(Upload.id))) == 0


def test_identical_reupload_is_a_noop(db, settings):
    first = import_mock(db, settings, "TL-0512_2026-W38.csv")
    n = db.scalar(select(func.count(Reading.id)))
    second = import_mock(db, settings, "TL-0512_2026-W38.csv")
    assert not first.already_imported and second.already_imported
    assert second.upload_id == first.upload_id
    assert db.scalar(select(func.count(Reading.id))) == n
    assert db.scalar(select(func.count(Upload.id))) == 1


def test_exact_duplicate_collapses_and_gap_is_found(db, settings):
    s = import_mock(db, settings, "TL-0512_2026-W38.csv")
    assert s.duplicates == 1
    assert s.gaps == 1 and s.excursions == 0
    rows = readings(db, "TL-0512")
    at = [r for r in rows if r.ts_local == datetime(2026, 9, 14, 6, 15)]
    assert len(at) == 1 and at[0].temp_c == Decimal("3.9")


def test_out_of_order_rows_are_sorted(db, settings):
    import_mock(db, settings, "TL-0417_2026-W38.csv")
    ts = [r.ts_utc for r in readings(db, "TL-0417")]
    assert ts == sorted(ts)
    assert datetime(2026, 9, 14, 2, 45) in ts  # 05:45 local, written after 06:30


def test_fahrenheit_converted_from_registry_and_err_kept(db, settings):
    s = import_mock(db, settings, "TL-0231_2026-W38.csv")
    assert s.sensor_errors == 4 and s.excursions == 0
    rows = {r.ts_local: r for r in readings(db, "TL-0231")}
    six = rows[datetime(2026, 9, 14, 6, 0)]
    assert (six.raw_value, six.temp_c, six.status) == ("38.3", Decimal("3.50"), "ok")
    err = rows[datetime(2026, 9, 14, 6, 30)]
    assert (err.raw_value, err.temp_c, err.status) == ("ERR", None, "err")
    assert six.ts_utc == datetime(2026, 9, 14, 3, 0)


def test_header_unit_disagreeing_with_registry_warns_but_trusts_registry(db, settings):
    data = b"Units: C\nDate,Temperature\n14/09/2026 06:00,38.3\n"
    s = import_file(db, settings, "TL-0231_fixed.csv", data, "TL-0231")
    assert any("using the registry" in w for w in s.warnings)
    (r,) = readings(db, "TL-0231")
    assert r.temp_c == Decimal("3.50")


def test_logger_move_splits_one_file_across_two_fridges(db, settings):
    import_mock(db, settings, "TL-0417_2026-W38.csv")
    names = {f.id: f.name for f in db.scalars(select(Fridge))}
    rows = readings(db, "TL-0417")
    assert {names[r.fridge_id] for r in rows if r.ts_local < datetime(2026, 9, 17)} == {"Walk-in"}
    assert {names[r.fridge_id] for r in rows if r.ts_local >= datetime(2026, 9, 17)} == {
        "Display 2"
    }


def test_corrected_file_overwrites_and_recomputes(db, settings):
    import_mock(db, settings, "TL-0901_2026-W38.csv")
    text = (MOCK / "TL-0901_2026-W38.csv").read_text()
    fixed = text.replace("2026-09-16 03:15;6.8", "2026-09-16 03:15;4.0")
    assert fixed != text
    s = import_file(db, settings, "TL-0901_fixed.csv", fixed.encode(), "TL-0901")
    assert s.updated == 1 and s.inserted == 0
    assert any("different value" in w for w in s.warnings)
    assert db.scalar(select(func.count(Upload.id))) == 2
    # 03:00 alone is now a spike; 03:30..04:00 is a 3-reading excursion.
    assert s.excursions == 1 and s.spikes == 1


def test_original_file_is_stored(db, settings):
    s = import_mock(db, settings, "TL-0232_2026-W38.csv")
    up = db.get(Upload, s.upload_id)
    with open(up.stored_path, "rb") as fh:
        assert fh.read() == (MOCK / "TL-0232_2026-W38.csv").read_bytes()


def test_rows_outside_every_assignment_are_rejected(db, settings):
    data = b"timestamp,temp_c\n2026-09-16 00:00,3.1\n"
    with pytest.raises(ImportRejected, match="inside an assignment"):
        import_file(db, settings, "TL-0420.csv", data, "TL-0420")  # assigned from 17 Sep
