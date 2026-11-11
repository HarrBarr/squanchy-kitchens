"""Parser: one test per format family, plus the sample-table pins from SCENARIOS.md."""

from datetime import datetime
from decimal import Decimal

import pytest

from app.parsing import ParseError, parse_bytes
from tests.conftest import MOCK


def parse_mock(name: str):
    return parse_bytes((MOCK / name).read_bytes())


def row_at(result, ts: str):
    want = datetime.fromisoformat(ts)
    rows = [r for r in result.rows if r.ts_local == want]
    assert rows, f"no row at {ts}"
    return rows


def test_comma_timestamp_temp_c():
    r = parse_mock("TL-0512_2026-W38.csv")
    assert r.delimiter == ","
    assert r.has_header and (r.time_col, r.temp_col) == (0, 1)
    assert r.preamble == []
    assert row_at(r, "2026-09-14 06:00")[0].value == Decimal("3.8")
    # Written twice in the file; the parser keeps both, ingest collapses them.
    assert [x.value for x in row_at(r, "2026-09-14 06:15")] == [Decimal("3.9"), Decimal("3.9")]
    assert row_at(r, "2026-09-14 08:30")[0].value == Decimal("4.0")


def test_reversed_temp_time_columns():
    r = parse_mock("TL-0417_2026-W38.csv")
    assert r.delimiter == ","
    assert (r.time_col, r.temp_col) == (1, 0)
    assert row_at(r, "2026-09-14 06:00")[0].value == Decimal("4.1")
    assert row_at(r, "2026-09-14 06:15")[0].value == Decimal("9.4")
    assert row_at(r, "2026-09-14 06:30")[0].value == Decimal("4.3")
    assert row_at(r, "2026-09-17 06:00")[0].value == Decimal("3.7")
    # 05:45 is written after 06:30: the parser preserves file order, ingest sorts.
    idx = {r_.ts_local: i for i, r_ in enumerate(r.rows)}
    assert idx[datetime(2026, 9, 14, 5, 45)] > idx[datetime(2026, 9, 14, 6, 30)]
    assert row_at(r, "2026-09-14 05:45")[0].value == Decimal("4.0")


def test_semicolon_with_metadata():
    r = parse_mock("TL-0901_2026-W38.csv")
    assert r.delimiter == ";"
    assert r.preamble[:2] == ["Device Serial: TL-0901", "Firmware: 2.1.4"]
    assert r.metadata["device serial"] == "TL-0901"
    assert row_at(r, "2026-09-16 03:30")[0].value == Decimal("7.4")


def test_semicolon_without_metadata():
    r = parse_mock("TL-0601_2026-W38.csv")
    assert r.delimiter == ";" and r.preamble == []
    assert len(r.rows) == 672


def test_tab_separated():
    r = parse_mock("TL-0513_2026-W38.csv")
    assert r.delimiter == "\t"
    assert len(r.rows) == 672


def test_iso_t_timestamps_with_metadata():
    r = parse_mock("TL-0388_2026-W38.csv")
    assert r.delimiter == ","
    assert r.preamble == ["Serial: TL-0388", "Model: LogiTemp LT-2", "Units: C"]
    assert r.declared_unit == "C"
    pins = {"06:00": "4.6", "06:15": "5.4", "06:30": "6.3", "06:45": "7.1"}
    for hhmm, v in pins.items():
        assert row_at(r, f"2026-09-14 {hhmm}")[0].value == Decimal(v)


def test_haifa_legacy_fahrenheit_day_first_and_err():
    r = parse_mock("TL-0231_2026-W38.csv")
    assert r.preamble == ["Serial: TL-0231", "Model: LogiTemp LT-1 (legacy)", "Units: F"]
    assert r.declared_unit == "F"
    assert (r.time_col, r.temp_col) == (0, 1)
    # 14/09/2026 is 14 September (day first), never 9 February-ish nonsense.
    assert row_at(r, "2026-09-14 06:00")[0].raw_value == "38.3"
    assert row_at(r, "2026-09-14 06:00")[0].value == Decimal("38.3")  # still Fahrenheit here
    assert row_at(r, "2026-09-14 06:15")[0].value == Decimal("39.0")
    err = row_at(r, "2026-09-14 06:30")[0]
    assert err.raw_value == "ERR" and err.value is None and err.is_error
    assert sum(1 for x in r.rows if x.is_error) == 4


@pytest.mark.parametrize(
    "header",
    ["Time Stamp,Temperature (C)", "Logged At,Temperature C", "datetime,temperature"],
)
def test_header_variants(header):
    r = parse_bytes(f"{header}\n2026-09-14 00:00,3.1\n".encode())
    assert (r.time_col, r.temp_col) == (0, 1)
    assert r.rows[0].value == Decimal("3.1")


def test_headerless_file_guessed_from_values():
    r = parse_bytes(b"3.2;2026-09-14 00:00\n3.3;2026-09-14 00:15\n")
    assert not r.has_header and r.delimiter == ";"
    assert (r.time_col, r.temp_col) == (1, 0)
    assert len(r.rows) == 2


def test_blank_lines_and_crlf_are_ignored():
    r = parse_bytes(b"timestamp,temp_c\r\n\r\n2026-09-14 00:00,3.1\r\n\r\n2026-09-14 00:15,3.2\r\n")
    assert len(r.rows) == 2 and not r.rejected


def test_decimal_comma_in_semicolon_file():
    r = parse_bytes(b"Time;Temp\n2026-09-14 00:00;3,5\n")
    assert r.rows[0].value == Decimal("3.5")


def test_unhappy_path_file_keeps_valid_timestamps_and_rejects_junk():
    r = parse_mock("TL-9999_2026-W38.csv")
    assert r.delimiter == ","
    by_ts = {x.ts_local.strftime("%H:%M"): x for x in r.rows}
    assert by_ts["00:00"].value == Decimal("3.2")
    assert by_ts["00:45"].value == Decimal("4.1")
    assert by_ts["01:15"].value == Decimal("3.9")  # DD/MM/YYYY mixed in
    for hhmm in ("00:15", "00:30", "01:00", "01:30", "01:45"):  # abc, '', missing, ??, null
        assert by_ts[hhmm].is_error
    assert len(r.rejected) >= 4  # "not a valid line", ";;;;", "ERROR: ...", "NaN", "end of dump"


def test_nan_is_not_a_temperature():
    r = parse_bytes(b"timestamp,temp_c\n2026-09-14 00:00,NaN\n2026-09-14 00:15,inf\n")
    assert all(x.is_error for x in r.rows)


def test_garbage_raises_parse_error():
    with pytest.raises(ParseError):
        parse_bytes(b"hello\nthis is not a logger file\n")
