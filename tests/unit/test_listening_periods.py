"""Calendar periods of the listening statistics and the chart buckets (pure functions)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from mtee.domain.listening_periods import calendar_period, listening_buckets


def local_midnight(day: date) -> datetime:
    """Expected boundary: the local midnight of ``day`` as UTC, resolved by the machine."""
    return datetime.combine(day, datetime.min.time()).astimezone().astimezone(UTC)


def local_now(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, 0).astimezone()


def test_week_starts_on_monday_and_ends_on_the_next_monday() -> None:
    # 14 October 2026 is a Wednesday.
    period = calendar_period("week", local_now(2026, 10, 14))
    assert period.start == local_midnight(date(2026, 10, 12))
    assert period.end == local_midnight(date(2026, 10, 19))


def test_a_monday_and_a_sunday_belong_to_their_own_week() -> None:
    monday = calendar_period("week", local_now(2026, 10, 12, hour=0))
    sunday = calendar_period("week", local_now(2026, 10, 18, hour=23))
    assert monday.start == local_midnight(date(2026, 10, 12))
    assert sunday.start == local_midnight(date(2026, 10, 12))


def test_month_and_year_use_local_calendar_boundaries() -> None:
    month = calendar_period("month", local_now(2026, 10, 14))
    assert month.start == local_midnight(date(2026, 10, 1))
    assert month.end == local_midnight(date(2026, 11, 1))
    year = calendar_period("year", local_now(2026, 10, 14))
    assert year.start == local_midnight(date(2026, 1, 1))
    assert year.end == local_midnight(date(2027, 1, 1))


def test_december_month_ends_in_january() -> None:
    period = calendar_period("month", local_now(2026, 12, 31))
    assert period.end == local_midnight(date(2027, 1, 1))


def test_all_time_is_unbounded() -> None:
    period = calendar_period("all", local_now(2026, 10, 14))
    assert period.start is None
    assert period.end is None


def test_unknown_kind_and_naive_now_are_refused() -> None:
    with pytest.raises(ValueError):
        calendar_period("decade", local_now(2026, 10, 14))
    with pytest.raises(ValueError):
        calendar_period("week", datetime(2026, 10, 14, 12, 0))


def test_week_buckets_cover_seven_days_with_empty_days_kept() -> None:
    now = local_now(2026, 10, 14)
    rows = [
        (date(2026, 10, 12), 1_000, 1),
        (date(2026, 10, 14), 2_500, 0),
        (date(2026, 10, 14), 500, 1),
        (date(2026, 10, 1), 9_999, 1),  # outside the week: ignored
    ]
    buckets = listening_buckets("week", now, rows)
    assert [bucket.start for bucket in buckets] == [
        date(2026, 10, 12) + timedelta(days=i) for i in range(7)
    ]
    assert all(bucket.granularity == "day" for bucket in buckets)
    assert (buckets[0].listening_ms, buckets[0].counted_plays) == (1_000, 1)
    assert (buckets[1].listening_ms, buckets[1].counted_plays) == (0, 0)
    assert (buckets[2].listening_ms, buckets[2].counted_plays) == (3_000, 1)


def test_month_buckets_have_one_bar_per_day() -> None:
    buckets = listening_buckets("month", local_now(2026, 2, 10), [])
    assert len(buckets) == 28
    assert buckets[-1].start == date(2026, 2, 28)


def test_year_buckets_group_by_month() -> None:
    rows = [(date(2026, 3, 4), 100, 1), (date(2026, 3, 30), 50, 0), (date(2025, 12, 31), 7, 1)]
    buckets = listening_buckets("year", local_now(2026, 10, 14), rows)
    assert len(buckets) == 12
    assert all(bucket.granularity == "month" for bucket in buckets)
    march = buckets[2]
    assert (march.start, march.listening_ms, march.counted_plays) == (date(2026, 3, 1), 150, 1)
    assert sum(bucket.listening_ms for bucket in buckets) == 150


def test_all_time_buckets_run_from_the_first_month_to_now() -> None:
    now = local_now(2026, 10, 14)
    rows = [(date(2026, 3, 4), 100, 1), (date(2026, 10, 2), 40, 1)]
    buckets = listening_buckets("all", now, rows)
    assert [bucket.start for bucket in buckets] == [
        date(2026, 3, 1),
        date(2026, 4, 1),
        date(2026, 5, 1),
        date(2026, 6, 1),
        date(2026, 7, 1),
        date(2026, 8, 1),
        date(2026, 9, 1),
        date(2026, 10, 1),
    ]
    assert buckets[0].listening_ms == 100
    assert buckets[-1].counted_plays == 1
    assert listening_buckets("all", now, []) == []
