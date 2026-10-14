"""Calendar periods of the listening statistics, in the local time zone.

A period is the UTC interval ``[start, end)`` of a local calendar unit: the week
starts on Monday, the month on its first day, the year on 1 January. Local
midnights are computed from naive local dates, so daylight saving time moves the
boundaries as the machine does. The functions take ``now`` explicitly; nothing
reads the clock here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from mtee.domain.play_log import ListeningPeriod

__all__ = [
    "PERIOD_KINDS",
    "ListeningBucket",
    "PeriodKind",
    "calendar_period",
    "listening_buckets",
]

PeriodKind = Literal["week", "month", "year", "all"]
PERIOD_KINDS: tuple[PeriodKind, ...] = ("week", "month", "year", "all")


@dataclass(frozen=True, slots=True)
class ListeningBucket:
    """One bar of the listening chart: a local day, or a local month for long periods."""

    start: date
    granularity: Literal["day", "month"]
    listening_ms: int
    counted_plays: int


def calendar_period(kind: str, now: datetime) -> ListeningPeriod:
    """Return the period that contains ``now`` (an aware datetime) for ``kind``.

    ``all`` is the unbounded period. An unknown kind raises ``ValueError``.
    """
    if kind == "all":
        return ListeningPeriod()
    today = _local_date(now)
    start, end = _calendar_days(kind, today)
    return ListeningPeriod(start=_local_midnight(start), end=_local_midnight(end))


def listening_buckets(
    kind: str,
    now: datetime,
    daily: Iterable[tuple[date, int, int]],
) -> list[ListeningBucket]:
    """Group per-day rows ``(local day, listening_ms, counted_plays)`` for the chart.

    Week, month and year return one bucket per day of the period, days without
    listening included, so the axis is complete. ``all`` returns one bucket per
    month from the first listening to the current month; it is empty without data.
    """
    rows = list(daily)
    today = _local_date(now)
    if kind == "all":
        if not rows:
            return []
        first = min(day for day, _, _ in rows)
        return _monthly(rows, _month_starts(_month_start(first), _month_start(today)))
    start, end = _calendar_days(kind, today)
    if kind == "year":
        return _monthly(rows, _month_starts(start, _month_start(end - timedelta(days=1))))
    per_day = _sum_by(rows, lambda day: day)
    buckets: list[ListeningBucket] = []
    day = start
    while day < end:
        ms, counted = per_day.get(day, (0, 0))
        buckets.append(ListeningBucket(day, "day", ms, counted))
        day += timedelta(days=1)
    return buckets


def _monthly(rows: list[tuple[date, int, int]], months: list[date]) -> list[ListeningBucket]:
    per_month = _sum_by(rows, _month_start)
    return [ListeningBucket(month, "month", *per_month.get(month, (0, 0))) for month in months]


def _sum_by(
    rows: list[tuple[date, int, int]], key: Callable[[date], date]
) -> dict[date, tuple[int, int]]:
    """Add the listening and counted plays of every row to the bucket of its ``key``."""
    totals: dict[date, tuple[int, int]] = {}
    for day, ms, counted in rows:
        bucket = key(day)
        previous_ms, previous_counted = totals.get(bucket, (0, 0))
        totals[bucket] = (previous_ms + ms, previous_counted + counted)
    return totals


def _calendar_days(kind: str, today: date) -> tuple[date, date]:
    if kind == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=7)
    if kind == "month":
        start = today.replace(day=1)
        return start, _next_month(start)
    if kind == "year":
        return date(today.year, 1, 1), date(today.year + 1, 1, 1)
    raise ValueError(f"unknown statistics period: {kind!r}")


def _local_date(value: datetime) -> date:
    if value.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    return value.astimezone().date()


def _local_midnight(day: date) -> datetime:
    """Local midnight of ``day`` as UTC; Python resolves the local offset of that date."""
    return datetime.combine(day, time()).astimezone().astimezone(UTC)


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _next_month(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _month_starts(first: date, last: date) -> list[date]:
    months: list[date] = []
    current = _month_start(first)
    while current <= last:
        months.append(current)
        current = _next_month(current)
    return months
