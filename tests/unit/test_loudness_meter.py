"""Integrated loudness and sample peak of synthetic signals against known values.

The reference values come from ITU-R BS.1770-4: a full-scale 997 Hz sine reads -3.01 LUFS
in one channel, and two identical channels add 3.01 LU. A 1 kHz sine of peak amplitude A
reads 20 log10(A) - 3.01 + 0.0 LUFS per channel, plus 3.01 LU for two channels. The
measurements are on synthetic tones only: nothing here claims anything about music.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from mtee.services.analysis.loudness import LoudnessMeter, k_weighting_sections

RATE_STANDARD = 48_000
RATE_ANALYSIS = 22_050


def _sine(
    rate: int, seconds: float, frequency: float, amplitude: float, channels: str
) -> np.ndarray:
    """Stereo int16 PCM of a sine on the channels named by ``channels`` ("LR", "L" or "R")."""
    time = np.arange(round(rate * seconds)) / rate
    tone = amplitude * np.sin(2 * np.pi * frequency * time)
    pcm = np.zeros((time.size, 2), dtype=np.float64)
    if "L" in channels:
        pcm[:, 0] = tone
    if "R" in channels:
        pcm[:, 1] = tone
    return np.round(pcm * 32767).astype(np.int16)


def _measure(pcm: np.ndarray, rate: int, chunk: int = 65_536):
    meter = LoudnessMeter(rate)
    for start in range(0, pcm.shape[0], chunk):
        meter.feed(pcm[start : start + chunk])
    return meter.finish()


def test_k_weighting_reproduces_the_published_48_khz_coefficients() -> None:
    (shelf_b, shelf_a), (highpass_b, highpass_a) = k_weighting_sections(RATE_STANDARD)

    assert shelf_b == pytest.approx(
        (1.53512485958697, -2.69169618940638, 1.19839281085285), abs=1e-9
    )
    assert shelf_a[1:] == pytest.approx((-1.69065929318241, 0.73248077421585), abs=1e-9)
    assert highpass_b == pytest.approx((1.0, -2.0, 1.0), abs=1e-12)
    assert highpass_a[1:] == pytest.approx((-1.99004745483398, 0.99007225036621), abs=1e-9)


def test_a_full_scale_sine_in_one_channel_reads_minus_3_01_lufs() -> None:
    result = _measure(_sine(RATE_STANDARD, 20, 997.0, 1.0, "L"), RATE_STANDARD)

    assert result.integrated_lufs == pytest.approx(-3.01, abs=0.02)
    assert result.sample_peak_dbfs == pytest.approx(0.0, abs=0.01)


def test_identical_stereo_channels_add_3_01_lu() -> None:
    one = _measure(_sine(RATE_STANDARD, 20, 997.0, 1.0, "L"), RATE_STANDARD)
    both = _measure(_sine(RATE_STANDARD, 20, 997.0, 1.0, "LR"), RATE_STANDARD)

    assert both.integrated_lufs - one.integrated_lufs == pytest.approx(3.01, abs=0.02)
    assert both.integrated_lufs == pytest.approx(0.0, abs=0.05)


@pytest.mark.parametrize("rate", [RATE_STANDARD, RATE_ANALYSIS])
def test_a_quiet_stereo_tone_reads_its_peak_level_plus_stereo_gain(rate: int) -> None:
    # Peak 0.1 (-20 dBFS) per channel: RMS -23.01 dBFS, two channels: -20.0 LUFS.
    result = _measure(_sine(rate, 20, 1000.0, 0.1, "LR"), rate)

    assert result.integrated_lufs == pytest.approx(-20.0, abs=0.05)
    assert result.sample_peak_dbfs == pytest.approx(-20.0, abs=0.01)


def test_the_analysis_rate_agrees_with_the_standard_rate() -> None:
    standard = _measure(_sine(RATE_STANDARD, 20, 1000.0, 0.1, "LR"), RATE_STANDARD)
    analysis = _measure(_sine(RATE_ANALYSIS, 20, 1000.0, 0.1, "LR"), RATE_ANALYSIS)

    assert analysis.integrated_lufs == pytest.approx(standard.integrated_lufs, abs=0.05)


def test_silence_has_no_loudness_and_no_peak() -> None:
    result = _measure(np.zeros((RATE_ANALYSIS * 5, 2), dtype=np.int16), RATE_ANALYSIS)

    assert result.integrated_lufs is None
    assert result.sample_peak_dbfs is None


def test_a_track_shorter_than_one_gating_block_has_no_loudness_but_a_peak() -> None:
    # 400 ms is the shortest block the standard defines.
    result = _measure(_sine(RATE_ANALYSIS, 0.3, 1000.0, 0.5, "LR"), RATE_ANALYSIS)

    assert result.integrated_lufs is None
    assert result.sample_peak_dbfs == pytest.approx(20 * math.log10(0.5), abs=0.01)


def test_an_empty_stream_has_nothing_to_report() -> None:
    meter = LoudnessMeter(RATE_ANALYSIS)
    result = meter.finish()

    assert result.integrated_lufs is None
    assert result.sample_peak_dbfs is None


def test_a_signal_below_the_absolute_gate_has_no_loudness() -> None:
    # About -80 LUFS in every block: all of them are discarded by the absolute gate.
    whisper = _sine(RATE_ANALYSIS, 20, 1000.0, 0.0001, "LR")

    assert _measure(whisper, RATE_ANALYSIS).integrated_lufs is None


def test_quiet_blocks_do_not_pull_the_result_down() -> None:
    loud = _sine(RATE_ANALYSIS, 20, 1000.0, 0.1, "LR")  # about -20 LUFS
    whisper = _sine(RATE_ANALYSIS, 20, 1000.0, 0.0001, "LR")  # about -80 LUFS
    alone = _measure(loud, RATE_ANALYSIS).integrated_lufs
    mixed = _measure(np.vstack((loud, whisper)), RATE_ANALYSIS).integrated_lufs

    assert mixed == pytest.approx(alone, abs=0.05)


def test_blocks_more_than_10_lu_below_the_mean_are_ignored() -> None:
    loud = _sine(RATE_ANALYSIS, 20, 1000.0, 0.1, "LR")  # about -20 LUFS
    quiet = _sine(RATE_ANALYSIS, 20, 1000.0, 0.1 * 10 ** (-20 / 20), "LR")  # about -40 LUFS
    alone = _measure(loud, RATE_ANALYSIS).integrated_lufs
    mixed = _measure(np.vstack((loud, quiet)), RATE_ANALYSIS).integrated_lufs

    assert mixed == pytest.approx(alone, abs=0.05)


def test_the_result_does_not_depend_on_how_the_stream_is_cut() -> None:
    generator = np.random.default_rng(11)
    noise = np.round(generator.standard_normal((RATE_ANALYSIS * 4, 2)) * 2000).astype(np.int16)
    whole = _measure(noise, RATE_ANALYSIS, chunk=noise.shape[0])
    for chunk in (97, 997, 4_096, 65_536):
        cut = _measure(noise, RATE_ANALYSIS, chunk=chunk)
        assert cut.integrated_lufs == pytest.approx(whole.integrated_lufs, abs=1e-9)
        assert cut.sample_peak_dbfs == pytest.approx(whole.sample_peak_dbfs, abs=1e-12)


def test_bytes_and_arrays_give_the_same_result() -> None:
    pcm = _sine(RATE_ANALYSIS, 3, 440.0, 0.3, "LR")
    as_bytes = LoudnessMeter(RATE_ANALYSIS)
    as_bytes.feed(pcm.astype("<i2").tobytes())
    as_array = LoudnessMeter(RATE_ANALYSIS)
    as_array.feed(pcm)

    assert as_bytes.finish() == as_array.finish()


def test_a_sample_rate_that_is_not_a_multiple_of_10_is_refused() -> None:
    with pytest.raises(ValueError, match="multiple of 10"):
        LoudnessMeter(22_055)
