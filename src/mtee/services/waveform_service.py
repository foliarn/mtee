"""Build bounded min/max waveform pyramids through the shared PCM decoder."""

from __future__ import annotations

import sys
from array import array
from collections.abc import Callable

from mtee.domain.conversion import ConversionSource
from mtee.domain.jobs import JobCancelledError
from mtee.domain.tracks import SourceRevision
from mtee.domain.tracks import TrackId
from mtee.domain.waveform import WaveformConfig, WaveformData, WaveformLevel
from mtee.services.media_decode_service import MediaDecodeService
from mtee.services.media_probe import MediaProbeService
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.waveform_cache import WaveformCache

__all__ = ["WaveformService"]


class WaveformService:
    def __init__(
        self,
        decoder: MediaDecodeService,
        cache: WaveformCache,
        probe: MediaProbeService,
        file_access: FileAccessCoordinator,
    ) -> None:
        self._decoder = decoder
        self._cache = cache
        self._probe = probe
        self._file_access = file_access

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
        try:
            self._cache.invalidate(source.track_id, revision)
        except OSError:
            pass
        with self._file_access.acquire_read(
            TrackId.parse(source.track_id), "waveform generation", timeout_seconds=0
        ):
            return self._generate_locked(
                source,
                revision,
                config,
                is_cancelled=is_cancelled,
                report_progress=report_progress,
            )

    def _generate_locked(
        self,
        source: ConversionSource,
        revision: SourceRevision,
        config: WaveformConfig,
        *,
        is_cancelled: Callable[[], bool],
        report_progress: Callable[[float], None],
    ) -> WaveformData:
        observed = SourceRevision.observe(source.path, generation=revision.generation)
        if revision.looks_modified(observed):
            raise ValueError("The source changed before waveform generation started.")
        probe = self._probe.inspect(source.path)
        expected_frames = (
            max(1, round(probe.duration_us * config.sample_rate / 1_000_000))
            if probe.duration_us
            else None
        )
        channels = config.channels
        frame_bytes = channels * 2
        frames_per_bin = max(1, round(config.sample_rate * config.bin_ms / 1000))
        current_count = 0
        minima = [32767] * channels
        maxima = [-32768] * channels
        base_values: list[int] = []
        frames_seen = 0
        carry = b""

        for block in self._decoder.stream_pcm(
            source,
            sample_rate=config.sample_rate,
            channels=channels,
            read_lease_held=True,
            is_cancelled=is_cancelled,
        ):
            if is_cancelled():
                raise JobCancelledError("waveform generation cancelled")
            combined = carry + block
            aligned_bytes = len(combined) - len(combined) % frame_bytes
            carry = combined[aligned_bytes:]
            pcm = array("h")
            pcm.frombytes(combined[:aligned_bytes])
            if sys.byteorder != "little":
                pcm.byteswap()
            total_frames = len(pcm) // channels
            frame_index = 0
            while frame_index < total_frames:
                take = min(frames_per_bin - current_count, total_frames - frame_index)
                first_sample = frame_index * channels
                end_sample = (frame_index + take) * channels
                for channel in range(channels):
                    values = pcm[first_sample + channel : end_sample : channels]
                    if values:
                        minima[channel] = min(minima[channel], min(values))
                        maxima[channel] = max(maxima[channel], max(values))
                current_count += take
                frames_seen += take
                frame_index += take
                if current_count == frames_per_bin:
                    for channel in range(channels):
                        base_values.extend((minima[channel], maxima[channel]))
                    current_count = 0
                    minima = [32767] * channels
                    maxima = [-32768] * channels
            if expected_frames:
                report_progress(min(0.99, frames_seen / expected_frames))

        if current_count:
            for channel in range(channels):
                base_values.extend((minima[channel], maxima[channel]))
        if not base_values or frames_seen < 1:
            raise ValueError("No decodable audio frames were found for the waveform.")
        levels = [_level_from_values(base_values, channels)]
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
        try:
            self._cache.store(data)
        except (OSError, ValueError):
            pass
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
