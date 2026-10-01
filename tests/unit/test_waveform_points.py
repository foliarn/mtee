from __future__ import annotations

import numpy as np
import pytest

from mtee.domain.waveform import WAVEFORM_POINTS, WaveformPoints
from mtee.services.analysis.features import WAVEFORM_BIN_FRAMES, FeatureExtractor
from mtee.services.analysis.waveform import reduce_waveform


def _stereo(values: np.ndarray) -> np.ndarray:
    return np.stack([values, values], axis=1).astype("<i2")


def _energy(low: np.ndarray, high: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return a plausible (sum of squares, sample count) pair for min/max bins."""
    count = np.full(low.size, 2 * WAVEFORM_BIN_FRAMES, dtype=np.int64)
    sumsq = (np.maximum(np.abs(low.astype(np.int64)), high.astype(np.int64)) ** 2) * count
    return sumsq, count


def test_reduction_keeps_every_extreme_and_the_fixed_size() -> None:
    generator = np.random.default_rng(1)
    low = generator.integers(-30_000, 0, 50_000).astype(np.int16)
    high = generator.integers(0, 30_000, 50_000).astype(np.int16)
    low[12_345] = -32768
    high[49_999] = 32767
    points = reduce_waveform(low, high, *_energy(low, high), 1_000_000)
    assert len(points) == WAVEFORM_POINTS
    assert min(points.lows) == -32768
    assert max(points.highs) == 32767
    assert points.lows[-1] <= low[-1] and points.highs[-1] >= high[-1]


def test_a_short_track_keeps_one_point_per_bin() -> None:
    low = np.array([-1, -2, -3], dtype=np.int16)
    high = np.array([1, 2, 3], dtype=np.int16)
    points = reduce_waveform(low, high, *_energy(low, high), 60_000)
    assert points.lows == (-1, -2, -3)
    assert points.highs == (1, 2, 3)
    assert points.rms == (1, 2, 3)


def test_the_reduction_of_a_long_mix_is_fast() -> None:
    bins = 3 * 3600 * 50  # three hours of 20 ms bins
    low = np.full(bins, -100, dtype=np.int16)
    high = np.full(bins, 100, dtype=np.int16)
    points = reduce_waveform(low, high, *_energy(low, high), 3 * 3600 * 1_000_000)
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
    assert np.array_equal(first.waveform_sumsq, second.waveform_sumsq)
    assert np.array_equal(first.waveform_count, second.waveform_count)
    expected = samples[: WAVEFORM_BIN_FRAMES * 40].reshape(40, WAVEFORM_BIN_FRAMES)
    assert np.array_equal(first.waveform_low[:40], expected.min(axis=1))
    assert np.array_equal(first.waveform_high[:40], expected.max(axis=1))
    assert first.waveform_low.size == 41  # the partial last bin is kept
    assert first.waveform_sumsq.size == first.waveform_count.size == 41
    full_bins = 2 * np.square(expected.astype(np.int64)).sum(axis=1)
    assert np.array_equal(first.waveform_sumsq[:40], full_bins)
    assert np.array_equal(first.waveform_count[:40], np.full(40, 2 * WAVEFORM_BIN_FRAMES))
    assert first.waveform_count[40] == 2 * 123  # the partial bin counts its own samples


def test_stored_bytes_round_trip() -> None:
    points = WaveformPoints(2_000_000, (-5, -32768, 0), (5, 32767, 0), (3, 32767, 0))
    payload = points.to_bytes()
    assert len(payload) == 3 * 6
    restored = WaveformPoints.from_bytes(2_000_000, payload)
    assert restored == points


@pytest.mark.parametrize("payload", [b"", b"abc", bytes(4), bytes(12 + 4)])
def test_a_damaged_stored_waveform_is_refused(payload: bytes) -> None:
    with pytest.raises(ValueError):
        WaveformPoints.from_bytes(1_000, payload)


def test_a_waveform_needs_a_duration_and_matching_arrays() -> None:
    with pytest.raises(ValueError):
        WaveformPoints(0, (1,), (1,), (1,))
    with pytest.raises(ValueError):
        WaveformPoints(1_000, (1, 2), (1,), (1, 1))
    with pytest.raises(ValueError):
        WaveformPoints(1_000, (1,), (1,), (1, 1))
    with pytest.raises(ValueError):
        WaveformPoints(1_000, (40_000,), (1,), (1,))
    with pytest.raises(ValueError):
        WaveformPoints(1_000, (1,), (1,), (32_768,))
    with pytest.raises(ValueError):
        WaveformPoints(1_000, (1,), (1,), (-1,))


def test_the_rms_of_a_constant_signal_is_its_level() -> None:
    extractor = FeatureExtractor(rhythm=False, tonality=False)
    extractor.feed(_stereo(np.full(WAVEFORM_BIN_FRAMES * 100, 8_000, dtype=np.int16)))
    features = extractor.finish()
    points = reduce_waveform(
        features.waveform_low,
        features.waveform_high,
        features.waveform_sumsq,
        features.waveform_count,
        features.duration_us,
        points=10,
    )
    assert points.rms == (8_000,) * 10


def test_the_rms_of_a_sine_is_its_amplitude_over_root_two() -> None:
    frames = WAVEFORM_BIN_FRAMES * 200
    phase = np.arange(frames) * 2 * np.pi * 9 / WAVEFORM_BIN_FRAMES  # nine whole periods per bin
    amplitude = 20_000
    sine = np.rint(amplitude * np.sin(phase)).astype(np.int16)
    extractor = FeatureExtractor(rhythm=False, tonality=False)
    extractor.feed(_stereo(sine))
    features = extractor.finish()
    points = reduce_waveform(
        features.waveform_low,
        features.waveform_high,
        features.waveform_sumsq,
        features.waveform_count,
        features.duration_us,
        points=20,
    )
    expected = amplitude / np.sqrt(2)
    assert all(abs(value - expected) <= 2 for value in points.rms)


def test_the_rms_groups_every_sample_of_the_grouped_bins() -> None:
    low = np.array([0, 0, 0, 0], dtype=np.int16)
    high = np.array([0, 0, 0, 0], dtype=np.int16)
    sumsq = np.array([100, 300, 0, 0], dtype=np.int64)
    count = np.array([1, 3, 1, 1], dtype=np.int64)
    points = reduce_waveform(low, high, sumsq, count, 80_000, points=2)
    assert points.rms == (10, 0)  # sqrt(400 / 4) and sqrt(0 / 2)
