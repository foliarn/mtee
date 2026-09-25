"""Versioned waveform contracts for bounded amplitude previews."""

from __future__ import annotations

from dataclasses import dataclass

from mtee.domain.tracks import SourceRevision

__all__ = ["WAVEFORM_ALGORITHM_VERSION", "WaveformConfig", "WaveformData", "WaveformLevel"]

WAVEFORM_ALGORITHM_VERSION = 1


@dataclass(frozen=True, slots=True)
class WaveformConfig:
    sample_rate: int = 22_050
    channels: int = 2
    bin_ms: int = 20
    algorithm_version: int = WAVEFORM_ALGORITHM_VERSION

    def __post_init__(self) -> None:
        if not 8_000 <= self.sample_rate <= 192_000:
            raise ValueError("sample_rate must be between 8000 and 192000 Hz")
        if self.channels not in {1, 2}:
            raise ValueError("channels must be mono or stereo")
        if not 5 <= self.bin_ms <= 100:
            raise ValueError("bin_ms must be between 5 and 100")
        if self.algorithm_version < 1:
            raise ValueError("algorithm_version must be positive")


@dataclass(frozen=True, slots=True)
class WaveformLevel:
    """Interleaved signed 16-bit minimum/maximum values, two per channel/bin."""

    bin_count: int
    channels: int
    values: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.bin_count < 1 or self.channels not in {1, 2}:
            raise ValueError("waveform level dimensions must be positive")
        if len(self.values) != self.bin_count * self.channels * 2:
            raise ValueError("waveform level value count does not match its dimensions")
        if any(value < -32768 or value > 32767 for value in self.values):
            raise ValueError("waveform values must fit signed 16-bit PCM")

    def bin(self, index: int, channel: int = 0) -> tuple[int, int]:
        if not 0 <= index < self.bin_count or not 0 <= channel < self.channels:
            raise IndexError("waveform bin or channel is outside the level")
        offset = (index * self.channels + channel) * 2
        return self.values[offset], self.values[offset + 1]


@dataclass(frozen=True, slots=True)
class WaveformData:
    track_id: str
    source_revision: SourceRevision
    config: WaveformConfig
    duration_us: int
    levels: tuple[WaveformLevel, ...]

    def __post_init__(self) -> None:
        if not self.track_id:
            raise ValueError("track_id is required")
        if self.duration_us <= 0 or not self.levels:
            raise ValueError("a waveform must have positive duration and at least one level")
        previous = self.levels[0].bin_count
        for level in self.levels:
            if level.channels != self.config.channels or level.bin_count > previous:
                raise ValueError("waveform levels must use the configured channels and descend")
            previous = level.bin_count

    @property
    def base(self) -> WaveformLevel:
        return self.levels[0]
