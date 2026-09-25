from __future__ import annotations

import pytest

from mtee.domain.time import TimeRange
from mtee.domain.waveform import WaveformConfig


def test_time_range_uses_half_open_sample_covering_rounding() -> None:
    interval = TimeRange(1, 101)
    assert interval.to_sample_range(44_100) == (0, 5)
    assert interval.contains(100)
    assert not interval.contains(101)


@pytest.mark.parametrize("values", [(0, 2, 20), (44_100, 0, 20), (44_100, 2, 0)])
def test_waveform_config_rejects_invalid_parameters(values: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError):
        WaveformConfig(sample_rate=values[0], channels=values[1], bin_ms=values[2])
