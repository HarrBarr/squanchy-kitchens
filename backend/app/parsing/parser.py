from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

# Tried in this order: a line with tabs or semicolons is never comma-first, and a
# semicolon file may use a decimal comma ("3,5").
DELIMITERS = ("\t", ";", ",")

DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    # Day-first, as on the Haifa legacy logger: 14/09/2026 is 14 September, never M/D.
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
)

_TEMP_WORDS = ("temp",)
_TIME_WORDS = ("time", "date", "logged", "stamp")
_METADATA_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _\-]{0,40}):\s*(.*?)\s*$")


class ParseError(ValueError):
    """The file has no recognisable header or data rows."""


@dataclass(frozen=True)
class ParsedRow:
    line_no: int
    ts_local: datetime  # naive wall-clock time as written in the file
    raw_value: str  # exactly what was in the temperature cell ("38.3", "ERR", "")
    value: Decimal | None  # None means a sensor error / unreadable cell

    @property
    def is_error(self) -> bool:
        return self.value is None


@dataclass(frozen=True)
class RejectedLine:
    line_no: int
    text: str
    reason: str


@dataclass
class ParseResult:
    delimiter: str
    has_header: bool
    time_col: int
    temp_col: int
    header_line_no: int | None
    preamble: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    rows: list[ParsedRow] = field(default_factory=list)
    rejected: list[RejectedLine] = field(default_factory=list)

    @property
    def declared_unit(self) -> str | None:
        """`Units: F` from a device preamble, if present. Only used as a cross-check."""
        unit = self.metadata.get("units")
        if not unit:
            return None
        unit = unit.strip().upper().lstrip("°")
        return unit[:1] if unit[:1] in ("C", "F") else None


def parse_datetime(text: str) -> datetime | None:
    s = text.strip()
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_value(text: str, delimiter: str) -> Decimal | None:
    """Return a finite Decimal, or None for ERR / empty / anything non-numeric."""
    s = text.strip()
    if not s or s.upper() == "ERR":
        return None
    if delimiter != ",":
        s = s.replace(",", ".")
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _looks_numeric_or_err(text: str, delimiter: str) -> bool:
    return text.strip().upper() == "ERR" or parse_value(text, delimiter) is not None


def _classify_header(fields: list[str]) -> tuple[int, int] | None:
    """Return (time_col, temp_col) if these fields are a header row."""
    time_idx: list[int] = []
    temp_idx: list[int] = []
    for i, f in enumerate(fields):
        name = f.strip().lower()
        if not name:
            continue
        if any(w in name for w in _TEMP_WORDS):
            temp_idx.append(i)
        elif any(w in name for w in _TIME_WORDS):
            time_idx.append(i)
    if len(time_idx) == 1 and len(temp_idx) == 1:
        return time_idx[0], temp_idx[0]
    return None


def _classify_data(fields: list[str], delimiter: str) -> tuple[int, int] | None:
    """Return (time_col, temp_col) if these fields look like a data row (no header case)."""
    time_cols = [i for i, f in enumerate(fields) if parse_datetime(f)]
    if len(time_cols) != 1:
        return None
    t = time_cols[0]
    temp_cols = [i for i, f in enumerate(fields) if i != t and _looks_numeric_or_err(f, delimiter)]
    if len(temp_cols) != 1:
        return None
    return t, temp_cols[0]


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1255", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")  # pragma: no cover - latin-1 never fails


def parse_bytes(data: bytes) -> ParseResult:
    lines = _decode(data).splitlines()

    # 1. Skip the preamble until a header or the first data row appears; sniff the delimiter.
    start: tuple[int, str, bool, tuple[int, int]] | None = None
    preamble: list[str] = []
    metadata: dict[str, str] = {}
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        for delim in DELIMITERS:
            if delim not in line:
                continue
            fields = [f.strip() for f in line.split(delim)]
            if len(fields) < 2:
                continue
            header = _classify_header(fields)
            if header:
                start = (idx, delim, True, header)
                break
            data_cols = _classify_data(fields, delim)
            if data_cols:
                start = (idx, delim, False, data_cols)
                break
        if start:
            break
        preamble.append(line.strip())
        m = _METADATA_RE.match(line)
        if m:
            metadata[m.group(1).strip().lower()] = m.group(2)

    if start is None:
        raise ParseError(
            "Could not find a header (e.g. 'timestamp,temp_c') or any time/temperature rows."
        )

    header_idx, delim, has_header, (time_col, temp_col) = start
    result = ParseResult(
        delimiter=delim,
        has_header=has_header,
        time_col=time_col,
        temp_col=temp_col,
        header_line_no=header_idx + 1 if has_header else None,
        preamble=preamble,
        metadata=metadata,
    )

    # 2. Body. Blank lines are ignored; a row with a valid timestamp is kept even when the
    #    temperature is missing or garbage (it becomes a sensor error, so the chart shows a
    #    break instead of a silent hole). Rows without a valid timestamp are rejected.
    body_start = header_idx + 1 if has_header else header_idx
    for idx in range(body_start, len(lines)):
        line = lines[idx]
        if not line.strip():
            continue
        line_no = idx + 1
        fields = [f.strip() for f in line.split(delim)]
        if time_col >= len(fields):
            result.rejected.append(RejectedLine(line_no, line, "no timestamp column"))
            continue
        ts = parse_datetime(fields[time_col])
        if ts is None:
            result.rejected.append(RejectedLine(line_no, line, "unparseable timestamp"))
            continue
        raw = fields[temp_col] if temp_col < len(fields) else ""
        value = parse_value(raw, delim)
        raw_value = "ERR" if raw.upper() == "ERR" else raw
        result.rows.append(ParsedRow(line_no, ts, raw_value[:64], value))

    if not result.rows:
        raise ParseError("The file has a header but no rows with a valid timestamp.")
    return result
