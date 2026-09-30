"""Analysis settings and the stored result of a track.

Calculated values (tempo, key, waveform) are kept apart from the tags written in
the file. A value the user edited is flagged, and the flag protects it from any
later analysis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from mtee.domain.musical_key import KEY_NOTATIONS, MusicalKey

__all__ = [
    "ANALYSIS_ALGORITHM_VERSION",
    "BPM_LIMITS",
    "DECIMAL_LIMITS",
    "DURATION_TOLERANCE_US",
    "PARALLEL_LIMITS",
    "WAVEFORM_ALGORITHM_VERSION",
    "AnalysisSettings",
    "TrackAnalysis",
    "durations_agree",
    "format_bpm",
]

# Raise when the tempo or key method changes in a way that alters results: stored
# results of an older version are analyzed again by Analyze.
# Version 2: key from weighted peaks, harmonic support and the bass line.
ANALYSIS_ALGORITHM_VERSION = 2
# The stored waveform has its own version, so a better key does not throw it away.
WAVEFORM_ALGORITHM_VERSION = 1
# A stored result stays valid while the audio length agrees within this tolerance:
# a tag edit changes the file bytes but not the audio, a replaced file does.
DURATION_TOLERANCE_US = 1_000_000

BPM_LIMITS = (40, 300)
PARALLEL_LIMITS = (1, 8)
DECIMAL_LIMITS = (0, 2)


@dataclass(frozen=True, slots=True)
class AnalysisSettings:
    """User choices of the Analysis settings tab."""

    notation: str = "camelot"
    bpm_min: int = 70
    bpm_max: int = 180
    parallel_jobs: int = 1
    bpm_decimals: int = 2
    write_tags: bool = False

    def normalized(self) -> AnalysisSettings:
        """Return these settings with every value brought inside its valid range."""
        notation = self.notation if self.notation in KEY_NOTATIONS else "camelot"
        low = min(max(int(self.bpm_min), BPM_LIMITS[0]), BPM_LIMITS[1] // 2)
        high = min(max(int(self.bpm_max), 2 * low), BPM_LIMITS[1])
        return replace(
            self,
            notation=notation,
            bpm_min=low,
            bpm_max=high,
            parallel_jobs=min(max(int(self.parallel_jobs), PARALLEL_LIMITS[0]), PARALLEL_LIMITS[1]),
            bpm_decimals=min(max(int(self.bpm_decimals), DECIMAL_LIMITS[0]), DECIMAL_LIMITS[1]),
            write_tags=bool(self.write_tags),
        )


@dataclass(frozen=True, slots=True)
class TrackAnalysis:
    """What is stored for one track: calculated values and edit flags."""

    track_id: str
    bpm: float | None = None
    key: MusicalKey | None = None
    bpm_user_edited: bool = False
    key_user_edited: bool = False
    source_duration_us: int | None = None
    algorithm_version: int | None = None
    analyzed_at_utc: str | None = None

    @property
    def analyzed(self) -> bool:
        return self.analyzed_at_utc is not None


def durations_agree(stored_us: int | None, current_us: int | None) -> bool:
    """Return whether a result computed for ``stored_us`` still fits ``current_us``."""
    if not stored_us or not current_us:
        return True
    return abs(stored_us - current_us) <= DURATION_TOLERANCE_US


def format_bpm(bpm: float | int | str, decimals: int) -> str:
    """Return ``bpm`` with exactly ``decimals`` decimals; a non-number is unchanged."""
    try:
        number = float(bpm)
    except (TypeError, ValueError):
        return str(bpm)
    if not math.isfinite(number):
        return str(bpm)
    return f"{number:.{max(0, decimals)}f}"
