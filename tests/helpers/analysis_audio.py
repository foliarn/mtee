"""Reproducible, locally generated signals with known silent and musical regions."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def write_music_fixture(
    path: Path, *, duration_seconds: int = 14, sample_rate: int = 22_050
) -> None:
    time = np.arange(duration_seconds * sample_rate, dtype=np.float64) / sample_rate
    edge = 1.0
    active = (time >= edge) & (time < duration_seconds - edge)
    signal = np.zeros_like(time)
    signal[active] = (
        0.12 * np.sin(2 * np.pi * 261.6256 * time[active])
        + 0.10 * np.sin(2 * np.pi * 329.6276 * time[active])
        + 0.09 * np.sin(2 * np.pi * 391.9954 * time[active])
    )
    for beat in np.arange(edge, duration_seconds - edge, 0.5):
        click = (time >= beat) & (time < beat + 0.025)
        signal[click] += 0.32 * np.sin(2 * np.pi * 1_000 * time[click])
    write_wav(path, np.clip(signal, -0.95, 0.95), sample_rate)


def write_sine_fixture(
    path: Path, *, seconds: int = 8, amplitude: float = 0.5, sample_rate: int = 48_000
) -> None:
    time = np.arange(seconds * sample_rate, dtype=np.float64) / sample_rate
    write_wav(path, amplitude * np.sin(2 * np.pi * 1_000 * time), sample_rate)


def write_wav(path: Path, signal: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.asarray(np.clip(signal, -1, 1) * 32767, dtype="<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(samples.tobytes())
