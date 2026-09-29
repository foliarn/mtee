"""Tempo estimation from an onset-strength envelope.

The envelope of a track with a steady pulse is periodic, so its Fourier spectrum
shows lines at the beat frequency and at its harmonics. A candidate tempo is
scored by the excess energy on the whole comb of its harmonics, divided by the
square root of the number of teeth. That statistic prefers the true pulse to its
half and double: a half-tempo comb adds teeth without signal, a double-tempo comb
loses signal teeth.

The spectrum of the whole track is used, so the estimate improves with the
length of the track and resolves fractions of a beat per minute. It assumes a
tempo that stays stable, as in music produced on a grid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = ["TempoEstimate", "comb_scores", "estimate_tempo"]

_MIN_SECONDS = 8.0
_MAX_TEETH = 8
_PADDING_FACTOR = 16
_MAX_FFT = 1 << 22
_GRID_STEP_BPM = 0.01
_MIN_SCORE = 12.0
_PRIOR_CENTRE_BPM = 120.0
_PRIOR_SPREAD_OCTAVES = 1.0
_WHITENING_HZ = 1.2


@dataclass(frozen=True, slots=True)
class TempoEstimate:
    """A tempo and the strength of the periodic evidence behind it."""

    bpm: float
    score: float


def estimate_tempo(
    envelope: np.ndarray, rate: float, bpm_min: float, bpm_max: float
) -> TempoEstimate | None:
    """Return the tempo of ``envelope`` inside ``[bpm_min, bpm_max]``, or ``None``.

    ``rate`` is the number of envelope values per second. ``None`` means the
    material is too short, silent or without a steady pulse; no value is invented.
    """
    if bpm_min <= 0 or bpm_max < 2 * bpm_min - 1e-9:
        raise ValueError("the tempo range must span at least one octave")
    grid = np.arange(bpm_min, bpm_max + _GRID_STEP_BPM / 2, _GRID_STEP_BPM)
    scores = comb_scores(envelope, rate, grid)
    if scores is None:
        return None
    weighted = scores * _prior(grid)
    best = int(np.argmax(weighted))
    if scores[best] < _MIN_SCORE:
        return None
    refined = _parabolic_peak(grid, weighted, best)
    return TempoEstimate(bpm=float(refined), score=float(scores[best]))


def comb_scores(envelope: np.ndarray, rate: float, grid: np.ndarray) -> np.ndarray | None:
    """Return the harmonic-comb score of every tempo of ``grid`` (in BPM)."""
    if envelope.size < rate * _MIN_SECONDS:
        return None
    signal = np.asarray(envelope, dtype=np.float64)
    signal = signal - _moving_average(signal, max(3, round(rate)))
    np.maximum(signal, 0.0, out=signal)
    spread = signal.std()
    if not math.isfinite(spread) or spread < 1e-9:
        return None
    signal -= signal.mean()
    signal *= np.hanning(signal.size)
    size = min(_MAX_FFT, 1 << math.ceil(math.log2(signal.size * _PADDING_FACTOR)))
    magnitude = np.abs(np.fft.rfft(signal, size))
    frequencies = np.fft.rfftfreq(size, 1.0 / rate)
    width = max(3, round(_WHITENING_HZ * size / rate))
    baseline = _moving_average(magnitude, width)
    excess = magnitude / np.maximum(baseline, 1e-12) - 1.0

    fundamental = grid / 60.0
    teeth = np.minimum(_MAX_TEETH, np.floor(0.45 * rate / fundamental)).astype(int)
    scores = np.zeros_like(grid)
    for harmonic in range(1, _MAX_TEETH + 1):
        active = teeth >= harmonic
        if not active.any():
            break
        scores[active] += np.interp(harmonic * fundamental[active], frequencies, excess)
    return scores / np.sqrt(np.maximum(teeth, 1))


def _prior(bpm: np.ndarray) -> np.ndarray:
    """Mildly favour common tempos so exact octave ties resolve consistently."""
    distance = np.log2(bpm / _PRIOR_CENTRE_BPM) / _PRIOR_SPREAD_OCTAVES
    return np.exp(-0.5 * distance * distance)


def _moving_average(values: np.ndarray, width: int) -> np.ndarray:
    """Centred moving average with edge handling by shrinking windows."""
    width = min(width, values.size)
    cumulative = np.concatenate(([0.0], np.cumsum(values)))
    half = width // 2
    indices = np.arange(values.size)
    lower = np.clip(indices - half, 0, values.size)
    upper = np.clip(indices + half + 1, 0, values.size)
    return (cumulative[upper] - cumulative[lower]) / (upper - lower)


def _parabolic_peak(grid: np.ndarray, values: np.ndarray, index: int) -> float:
    """Return the abscissa of the parabola through the peak and its neighbours."""
    if index <= 0 or index >= grid.size - 1:
        return float(grid[index])
    left, middle, right = values[index - 1], values[index], values[index + 1]
    denominator = left - 2.0 * middle + right
    if abs(denominator) < 1e-12:
        return float(grid[index])
    shift = 0.5 * (left - right) / denominator
    return float(grid[index] + max(-1.0, min(1.0, shift)) * (grid[1] - grid[0]))
