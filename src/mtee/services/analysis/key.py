"""Key estimation from a pitch-class profile.

The extractor accumulates a 36-bin profile (thirds of a semitone, ``A`` first).
The bins are grouped into twelve pitch classes around the tuning that carries the
most energy, so a recording tuned a few cents away from A = 440 Hz still lands on
the right classes. The resulting chroma is correlated with the 24 rotations of
two published major/minor key profiles; the best correlation names the key.

Profiles: Krumhansl and Kessler (1982) and Temperley (2005), values as printed in
the literature. Their average is used because each errs on different relative
major/minor pairs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from mtee.domain.musical_key import MusicalKey

__all__ = ["KeyEstimate", "estimate_key"]

_MAJOR_PROFILES = (
    np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]),
    np.array([5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0]),
)
_MINOR_PROFILES = (
    np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]),
    np.array([5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0]),
)
_MIN_CORRELATION = 0.45
_MIN_ENERGY = 1.0


@dataclass(frozen=True, slots=True)
class KeyEstimate:
    """A key with the correlation of its profile and its lead over the next key."""

    key: MusicalKey
    correlation: float
    margin: float


def estimate_key(pitch_profile: np.ndarray) -> KeyEstimate | None:
    """Return the key of a 36-bin pitch profile, or ``None`` without tonal evidence."""
    profile = np.asarray(pitch_profile, dtype=np.float64)
    if profile.shape != (36,) or not np.isfinite(profile).all():
        return None
    if profile.sum() < _MIN_ENERGY:
        return None
    chroma = _chroma(profile)
    if chroma.std() < 1e-9:
        return None

    correlations: list[tuple[float, MusicalKey]] = []
    for tonic in range(12):
        for minor, profiles in ((False, _MAJOR_PROFILES), (True, _MINOR_PROFILES)):
            score = float(
                np.mean([_correlation(chroma, np.roll(item, tonic)) for item in profiles])
            )
            correlations.append((score, MusicalKey(tonic, minor)))
    correlations.sort(key=lambda item: item[0], reverse=True)
    best_score, best_key = correlations[0]
    if not math.isfinite(best_score) or best_score < _MIN_CORRELATION:
        return None
    return KeyEstimate(best_key, best_score, best_score - correlations[1][0])


def _chroma(profile: np.ndarray) -> np.ndarray:
    """Fold the 36-bin profile into twelve pitch classes starting at C."""
    per_offset = profile.reshape(12, 3).sum(axis=0)
    centre = int(np.argmax(per_offset))
    if centre == 2:
        centre = -1  # notes sitting a third of a semitone below their pitch class
    grouped = np.zeros(12)
    for pitch_class in range(12):
        for delta in (-1, 0, 1):
            grouped[pitch_class] += profile[(3 * pitch_class + centre + delta) % 36]
    # ``grouped`` starts at A; the key profiles start at C, three semitones higher.
    return np.roll(grouped, -3)


def _correlation(first: np.ndarray, second: np.ndarray) -> float:
    first_centered = first - first.mean()
    second_centered = second - second.mean()
    denominator = np.linalg.norm(first_centered) * np.linalg.norm(second_centered)
    return float(first_centered @ second_centered / denominator) if denominator > 0 else 0.0
