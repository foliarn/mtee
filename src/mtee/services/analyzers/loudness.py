"""EBU R128 loudness and peak measurements through bundled FFmpeg."""

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

_NUMBER = r"(-?(?:\d+(?:\.\d+)?|inf|-inf))"
_I = re.compile(rf"^\s*I:\s*{_NUMBER}\s*LUFS", re.MULTILINE)
_LRA = re.compile(rf"^\s*LRA:\s*{_NUMBER}\s*LU", re.MULTILINE)
_SAMPLE_PEAK = re.compile(rf"Sample peak:\s*Peak:\s*{_NUMBER}\s*dBFS", re.MULTILINE)
_TRUE_PEAK = re.compile(rf"True peak:\s*Peak:\s*{_NUMBER}\s*dBFS", re.MULTILINE)


class LoudnessAnalyzer:
    name = "loudness"
    version = "ffmpeg-ebur128-v1"

    def __init__(self, runtime: FfmpegRuntime) -> None:
        self._runtime = runtime

    def analyze(
        self, source: ConversionSource, spec: AnalysisSpec, context: AnalyzerContext
    ) -> AnalysisResult:
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
                "ebur128=peak=true+sample:framelog=quiet",
                "-f",
                "null",
                "-",
            ],
            context.is_cancelled,
        )
        observed = SourceRevision.observe(source.path, generation=source.revision.generation)
        if source.revision.looks_modified(observed):
            raise ValueError("The source changed during loudness analysis.")
        metric_values: list[AnalysisMetric] = []
        if match := _I.search(log):
            value = _parse_float(match.group(1))
            metric_values.append(AnalysisMetric("integrated_loudness", value, "LUFS"))
        else:
            metric_values.append(AnalysisMetric("integrated_loudness", None, "LUFS"))
        if match := _LRA.search(log):
            metric_values.append(
                AnalysisMetric("loudness_range", _parse_float(match.group(1)), "LU")
            )
        else:
            metric_values.append(AnalysisMetric("loudness_range", None, "LU"))
        sample_peak = _SAMPLE_PEAK.search(log)
        true_peak = _TRUE_PEAK.search(log)
        metric_values.extend(
            (
                AnalysisMetric(
                    "sample_peak",
                    _parse_float(sample_peak.group(1)) if sample_peak else None,
                    "dBFS",
                ),
                AnalysisMetric(
                    "true_peak", _parse_float(true_peak.group(1)) if true_peak else None, "dBTP"
                ),
            )
        )
        no_loudness = metric_values[0].value is None
        context.report_progress(1.0)
        return AnalysisResult(
            new_analysis_id(),
            context.run_id,
            source.track_id,
            self.name,
            self.version,
            source.revision,
            {"filter": "ebur128", "peak": ["true", "sample"]},
            AnalysisStatus.NOT_APPLICABLE if no_loudness else AnalysisStatus.AVAILABLE,
            tuple(metric_values),
            diagnostics="Insufficient gated loudness energy." if no_loudness else "",
        )


def _parse_float(value: str) -> float | None:
    return None if value.casefold() in {"inf", "-inf"} else float(value)
