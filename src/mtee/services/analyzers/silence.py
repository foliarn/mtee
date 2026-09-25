"""Silence intervals from FFmpeg silencedetect with explicit timing rules."""

from __future__ import annotations

import re

from mtee.domain.analysis import (
    AnalysisMetric,
    AnalysisResult,
    AnalysisSpec,
    AnalysisStatus,
    new_analysis_id,
)
from mtee.domain.conversion import ConversionSource
from mtee.domain.tracks import SourceRevision
from mtee.services.analyzers.base import AnalyzerContext
from mtee.services.analyzers.ffmpeg import run_filter
from mtee.services.ffmpeg_runtime import FfmpegRuntime
from mtee.services.media_probe import MediaProbeService

_START = re.compile(r"silence_start:\s*([0-9.]+)")
_END = re.compile(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)")


class SilenceAnalyzer:
    name = "silence"
    version = "ffmpeg-silencedetect-v1"

    def __init__(self, runtime: FfmpegRuntime, probe: MediaProbeService) -> None:
        self._runtime = runtime
        self._probe = probe

    def analyze(
        self, source: ConversionSource, spec: AnalysisSpec, context: AnalyzerContext
    ) -> AnalysisResult:
        threshold_db = float(spec.config.get("threshold_db", -60.0))
        minimum_seconds = float(spec.config.get("minimum_seconds", 0.5))
        if not -120 <= threshold_db <= 0 or minimum_seconds <= 0:
            raise ValueError("Silence threshold or minimum duration is outside its valid range.")
        context.raise_if_cancelled()
        log = run_filter(
            self._runtime,
            [
                "-hide_banner",
                "-nostdin",
                "-v",
                "info",
                "-i",
                str(source.path),
                "-map",
                "0:a:0",
                "-af",
                f"silencedetect=noise={threshold_db}dB:d={minimum_seconds}",
                "-f",
                "null",
                "-",
            ],
            context.is_cancelled,
        )
        duration_us = self._probe.inspect(source.path).duration_us
        segments: list[dict[str, int]] = []
        pending_start: int | None = None
        for line in log.splitlines():
            if match := _START.search(line):
                pending_start = round(float(match.group(1)) * 1_000_000)
            elif match := _END.search(line):
                end_us = round(float(match.group(1)) * 1_000_000)
                if pending_start is None:
                    pending_start = max(0, end_us - round(float(match.group(2)) * 1_000_000))
                segments.append({"start_us": pending_start, "end_us": end_us})
                pending_start = None
        if pending_start is not None and duration_us is not None and duration_us >= pending_start:
            segments.append({"start_us": pending_start, "end_us": duration_us})
        if (
            duration_us is not None
            and not segments
            and duration_us / 1_000_000 >= minimum_seconds
            and "silence_start: 0" in log
        ):
            segments.append({"start_us": 0, "end_us": duration_us})
        observed = SourceRevision.observe(source.path, generation=source.revision.generation)
        if source.revision.looks_modified(observed):
            raise ValueError("The source changed during silence analysis.")
        silence_us = sum(item["end_us"] - item["start_us"] for item in segments)
        context.report_progress(1.0)
        return AnalysisResult(
            new_analysis_id(),
            context.run_id,
            source.track_id,
            self.name,
            self.version,
            source.revision,
            {
                "threshold_db": threshold_db,
                "minimum_seconds": minimum_seconds,
                "channel_mode": "FFmpeg default combined channel evaluation",
            },
            AnalysisStatus.AVAILABLE,
            (
                AnalysisMetric("silence_count", len(segments), "intervals"),
                AnalysisMetric("silence_duration", silence_us, "µs"),
            ),
            tuple(segments),
        )
