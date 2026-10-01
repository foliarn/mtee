"""Stored waveform: a fixed number of min/max/RMS amplitude points per track.

The waveform is computed once, kept permanently and drawn as is. Its resolution
does not depend on the length of the track, which keeps the size of a stored
waveform constant (a few kilobytes) and its display predictable.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

__all__ = ["RMS_MAX", "WAVEFORM_POINTS", "WaveformPoints"]

WAVEFORM_POINTS = 1200
RMS_MAX = 32767
_POINT = struct.Struct("<hhH")


@dataclass(frozen=True, slots=True)
class WaveformPoints:
    """Minimum, maximum and RMS energy of each slice of the track.

    ``lows`` and ``highs`` are signed 16-bit samples; ``rms`` is the root mean square of
    the slice scaled to ``0..32767`` (full scale is 32767).
    """

    duration_us: int
    lows: tuple[int, ...]
    highs: tuple[int, ...]
    rms: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.duration_us <= 0:
            raise ValueError("a waveform needs a positive duration")
        if not self.lows or len(self.lows) != len(self.highs) or len(self.rms) != len(self.lows):
            raise ValueError("a waveform needs as many minima, maxima and RMS values, and one")
        if any(not -32768 <= value <= 32767 for value in (*self.lows, *self.highs)):
            raise ValueError("waveform values must fit signed 16-bit PCM")
        if any(not 0 <= value <= RMS_MAX for value in self.rms):
            raise ValueError("waveform RMS values must be between 0 and 32767")

    def __len__(self) -> int:
        return len(self.lows)

    def to_bytes(self) -> bytes:
        return b"".join(
            _POINT.pack(low, high, rms)
            for low, high, rms in zip(self.lows, self.highs, self.rms, strict=True)
        )

    @classmethod
    def from_bytes(cls, duration_us: int, payload: bytes) -> WaveformPoints:
        if not payload or len(payload) % _POINT.size:
            raise ValueError("the stored waveform has an invalid size")
        points = [
            _POINT.unpack_from(payload, offset) for offset in range(0, len(payload), _POINT.size)
        ]
        return cls(
            duration_us,
            tuple(point[0] for point in points),
            tuple(point[1] for point in points),
            tuple(point[2] for point in points),
        )

    def packed(self) -> bytes:
        """Return little-endian float32 ``(low, high)`` pairs scaled to ``[-1, 1]``.

        This is what the interface reads: one flat buffer that QML views as a typed
        array, instead of a nested list that it would copy for every element.
        """
        pairs = [
            value / 32768.0
            for low, high in zip(self.lows, self.highs, strict=True)
            for value in (low, high)
        ]
        return struct.pack(f"<{len(pairs)}f", *pairs)

    def samples(self) -> list[list[float]]:
        """Return ``[low, high]`` pairs scaled to ``[-1, 1]`` for the display."""
        return [
            [low / 32768.0, high / 32768.0] for low, high in zip(self.lows, self.highs, strict=True)
        ]
