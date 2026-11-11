"""Parser for raw temperature-logger exports.

The files only ever carry a time and a temperature, but they arrive in many shapes:
device metadata lines before the header, comma / semicolon / tab delimiters, reversed
``Temp,Time`` columns, ``ERR`` cells, ISO ``T`` timestamps and day-first ``DD/MM/YYYY``.
The parser does not convert units or timezones; that is ``app.normalize``'s job, because
the unit comes from the registry, never from the file.
"""

from app.parsing.parser import ParsedRow, ParseError, ParseResult, RejectedLine, parse_bytes

__all__ = ["ParseError", "ParseResult", "ParsedRow", "RejectedLine", "parse_bytes"]
