"""Loudness measured by Analyze, and the playback gain that brings a track to a target.

The gain is computed from the integrated loudness and the sample peak stored by Analyze.
The player applies it; the audio file is never changed and no limiter is involved. A
positive gain is only allowed as far as the sample peak stays under the ceiling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

__all__ = [
    "DEFAULT_NORMALIZATION_LEVEL",
    "GAIN_LIMITS_DB",
    "NORMALIZATION_LEVELS",
    "PEAK_CEILING_DBFS",
    "LoudnessResult",
    "NormalizationSettings",
    "playback_gain_db",
]

# Integrated loudness targets in LUFS, by the name the settings store.
NORMALIZATION_LEVELS: dict[str, float] = {"quiet": -23.0, "normal": -14.0, "loud": -11.0}
DEFAULT_NORMALIZATION_LEVEL = "normal"
# A boost never takes the sample peak above this level.
PEAK_CEILING_DBFS = -1.0
# The range accepted by the native player for its gain property (libmpv defaults are
# -96 and +12 dB; the backend raises the upper bound to this value).
GAIN_LIMITS_DB = (-96.0, 40.0)


@dataclass(frozen=True, slots=True)
class LoudnessResult:
    """Integrated loudness (LUFS) and sample peak (dBFS) of a track.

    A value is ``None`` when the audio has none to give: a track shorter than 400 ms, or a
    track whose blocks are all below the absolute gate (silence).
    """

    integrated_lufs: float | None
    sample_peak_dbfs: float | None


@dataclass(frozen=True, slots=True)
class NormalizationSettings:
    """Playback normalization choices: on or off, and the loudness target."""

    enabled: bool = True
    level: str = DEFAULT_NORMALIZATION_LEVEL

    @property
    def target_lufs(self) -> float:
        return NORMALIZATION_LEVELS[self.level]

    def normalized(self) -> NormalizationSettings:
        """Return these settings with an unknown level replaced by the default."""
        level = self.level if self.level in NORMALIZATION_LEVELS else DEFAULT_NORMALIZATION_LEVEL
        return replace(self, enabled=bool(self.enabled), level=level)


def playback_gain_db(
    integrated_lufs: float | None,
    sample_peak_dbfs: float | None,
    settings: NormalizationSettings,
) -> float:
    """Return the gain in dB to apply to a track before it is heard.

    ``target - integrated``, except that a positive gain stops where the sample peak
    would reach the ceiling. A track without a measured loudness plays with 0 dB, and so
    does a track whose boost cannot be checked against its peak. A negative gain never
    depends on the peak: it only lowers the level.
    """
    if not settings.enabled or integrated_lufs is None or not math.isfinite(integrated_lufs):
        return 0.0
    gain = settings.target_lufs - float(integrated_lufs)
    if gain > 0:
        if sample_peak_dbfs is None or not math.isfinite(sample_peak_dbfs):
            return 0.0
        gain = min(gain, max(0.0, PEAK_CEILING_DBFS - float(sample_peak_dbfs)))
    low, high = GAIN_LIMITS_DB
    return min(max(gain, low), high)
