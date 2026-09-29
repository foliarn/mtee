"""Reproducible synthetic signals with a known tempo and a known key.

The drum loops place their hits on an exact grid (optionally swung), so a test can
assert the tempo to a fraction of a beat per minute. Nothing here is a claim about
real music: it proves the arithmetic of the analysis, not its musical accuracy.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 22_050

# One bar of sixteen steps per pattern: kick, snare/clap, hat.
PATTERNS: dict[str, dict[str, tuple[int, ...]]] = {
    "house": {"kick": (0, 4, 8, 12), "snare": (4, 12), "hat": (2, 6, 10, 14)},
    "garage": {"kick": (0, 10), "snare": (4, 12), "hat": (0, 2, 4, 6, 8, 10, 12, 14)},
    "dnb": {"kick": (0, 10), "snare": (4, 12), "hat": (0, 2, 4, 6, 8, 10, 12, 14)},
    "hiphop": {"kick": (0, 7, 10), "snare": (4, 12), "hat": (0, 2, 4, 6, 8, 10, 12, 14)},
}


def _kick(rate: int) -> np.ndarray:
    time = np.arange(int(0.22 * rate)) / rate
    frequency = 45.0 + 105.0 * np.exp(-time * 38.0)
    phase = 2 * np.pi * np.cumsum(frequency) / rate
    return (0.9 * np.sin(phase) * np.exp(-time * 16.0)).astype(np.float32)


def _snare(rate: int, generator: np.random.Generator) -> np.ndarray:
    time = np.arange(int(0.18 * rate)) / rate
    noise = np.diff(generator.standard_normal(time.size + 1))
    tone = np.sin(2 * np.pi * 190.0 * time)
    return (0.45 * (0.7 * noise * 0.5 + 0.5 * tone) * np.exp(-time * 24.0)).astype(np.float32)


def _hat(rate: int, generator: np.random.Generator) -> np.ndarray:
    time = np.arange(int(0.05 * rate)) / rate
    noise = np.diff(generator.standard_normal(time.size + 1))
    return (0.16 * noise * np.exp(-time * 90.0)).astype(np.float32)


def drum_loop(
    bpm: float,
    seconds: float,
    *,
    pattern: str = "house",
    swing: float = 0.0,
    rate: int = SAMPLE_RATE,
    seed: int = 7,
    intro_seconds: float = 0.0,
) -> np.ndarray:
    """Return a mono float32 drum loop whose steps follow ``bpm`` exactly."""
    generator = np.random.default_rng(seed)
    hits = {
        "kick": _kick(rate),
        "snare": _snare(rate, generator),
        "hat": _hat(rate, generator),
    }
    total = int((seconds + 1.0) * rate)
    signal = np.zeros(total, dtype=np.float32)
    step_seconds = 60.0 / bpm / 4.0
    steps = int(seconds / step_seconds)
    layout = PATTERNS[pattern]
    for step in range(steps):
        position = step % 16
        moment = intro_seconds + step * step_seconds
        if step % 2 == 1:
            moment += swing * step_seconds
        start = round(moment * rate)
        for name, hit in hits.items():
            if position in layout[name] and start < total:
                end = min(total, start + hit.size)
                signal[start:end] += hit[: end - start]
    return np.clip(signal[: int(seconds * rate)], -1.0, 1.0)


_TRIADS = {False: (0, 4, 7), True: (0, 3, 7)}


def chord(
    tonic: int, minor: bool, seconds: float, *, octave: int = 3, rate: int = SAMPLE_RATE
) -> np.ndarray:
    """Return a sustained triad with a few harmonics, rooted on ``tonic``."""
    time = np.arange(int(seconds * rate)) / rate
    signal = np.zeros(time.size, dtype=np.float64)
    root = 440.0 * 2.0 ** ((tonic - 9) / 12.0 + (octave - 4))
    for interval in _TRIADS[minor]:
        base = root * 2.0 ** (interval / 12.0)
        for harmonic, weight in enumerate((1.0, 0.5, 0.33, 0.25), start=1):
            signal += weight * np.sin(2 * np.pi * base * harmonic * time)
    fade = np.minimum(1.0, np.minimum(time, time[-1] - time) / 0.03)
    return (signal * fade / 6.0).astype(np.float32)


def key_progression(
    tonic: int, minor: bool, seconds: float, *, rate: int = SAMPLE_RATE
) -> np.ndarray:
    """Return I - IV - V - I chords (or i - iv - v - i) in the requested key."""
    scale = (0, 5, 7, 0)
    length = seconds / len(scale)
    return np.concatenate(
        [chord((tonic + degree) % 12, minor, length, rate=rate) for degree in scale]
    )


def to_stereo_pcm(mono: np.ndarray) -> bytes:
    """Return interleaved 16-bit little-endian stereo PCM for ``mono``."""
    samples = np.asarray(np.clip(mono, -1.0, 1.0) * 32767, dtype="<i2")
    return np.repeat(samples[:, None], 2, axis=1).tobytes()


def write_wav(path: Path, signal: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.asarray(np.clip(signal, -1, 1) * 32767, dtype="<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(samples.tobytes())
