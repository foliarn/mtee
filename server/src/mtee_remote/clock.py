"""The only source of time for the server, so tests can replace it."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def to_iso(dt: datetime) -> str:
    """Format a datetime as `2026-10-31T07:18:24.123456Z` (UTC, microseconds)."""
    if dt.tzinfo is None:
        raise ValueError("to_iso needs a timezone-aware datetime.")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
