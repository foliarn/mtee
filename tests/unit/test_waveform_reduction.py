from __future__ import annotations

from mtee.domain.waveform import WaveformLevel
from mtee.services.waveform_service import _reduce_level


def test_waveform_pyramid_preserves_one_sample_impulses() -> None:
    values = [0, 0] * 15 + [-32768, 32767]
    level = WaveformLevel(16, 1, tuple(values))
    while level.bin_count > 1:
        level = _reduce_level(level)
    assert level.bin(0) == (-32768, 32767)


def test_silent_stereo_channel_does_not_inherit_other_channel_peaks() -> None:
    level = WaveformLevel(
        4, 2, (0, 0, -1000, 1000, 0, 0, -2000, 2000, 0, 0, -3000, 3000, 0, 0, -4000, 4000)
    )
    reduced = _reduce_level(level)
    assert reduced.bin(0, 0) == (0, 0)
    assert reduced.bin(0, 1) == (-2000, 2000)
