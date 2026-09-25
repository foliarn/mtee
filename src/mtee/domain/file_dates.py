"""Descriptive timestamps observed from a local file system."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from os import stat_result
from pathlib import Path

__all__ = ["FileDates", "format_file_timestamp"]


@dataclass(frozen=True, slots=True)
class FileDates:
    """Creation and modification instants in UTC nanoseconds."""

    created_at_ns: int | None
    modified_at_ns: int

    @classmethod
    def observe(cls, path: Path | str) -> FileDates:
        """Observe supported timestamps without treating POSIX ctime as creation."""
        return cls.from_stat(os.stat(path))

    @classmethod
    def from_stat(cls, status: stat_result) -> FileDates:
        created = getattr(status, "st_birthtime_ns", None)
        return cls(
            created_at_ns=int(created) if created is not None and created >= 0 else None,
            modified_at_ns=max(0, int(status.st_mtime_ns)),
        )


def format_file_timestamp(timestamp_ns: int | None) -> str:
    """Format a UTC timestamp in the local time zone for the English UI."""
    if timestamp_ns is None:
        return "—"
    try:
        instant = datetime.fromtimestamp(timestamp_ns / 1_000_000_000, tz=UTC).astimezone()
    except (OverflowError, OSError, ValueError):
        return "—"
    return instant.strftime("%Y-%m-%d %H:%M:%S")
