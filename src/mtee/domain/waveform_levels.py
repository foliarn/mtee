"""Heights of the waveform bars, from the stored RMS energy of a track.

Every bar groups a contiguous range of stored points. Its energy is normalised by the
loudest bar of the same track, so that the quiet and the loud parts of one track both
use the full height, then raised to ``gamma``: above 1, two sections a few decibels
apart keep clearly different heights instead of all saturating.
"""

from __future__ import annotations

import math

from mtee.domain.waveform import WaveformPoints

__all__ = ["WAVEFORM_DISPLAY_GAMMA", "bar_levels"]

# Chosen at the plan 100 mock-up review (initial value, may be adjusted).
WAVEFORM_DISPLAY_GAMMA = 1.6


def bar_levels(points: WaveformPoints, bar_count: int, gamma: float) -> list[float]:
    """Return one level in ``[0, 1]`` per bar; the loudest bar of the track is 1.

    When there are more bars than stored points, each point gets one bar and the list
    holds as many values as there are points. A silent track gives only zeros.
    """
    if bar_count < 1:
        raise ValueError("bar_count must be at least 1")
    if gamma <= 0:
        raise ValueError("gamma must be positive")
    count = len(points)
    bars = min(bar_count, count)
    energies: list[float] = []
    for index in range(bars):
        start = index * count // bars
        end = max(start + 1, (index + 1) * count // bars)
        window = points.rms[start:end]
        energies.append(math.sqrt(sum(value * value for value in window) / len(window)))
    loudest = max(energies)
    if loudest <= 0:
        return [0.0] * bars
    return [min(1.0, max(0.0, (energy / loudest) ** gamma)) for energy in energies]
