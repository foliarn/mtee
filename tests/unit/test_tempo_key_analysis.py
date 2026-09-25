from __future__ import annotations

import uuid
from pathlib import Path

from tests.helpers.analysis_audio import write_music_fixture

from mtee.domain.analysis import AnalysisSpec, AnalysisStatus
from mtee.domain.conversion import ConversionSource
from mtee.domain.tracks import SourceRevision
from mtee.services.analyzers.base import AnalyzerContext
from mtee.services.analyzers.key import KeyAnalyzer
from mtee.services.analyzers.tempo import TempoAnalyzer
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.media_decode_service import MediaDecodeService


def test_segmented_estimators_keep_half_double_options_and_annotate_key(tmp_path: Path) -> None:
    path = tmp_path / "C major pulse.wav"
    write_music_fixture(path)
    source = ConversionSource(str(uuid.uuid4()), path, SourceRevision.observe(path))
    decoder = MediaDecodeService(FileAccessCoordinator())
    context = AnalyzerContext("run", lambda: False, lambda _: None)

    tempo = TempoAnalyzer(decoder).analyze(source, AnalysisSpec("tempo"), context)
    key = KeyAnalyzer(decoder).analyze(source, AnalysisSpec("key"), context)
    tempo_metrics = {metric.name: metric.value for metric in tempo.metrics}
    key_metrics = {metric.name: metric.value for metric in key.metrics}
    tempo_bpm = tempo_metrics["tempo_bpm"]
    tempo_half_bpm = tempo_metrics["tempo_half_bpm"]
    tempo_double_bpm = tempo_metrics["tempo_double_bpm"]

    assert tempo.status in {AnalysisStatus.AVAILABLE, AnalysisStatus.UNCERTAIN}
    assert isinstance(tempo_bpm, (int, float))
    assert isinstance(tempo_half_bpm, (int, float))
    assert isinstance(tempo_double_bpm, (int, float))
    bpm = tempo_bpm
    assert abs(bpm - 120) < 12
    assert tempo_half_bpm == bpm / 2
    assert tempo_double_bpm == bpm * 2
    assert key.status in {AnalysisStatus.AVAILABLE, AnalysisStatus.UNCERTAIN}
    assert key_metrics["key"] == "C major"
    assert "profile_source" in key.config
