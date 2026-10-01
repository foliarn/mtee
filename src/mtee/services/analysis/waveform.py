"""Reduction of 20 ms min/max/energy bins to the fixed-size stored waveform."""

from __future__ import annotations

import numpy as np

from mtee.domain.waveform import RMS_MAX, WAVEFORM_POINTS, WaveformPoints

__all__ = ["reduce_waveform"]


def reduce_waveform(
    low: np.ndarray,
    high: np.ndarray,
    sumsq: np.ndarray,
    count: np.ndarray,
    duration_us: int,
    points: int = WAVEFORM_POINTS,
) -> WaveformPoints:
    """Return ``points`` min/max/RMS values covering the whole track.

    A track shorter than ``points`` bins keeps one point per bin. The RMS of a point is
    the square root of the mean square of all the samples of the bins it groups, scaled
    to ``0..32767``. The reduction is one vectorised pass, so it takes milliseconds even
    for a multi-hour mix.
    """
    if low.size == 0 or not low.size == high.size == sumsq.size == count.size:
        raise ValueError("No decodable audio frames were found for the waveform.")
    size = min(points, low.size)
    edges = np.linspace(0, low.size, size + 1).astype(np.int64)[:-1]
    reduced_low = np.minimum.reduceat(low, edges)
    reduced_high = np.maximum.reduceat(high, edges)
    energy = np.add.reduceat(sumsq.astype(np.float64), edges)
    samples = np.add.reduceat(count.astype(np.float64), edges)
    rms = np.rint(np.sqrt(energy / np.maximum(samples, 1.0)))
    return WaveformPoints(
        duration_us,
        tuple(int(value) for value in reduced_low),
        tuple(int(value) for value in reduced_high),
        tuple(int(min(RMS_MAX, value)) for value in rms),
    )
