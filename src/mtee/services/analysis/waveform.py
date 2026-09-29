"""Reduction of 20 ms min/max bins to the fixed-size stored waveform."""

from __future__ import annotations

import numpy as np

from mtee.domain.waveform import WAVEFORM_POINTS, WaveformPoints

__all__ = ["reduce_waveform"]


def reduce_waveform(
    low: np.ndarray, high: np.ndarray, duration_us: int, points: int = WAVEFORM_POINTS
) -> WaveformPoints:
    """Return ``points`` min/max values covering the whole track.

    A track shorter than ``points`` bins keeps one point per bin. The reduction is
    one vectorised pass, so it takes milliseconds even for a multi-hour mix.
    """
    if low.size == 0 or low.size != high.size:
        raise ValueError("No decodable audio frames were found for the waveform.")
    count = min(points, low.size)
    edges = np.linspace(0, low.size, count + 1).astype(np.int64)[:-1]
    reduced_low = np.minimum.reduceat(low, edges)
    reduced_high = np.maximum.reduceat(high, edges)
    return WaveformPoints(
        duration_us,
        tuple(int(value) for value in reduced_low),
        tuple(int(value) for value in reduced_high),
    )
