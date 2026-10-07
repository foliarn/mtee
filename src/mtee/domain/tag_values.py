"""Check and normalize what the user types in a tag before it is written.

Only edited values are checked: a tag written by another tool is shown and kept as is
until the user changes it.
"""

from __future__ import annotations

import re
from datetime import date

from mtee.domain.musical_key import format_key, parse_key

__all__ = ["normalize_date", "validate_field"]

_YEAR_FIRST = re.compile(r"^(\d{4})(?:[-/.](\d{1,2})(?:[-/.](\d{1,2}))?)?$")
_DAY_FIRST = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_TRACK = re.compile(r"^\d{1,4}(?:/\d{1,4})?$")
_NUMBER = re.compile(r"^\d{1,3}(?:[.,]\d{1,2})?$")
_DATE_HINT = "Use a year, a year and month, or a full date: 2024, 2024-03 or 2024-03-05."


def normalize_date(text: str) -> tuple[str, str]:
    """Return ``(date, error)``: ISO 8601 ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD``.

    A year comes first with ``-``, ``/`` or ``.``; a day-first date needs dots
    (``5.3.2024``), because ``5/3/2024`` could be read either way.
    """
    value = text.strip()
    match = _YEAR_FIRST.match(value)
    if match is not None:
        year, month, day = match.group(1), match.group(2), match.group(3)
    else:
        day_first = _DAY_FIRST.match(value)
        if day_first is None:
            return "", _DATE_HINT
        day, month, year = day_first.groups()
    try:
        if month is None:
            if not 1000 <= int(year) <= 2999:
                raise ValueError
            return year, ""
        if day is None:
            date(int(year), int(month), 1)
            return f"{year}-{int(month):02d}", ""
        date(int(year), int(month), int(day))
    except ValueError:
        return "", f"This is not a real date. {_DATE_HINT}"
    return f"{year}-{int(month):02d}-{int(day):02d}", ""


def validate_field(field: str, text: str, notation: str = "camelot") -> tuple[str, str]:
    """Return ``(value to write, error)``; an empty value is a removal and always valid."""
    value = text.strip() if field != "comment" else text
    if not value.strip():
        return "", ""
    if field == "date":
        return normalize_date(value)
    if field == "track_number":
        if _TRACK.match(value):
            return value, ""
        return "", "Use a number, or a number and a total: 3 or 3/12."
    if field == "bpm":
        if _NUMBER.match(value) and 20 <= float(value.replace(",", ".")) <= 400:
            return value.replace(",", "."), ""
        return "", "Use a tempo between 20 and 400, such as 174 or 87.5."
    if field == "key":
        if parse_key(value) is None:
            return "", "Use a Camelot code (8A) or a key name (Am, F#m, Bb)."
        return format_key(value, notation), ""
    return value, ""
