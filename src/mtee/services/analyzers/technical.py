"""Read stream facts reported by the bundled ffprobe executable."""

from __future__ import annotations

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
from mtee.services.media_probe import MediaProbeService


class TechnicalAnalyzer:
    name = "technical"
    version = "ffprobe-v1"

    def __init__(self, probe: MediaProbeService) -> None:
        self._probe = probe

    def analyze(
        self, source: ConversionSource, spec: AnalysisSpec, context: AnalyzerContext
    ) -> AnalysisResult:
        context.report_progress(0.1)
        context.raise_if_cancelled()
        media = self._probe.inspect(source.path)
        observed = SourceRevision.observe(source.path, generation=source.revision.generation)
        if source.revision.looks_modified(observed):
            raise ValueError("The source changed during technical inspection.")
        context.report_progress(1.0)
        metrics = (
            AnalysisMetric("container", media.container),
            AnalysisMetric("codec", media.codec),
            AnalysisMetric("duration", media.duration_us, "µs"),
            AnalysisMetric("sample_rate", media.sample_rate, "Hz"),
            AnalysisMetric("channels", media.channels, "channels"),
            AnalysisMetric("channel_layout", media.channel_layout),
            AnalysisMetric("bitrate", media.bitrate, "bit/s"),
            AnalysisMetric("bits_per_sample", media.bits_per_sample, "bits/sample"),
        )
        return AnalysisResult(
            new_analysis_id(),
            context.run_id,
            source.track_id,
            self.name,
            self.version,
            source.revision,
            dict(spec.config),
            AnalysisStatus.AVAILABLE,
            metrics,
        )
