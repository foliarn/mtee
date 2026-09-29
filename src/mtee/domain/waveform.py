"""Stored waveform: a fixed number of min/max amplitude points per track.

The waveform is computed once, kept permanently and drawn as is. Its resolution
does not depend on the length of the track, which keeps the size of a stored
waveform constant (a few kilobytes) and its display predictable.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

__all__ = ["WAVEFORM_POINTS", "WaveformPoints"]

WAVEFORM_POINTS = 1200
_POINT = struct.Struct("<hh")


@dataclass(frozen=True, slots=True)
class WaveformPoints:
    """Minimum and maximum sample of each slice of the track, signed 16-bit."""

    duration_us: int
    lows: tuple[int, ...]
    highs: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.duration_us <= 0:
            raise ValueError("a waveform needs a positive duration")
        if not self.lows or len(self.lows) != len(self.highs):
            raise ValueError("a waveform needs as many minima as maxima, and at least one")
        if any(not -32768 <= value <= 32767 for value in (*self.lows, *self.highs)):
            raise ValueError("waveform values must fit signed 16-bit PCM")

    def __len__(self) -> int:
        return len(self.lows)

    def to_bytes(self) -> bytes:
        return b"".join(
            _POINT.pack(low, high) for low, high in zip(self.lows, self.highs, strict=True)
        )

    @classmethod
    def from_bytes(cls, duration_us: int, payload: bytes) -> WaveformPoints:
        if not payload or len(payload) % _POINT.size:
            raise ValueError("the stored waveform has an invalid size")
        pairs = [
            _POINT.unpack_from(payload, offset) for offset in range(0, len(payload), _POINT.size)
        ]
        return cls(duration_us, tuple(pair[0] for pair in pairs), tuple(pair[1] for pair in pairs))

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
