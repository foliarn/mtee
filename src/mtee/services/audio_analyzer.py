"""Decode a track once and derive its waveform, tempo and key from that pass."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mtee.domain.conversion import ConversionSource
from mtee.domain.jobs import JobCancelledError
from mtee.domain.musical_key import MusicalKey
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.domain.waveform import WaveformPoints
from mtee.services.analysis.features import ENVELOPE_RATE, SAMPLE_RATE, FeatureExtractor
from mtee.services.analysis.key import estimate_key
from mtee.services.analysis.tempo import estimate_tempo
from mtee.services.analysis.waveform import reduce_waveform
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.media_decode_service import MediaDecodeService

__all__ = ["AnalysisOutcome", "AudioAnalyzer"]

_BLOCK_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    """Everything one pass over the audio produced; a value is ``None`` when unknown."""

    waveform: WaveformPoints
    bpm: float | None
    key: MusicalKey | None


class AudioAnalyzer:
    """Stream a track through the feature extractor without holding it in memory."""

    def __init__(self, decoder: MediaDecodeService, file_access: FileAccessCoordinator) -> None:
        self._decoder = decoder
        self._file_access = file_access

    def analyze(
        self,
        source: ConversionSource,
        revision: SourceRevision,
        *,
        tempo_range: tuple[float, float] | None = None,
        tonality: bool = False,
        expected_duration_us: int | None = None,
        is_cancelled: Callable[[], bool] = lambda: False,
        report_progress: Callable[[float], None] = lambda _value: None,
    ) -> AnalysisOutcome:
        """Return the waveform, and the tempo and key when they were requested.

        ``tempo_range`` asks for the tempo inside that interval; ``tonality`` asks
        for the key. With neither, only the waveform is computed.
        """
        self._ensure_unchanged(source, revision, "before")
        with self._file_access.acquire_read(
            TrackId.parse(source.track_id), "audio analysis", timeout_seconds=0
        ):
            outcome = self._run(
                source,
                tempo_range,
                tonality,
                expected_duration_us,
                is_cancelled,
                report_progress,
            )
        self._ensure_unchanged(source, revision, "while")
        report_progress(1.0)
        return outcome

    def _run(
        self,
        source: ConversionSource,
        tempo_range: tuple[float, float] | None,
        tonality: bool,
        expected_duration_us: int | None,
        is_cancelled: Callable[[], bool],
        report_progress: Callable[[float], None],
    ) -> AnalysisOutcome:
        extractor = FeatureExtractor(rhythm=tempo_range is not None, tonality=tonality)
        expected_frames = (
            max(1, round(expected_duration_us * SAMPLE_RATE / 1_000_000))
            if expected_duration_us
            else None
        )
        for block in self._decoder.stream_pcm(
            source,
            sample_rate=SAMPLE_RATE,
            channels=2,
            block_bytes=_BLOCK_BYTES,
            read_lease_held=True,
            is_cancelled=is_cancelled,
        ):
            if is_cancelled():
                raise JobCancelledError("audio analysis cancelled")
            extractor.feed(block)
            if expected_frames:
                report_progress(min(0.98, extractor.frames / expected_frames))
        features = extractor.finish()
        if features.frames < 1:
            raise ValueError("No decodable audio frames were found.")
        waveform = reduce_waveform(
            features.waveform_low, features.waveform_high, features.duration_us
        )
        bpm: float | None = None
        if tempo_range is not None:
            estimate = estimate_tempo(
                features.onset_envelope, ENVELOPE_RATE, tempo_range[0], tempo_range[1]
            )
            bpm = estimate.bpm if estimate is not None else None
        key: MusicalKey | None = None
        if tonality:
            key_estimate = estimate_key(features.pitch_profile)
            key = key_estimate.key if key_estimate is not None else None
        return AnalysisOutcome(waveform, bpm, key)

    @staticmethod
    def _ensure_unchanged(source: ConversionSource, revision: SourceRevision, when: str) -> None:
        observed = SourceRevision.observe(source.path, generation=revision.generation)
        if revision.looks_modified(observed):
            raise ValueError(f"The source changed {when} its analysis.")
