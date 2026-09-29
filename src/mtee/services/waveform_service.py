"""Waveform of a track: read the stored one, or compute it once and keep it."""

from __future__ import annotations

from collections.abc import Callable

from mtee.domain.conversion import ConversionSource
from mtee.domain.tracks import SourceRevision
from mtee.domain.waveform import WaveformPoints
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.services.audio_analyzer import AudioAnalyzer

__all__ = ["WaveformService"]


class WaveformService:
    def __init__(self, analyzer: AudioAnalyzer, repository: AnalysisRepository) -> None:
        self._analyzer = analyzer
        self._repository = repository

    def stored(self, track_id: str, current_duration_us: int | None) -> WaveformPoints | None:
        """Return the permanent waveform of ``track_id`` when it still fits the audio."""
        return self._repository.load_waveform(track_id, current_duration_us)

    def request(
        self,
        source: ConversionSource,
        revision: SourceRevision,
        current_duration_us: int | None,
        *,
        is_cancelled: Callable[[], bool] = lambda: False,
        report_progress: Callable[[float], None] = lambda _value: None,
    ) -> WaveformPoints:
        """Return the waveform, computing and storing it when none is stored."""
        stored = self.stored(source.track_id, current_duration_us)
        if stored is not None:
            report_progress(1.0)
            return stored
        outcome = self._analyzer.analyze(
            source,
            revision,
            expected_duration_us=current_duration_us,
            is_cancelled=is_cancelled,
            report_progress=report_progress,
        )
        self._repository.save_waveform(source.track_id, outcome.waveform, current_duration_us)
        return outcome.waveform
