"""Internal time contract: microseconds, excluded end and explicit rounding."""

from __future__ import annotations

import pytest

from mtee.domain.time import TimeRange


def test_the_end_bound_is_excluded() -> None:
    span = TimeRange(1_000, 2_000)

    assert span.contains(1_000)
    assert not span.contains(2_000)
    assert span.duration_us == 1_000


@pytest.mark.parametrize("bounds", [(0, 0), (10, 10), (10, 9), (-1, 10)])
def test_an_empty_or_negative_range_is_refused(bounds: tuple[int, int]) -> None:
    with pytest.raises(ValueError):
        TimeRange(*bounds)


def test_a_float_bound_is_refused_to_keep_integer_microseconds() -> None:
    with pytest.raises(TypeError):
        TimeRange(0.5, 10)  # type: ignore[arg-type]


def test_seconds_are_converted_to_microseconds() -> None:
    assert TimeRange.from_seconds(1.5, 2.25) == TimeRange(1_500_000, 2_250_000)


def test_touching_ranges_do_not_overlap() -> None:
    first = TimeRange(0, 1_000)
    second = TimeRange(1_000, 2_000)

    assert not first.overlaps(second)
    assert first.overlaps(TimeRange(999, 2_000))


def test_sample_bounds_cover_the_whole_range() -> None:
    span = TimeRange(1_000_000, 2_000_000)

    assert span.to_sample_range(44_100) == (44_100, 88_200)


def test_a_range_shorter_than_one_sample_still_covers_one_sample() -> None:
    span = TimeRange(0, 1)

    start, end = span.to_sample_range(44_100)

    assert (start, end) == (0, 1)


def test_a_sample_rate_must_be_positive() -> None:
    with pytest.raises(ValueError):
        TimeRange(0, 1_000).to_sample_range(0)
