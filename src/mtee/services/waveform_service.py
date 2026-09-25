"""Build bounded min/max waveform pyramids through the shared PCM decoder."""

from __future__ import annotations

import struct
from collections.abc import Callable

from mtee.domain.conversion import ConversionSource
from mtee.domain.jobs import JobCancelledError
from mtee.domain.tracks import SourceRevision
from mtee.domain.waveform import WaveformConfig, WaveformData, WaveformLevel
from mtee.services.media_decode_service import MediaDecodeService
from mtee.services.media_probe import MediaProbeService
from mtee.services.waveform_cache import WaveformCache

__all__ = ["WaveformService"]


class WaveformService:
    def __init__(
        self, decoder: MediaDecodeService, cache: WaveformCache, probe: MediaProbeService
    ) -> None:
        self._decoder = decoder
        self._cache = cache
        self._probe = probe

    def request(
        self,
        source: ConversionSource,
        revision: SourceRevision,
        config: WaveformConfig | None = None,
        *,
        is_cancelled: Callable[[], bool] = lambda: False,
        report_progress: Callable[[float], None] = lambda _value: None,
    ) -> WaveformData:
        config = config or WaveformConfig()
        observed = SourceRevision.observe(source.path, generation=revision.generation)
        if revision.looks_modified(observed):
            raise ValueError("The source changed before waveform generation started.")
        cached = self._cache.load(source.track_id, revision, config)
        if cached is not None:
            return cached
        self._cache.invalidate(source.track_id, revision)
        probe = self._probe.inspect(source.path)
        expected_frames = (
            max(1, round(probe.duration_us * config.sample_rate / 1_000_000))
            if probe.duration_us
            else None
        )
        frames_per_bin = max(1, round(config.sample_rate * config.bin_ms / 1000))
        frame_bytes = config.channels * 2
        current_count = 0
        minima = [32767] * config.channels
        maxima = [-32768] * config.channels
        base_values: list[int] = []
        frames_seen = 0
        for block in self._decoder.stream_pcm(
            source,
            sample_rate=config.sample_rate,
            channels=config.channels,
            is_cancelled=is_cancelled,
        ):
            if is_cancelled():
                raise JobCancelledError("waveform generation cancelled")
            for frame in struct.iter_unpack("<" + "h" * config.channels, block):
                for channel, sample in enumerate(frame):
                    minima[channel] = min(minima[channel], sample)
                    maxima[channel] = max(maxima[channel], sample)
                current_count += 1
                frames_seen += 1
                if current_count >= frames_per_bin:
                    for channel in range(config.channels):
                        base_values.extend((minima[channel], maxima[channel]))
                    current_count = 0
                    minima = [32767] * config.channels
                    maxima = [-32768] * config.channels
            if expected_frames:
                report_progress(min(0.99, frames_seen / expected_frames))
        if current_count:
            for channel in range(config.channels):
                base_values.extend((minima[channel], maxima[channel]))
        if not base_values or frames_seen * frame_bytes < 1:
            raise ValueError("No decodable audio frames were found for the waveform.")
        levels = [_level_from_values(base_values, config.channels)]
        while levels[-1].bin_count > 1:
            levels.append(_reduce_level(levels[-1]))
            if is_cancelled():
                raise JobCancelledError("waveform generation cancelled")
        observed_after = SourceRevision.observe(source.path, generation=revision.generation)
        if revision.looks_modified(observed_after):
            raise ValueError("The source changed while its waveform was being generated.")
        data = WaveformData(
            source.track_id,
            revision,
            config,
            round(frames_seen * 1_000_000 / config.sample_rate),
            tuple(levels),
        )
        self._cache.store(data)
        report_progress(1.0)
        return data


def _level_from_values(values: list[int], channels: int) -> WaveformLevel:
    return WaveformLevel(len(values) // (channels * 2), channels, tuple(values))


def _reduce_level(level: WaveformLevel) -> WaveformLevel:
    values: list[int] = []
    for first in range(0, level.bin_count, 2):
        second = min(first + 1, level.bin_count - 1)
        for channel in range(level.channels):
            values.extend(
                (
                    min(level.bin(first, channel)[0], level.bin(second, channel)[0]),
                    max(level.bin(first, channel)[1], level.bin(second, channel)[1]),
                )
            )
    return _level_from_values(values, level.channels)
