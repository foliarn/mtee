from __future__ import annotations

from mtee.domain.time import TimeRange


def test_time_range_uses_half_open_sample_covering_rounding() -> None:
    interval = TimeRange(1, 101)
    assert interval.to_sample_range(44_100) == (0, 5)
    assert interval.contains(100)
    assert not interval.contains(101)
