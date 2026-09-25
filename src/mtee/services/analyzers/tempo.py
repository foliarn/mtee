"""Segmented librosa beat tracking with explicit half/double candidates."""

from __future__ import annotations

from importlib.metadata import version
from statistics import median

import librosa
import numpy as np

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
from mtee.services.analyzers.segmented import SAMPLE_RATE, pcm_segments
from mtee.services.media_decode_service import MediaDecodeService


class TempoAnalyzer:
    name = "tempo"
    version = f"librosa-{version('librosa')}-beattrack-v1"

    def __init__(self, decoder: MediaDecodeService) -> None:
        self._decoder = decoder

    def analyze(
        self, source: ConversionSource, spec: AnalysisSpec, context: AnalyzerContext
    ) -> AnalysisResult:
        start_bpm = float(spec.config.get("start_bpm", 120.0))
        if not 30 <= start_bpm <= 300:
            raise ValueError("The tempo tracking prior must be between 30 and 300 BPM.")
        estimates: list[float] = []
        segments: list[dict[str, float | int | str]] = []
        total_frames = 0
        useful_frames = 0
        for start_frame, payload in pcm_segments(self._decoder, source, context):
            context.raise_if_cancelled()
            sample_count = len(payload) // 2
            total_frames += sample_count
            start_us = round(start_frame * 1_000_000 / SAMPLE_RATE)
            end_us = round((start_frame + sample_count) * 1_000_000 / SAMPLE_RATE)
            if sample_count < SAMPLE_RATE * 10:
                continue
            audio = np.frombuffer(payload, dtype="<i2").astype(np.float32) / 32768.0
            onset = librosa.onset.onset_strength(y=audio, sr=SAMPLE_RATE, hop_length=512)
            if onset.size == 0 or float(np.std(onset)) < 1e-7:
                segments.append(
                    {
                        "start_us": start_us,
                        "end_us": end_us,
                        "status": "uncertain",
                        "reason": "no_onsets",
                    }
                )
                continue
            tempo, beat_frames = librosa.beat.beat_track(
                onset_envelope=onset,
                sr=SAMPLE_RATE,
                hop_length=512,
                start_bpm=start_bpm,
                trim=True,
            )
            bpm = float(np.asarray(tempo).reshape(-1)[0]) if np.asarray(tempo).size else 0.0
            if not np.isfinite(bpm) or bpm <= 0 or len(beat_frames) < 3:
                segments.append(
                    {
                        "start_us": start_us,
                        "end_us": end_us,
                        "status": "uncertain",
                        "reason": "insufficient_beats",
                    }
                )
                continue
            estimates.append(bpm)
            useful_frames += sample_count
            segments.append(
                {
                    "start_us": start_us,
                    "end_us": end_us,
                    "status": "available",
                    "tempo_bpm": bpm,
                    "beat_count": len(beat_frames),
                }
            )
        observed = SourceRevision.observe(source.path, generation=source.revision.generation)
        if source.revision.looks_modified(observed):
            raise ValueError("The source changed during tempo analysis.")
        if estimates:
            value = float(median(estimates))
            deviation = float(median([abs(item - value) for item in estimates]))
            status = (
                AnalysisStatus.AVAILABLE if deviation / value <= 0.08 else AnalysisStatus.UNCERTAIN
            )
            metrics = (
                AnalysisMetric("tempo_bpm", value, "BPM"),
                AnalysisMetric("tempo_half_bpm", value / 2, "BPM"),
                AnalysisMetric("tempo_double_bpm", value * 2, "BPM"),
                AnalysisMetric("segment_median_absolute_deviation", deviation, "BPM"),
                AnalysisMetric("segments_with_beats", len(estimates), "segments"),
            )
        else:
            status = AnalysisStatus.NOT_APPLICABLE
            metrics = (AnalysisMetric("tempo_bpm", None, "BPM"),)
        context.report_progress(1.0)
        return AnalysisResult(
            new_analysis_id(),
            context.run_id,
            source.track_id,
            self.name,
            self.version,
            source.revision,
            {
                "sample_rate": SAMPLE_RATE,
                "segment_seconds": 60,
                "hop_length": 512,
                "algorithm": "librosa.onset_strength + beat_track",
                "score_is_probability": False,
            },
            status,
            metrics,
            tuple(segments),
            "No stable beat estimate; no tempo value is assigned." if not estimates else "",
            useful_frames / total_frames if total_frames else 0.0,
        )
