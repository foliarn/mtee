from __future__ import annotations

from types import SimpleNamespace

from mtee.domain.file_dates import FileDates, format_file_timestamp


def test_file_dates_use_birth_time_when_available_and_never_ctime() -> None:
    dates = FileDates.from_stat(
        SimpleNamespace(
            st_birthtime_ns=1_700_000_000_000_000_000,
            st_ctime_ns=1_800_000_000_000_000_000,
            st_mtime_ns=1_750_000_000_000_000_000,
        )  # type: ignore[arg-type]
    )
    assert dates.created_at_ns == 1_700_000_000_000_000_000
    assert dates.modified_at_ns == 1_750_000_000_000_000_000


def test_file_dates_leave_creation_unknown_when_birth_time_is_unavailable() -> None:
    dates = FileDates.from_stat(
        SimpleNamespace(
            st_ctime_ns=1_800_000_000_000_000_000, st_mtime_ns=1_750_000_000_000_000_000
        )  # type: ignore[arg-type]
    )
    assert dates.created_at_ns is None
    assert dates.modified_at_ns == 1_750_000_000_000_000_000
    assert format_file_timestamp(None) == "—"
