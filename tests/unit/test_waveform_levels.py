from __future__ import annotations

import math

import pytest

from mtee.domain.waveform import WaveformPoints
from mtee.domain.waveform_levels import WAVEFORM_DISPLAY_GAMMA, bar_levels


def _points(rms: list[int]) -> WaveformPoints:
    zeros = tuple(0 for _ in rms)
    return WaveformPoints(1_000_000, zeros, zeros, tuple(rms))


def test_the_loudest_bar_of_the_track_is_one() -> None:
    levels = bar_levels(_points([100, 400, 200, 50] * 10), 4, 1.6)
    assert max(levels) == pytest.approx(1.0)
    assert all(0.0 <= level <= 1.0 for level in levels)


def test_the_normalisation_is_per_track() -> None:
    quiet = bar_levels(_points([10, 20, 40, 20]), 4, 1.0)
    loud = bar_levels(_points([1_000, 2_000, 4_000, 2_000]), 4, 1.0)
    assert quiet == pytest.approx(loud)


def test_a_silent_track_gives_only_zeros() -> None:
    assert bar_levels(_points([0] * 50), 10, 1.6) == [0.0] * 10


def test_more_bars_than_points_gives_one_bar_per_point() -> None:
    levels = bar_levels(_points([10, 20, 40]), 100, 1.0)
    assert levels == pytest.approx([0.25, 0.5, 1.0])


def test_a_bar_groups_a_contiguous_range_by_energy() -> None:
    # Two points per bar: energy is the root mean square of the grouped values.
    levels = bar_levels(_points([3, 4, 0, 0]), 2, 1.0)
    assert levels[1] == 0.0
    assert levels[0] == pytest.approx(1.0)
    levels = bar_levels(_points([3, 4, 5, 5]), 2, 1.0)
    assert levels[0] == pytest.approx(math.sqrt((9 + 16) / 2) / 5)


def test_gamma_one_keeps_the_ratio_and_a_larger_gamma_widens_the_gaps() -> None:
    points = _points([1_000] * 5 + [708] * 5)  # the second half is 3 dB lower
    flat = bar_levels(points, 2, 1.0)
    steep = bar_levels(points, 2, 2.2)
    assert flat[1] == pytest.approx(0.708)
    assert steep[1] < bar_levels(points, 2, 1.6)[1] < flat[1]


def test_two_sections_three_decibels_apart_differ_by_at_least_twenty_percent() -> None:
    points = _points([1_000] * 50 + [708] * 50)
    levels = bar_levels(points, 10, WAVEFORM_DISPLAY_GAMMA)
    loud, soft = levels[0], levels[-1]
    assert (loud - soft) / loud >= 0.20


def test_invalid_arguments_are_refused() -> None:
    with pytest.raises(ValueError):
        bar_levels(_points([1]), 0, 1.6)
    with pytest.raises(ValueError):
        bar_levels(_points([1]), 4, 0)


def test_computing_levels_for_a_full_waveform_is_fast() -> None:
    import time

    points = _points([(i * 37) % 32_767 for i in range(1_200)])
    start = time.perf_counter()
    for _ in range(20):
        bar_levels(points, 480, 1.6)
    per_call = (time.perf_counter() - start) / 20
    assert per_call < 0.05  # generous bound; measured and recorded in the validation report
