from __future__ import annotations

import uuid
from pathlib import Path

from tests.helpers.analysis_audio import write_sine_fixture

from mtee.domain.analysis import AnalysisSpec
from mtee.domain.conversion import ConversionSource
from mtee.domain.tracks import SourceRevision
from mtee.services.analyzers.base import AnalyzerContext
from mtee.services.analyzers.loudness import LoudnessAnalyzer
from mtee.services.ffmpeg_runtime import FfmpegRuntime


def test_ebur128_reports_integrated_loudness_and_distinct_peak_units(tmp_path: Path) -> None:
    path = tmp_path / "known-amplitude.wav"
    write_sine_fixture(path)
    source = ConversionSource(str(uuid.uuid4()), path, SourceRevision.observe(path))
    result = LoudnessAnalyzer(FfmpegRuntime()).analyze(
        source, AnalysisSpec("loudness"), AnalyzerContext("run", lambda: False, lambda _: None)
    )
    metrics = {metric.name: metric for metric in result.metrics}
    sample_peak = metrics["sample_peak"].value

    assert metrics["integrated_loudness"].value is not None
    assert isinstance(sample_peak, (int, float))
    assert metrics["integrated_loudness"].unit == "LUFS"
    assert abs(sample_peak + 6.02) < 0.1
    assert metrics["sample_peak"].unit == "dBFS"
    assert metrics["true_peak"].unit == "dBTP"
    assert metrics["true_peak"].value is not None
    assert metrics["loudness_range"].unit == "LU"
