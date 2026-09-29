from __future__ import annotations

import struct

import numpy as np
import pytest

from mtee.domain.waveform import WAVEFORM_POINTS, WaveformPoints
from mtee.services.analysis.features import WAVEFORM_BIN_FRAMES, FeatureExtractor
from mtee.services.analysis.waveform import reduce_waveform


def _stereo(values: np.ndarray) -> np.ndarray:
    return np.stack([values, values], axis=1).astype("<i2")


def test_reduction_keeps_every_extreme_and_the_fixed_size() -> None:
    generator = np.random.default_rng(1)
    low = generator.integers(-30_000, 0, 50_000).astype(np.int16)
    high = generator.integers(0, 30_000, 50_000).astype(np.int16)
    low[12_345] = -32768
    high[49_999] = 32767
    points = reduce_waveform(low, high, 1_000_000)
    assert len(points) == WAVEFORM_POINTS
    assert min(points.lows) == -32768
    assert max(points.highs) == 32767
    assert points.lows[-1] <= low[-1] and points.highs[-1] >= high[-1]


def test_a_short_track_keeps_one_point_per_bin() -> None:
    low = np.array([-1, -2, -3], dtype=np.int16)
    high = np.array([1, 2, 3], dtype=np.int16)
    points = reduce_waveform(low, high, 60_000)
    assert points.lows == (-1, -2, -3)
    assert points.highs == (1, 2, 3)


def test_the_reduction_of_a_long_mix_is_fast() -> None:
    bins = 3 * 3600 * 50  # three hours of 20 ms bins
    low = np.full(bins, -100, dtype=np.int16)
    high = np.full(bins, 100, dtype=np.int16)
    points = reduce_waveform(low, high, 3 * 3600 * 1_000_000)
    assert len(points) == WAVEFORM_POINTS


def test_bins_do_not_depend_on_how_the_stream_is_cut() -> None:
    generator = np.random.default_rng(2)
    samples = generator.integers(-20_000, 20_000, WAVEFORM_BIN_FRAMES * 40 + 123).astype(np.int16)
    pcm = _stereo(samples).tobytes()
    whole = FeatureExtractor(rhythm=False, tonality=False)
    whole.feed(pcm)
    cut = FeatureExtractor(rhythm=False, tonality=False)
    position = 0
    for size in (4, 1_000, 4_444, 20, 60_000):
        cut.feed(pcm[position : position + size])
        position += size
    cut.feed(pcm[position:])
    first, second = whole.finish(), cut.finish()
    assert first.frames == second.frames == samples.size
    assert np.array_equal(first.waveform_low, second.waveform_low)
    assert np.array_equal(first.waveform_high, second.waveform_high)
    expected = samples[: WAVEFORM_BIN_FRAMES * 40].reshape(40, WAVEFORM_BIN_FRAMES)
    assert np.array_equal(first.waveform_low[:40], expected.min(axis=1))
    assert np.array_equal(first.waveform_high[:40], expected.max(axis=1))
    assert first.waveform_low.size == 41  # the partial last bin is kept


def test_stored_bytes_round_trip() -> None:
    points = WaveformPoints(2_000_000, (-5, -32768, 0), (5, 32767, 0))
    restored = WaveformPoints.from_bytes(2_000_000, points.to_bytes())
    assert restored == points
    assert points.samples()[1] == [-1.0, 32767 / 32768.0]


def test_the_interface_buffer_holds_scaled_float_pairs() -> None:
    points = WaveformPoints(2_000_000, (-32768, -16384), (32767, 0))
    packed = points.packed()
    assert len(packed) == 2 * 2 * 4
    assert struct.unpack("<4f", packed) == (-1.0, 32767 / 32768.0, -0.5, 0.0)


@pytest.mark.parametrize("payload", [b"", b"abc"])
def test_a_damaged_stored_waveform_is_refused(payload: bytes) -> None:
    with pytest.raises(ValueError):
        WaveformPoints.from_bytes(1_000, payload)


def test_a_waveform_needs_a_duration_and_matching_arrays() -> None:
    with pytest.raises(ValueError):
        WaveformPoints(0, (1,), (1,))
    with pytest.raises(ValueError):
        WaveformPoints(1_000, (1, 2), (1,))
    with pytest.raises(ValueError):
        WaveformPoints(1_000, (40_000,), (1,))
