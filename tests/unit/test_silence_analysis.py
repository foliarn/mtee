from __future__ import annotations

import uuid
from pathlib import Path

from tests.helpers.analysis_audio import write_music_fixture

from mtee.domain.analysis import AnalysisSpec, AnalysisStatus
from mtee.domain.conversion import ConversionSource
from mtee.domain.tracks import SourceRevision
from mtee.services.analyzers.base import AnalyzerContext
from mtee.services.analyzers.silence import SilenceAnalyzer
from mtee.services.ffmpeg_runtime import FfmpegRuntime
from mtee.services.media_probe import MediaProbeService


def test_silence_intervals_match_synthetic_leading_and_trailing_silence(tmp_path: Path) -> None:
    source_path = tmp_path / "audio with spaces ' signal.wav"
    write_music_fixture(source_path)
    revision = SourceRevision.observe(source_path)
    source = ConversionSource(str(uuid.uuid4()), source_path, revision)
    result = SilenceAnalyzer(FfmpegRuntime(), MediaProbeService()).analyze(
        source, AnalysisSpec("silence"), AnalyzerContext("run", lambda: False, lambda _: None)
    )

    assert result.status is AnalysisStatus.AVAILABLE
    assert len(result.segments) == 2
    assert abs(result.segments[0]["start_us"] - 0) < 40_000
    assert abs(result.segments[0]["end_us"] - 1_000_000) < 40_000
    assert abs(result.segments[1]["start_us"] - 13_000_000) < 40_000
    assert abs(result.segments[1]["end_us"] - 14_000_000) < 40_000
