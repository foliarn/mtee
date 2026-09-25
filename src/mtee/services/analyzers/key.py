"""Segmented chroma key estimates with transparent profile provenance."""

from __future__ import annotations

from importlib.metadata import version

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

_NOTES = ("C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B")
_MAJOR = np.asarray([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.asarray([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


class KeyAnalyzer:
    name = "key"
    version = f"librosa-{version('librosa')}-chroma-krumhansl-v1"

    def __init__(self, decoder: MediaDecodeService) -> None:
        self._decoder = decoder

    def analyze(
        self, source: ConversionSource, spec: AnalysisSpec, context: AnalyzerContext
    ) -> AnalysisResult:
        winners: list[str] = []
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
            minimum_rms = float(spec.config.get("minimum_rms", 0.002))
            energy = librosa.feature.rms(y=audio, frame_length=4096, hop_length=512)[0]
            active_frames = energy > minimum_rms
            if int(np.count_nonzero(active_frames)) < 32:
                segments.append(
                    {
                        "start_us": start_us,
                        "end_us": end_us,
                        "status": "not_applicable",
                        "reason": "too_quiet",
                    }
                )
                continue
            chroma = librosa.feature.chroma_stft(
                y=audio, sr=SAMPLE_RATE, n_fft=4096, hop_length=512, n_chroma=12
            )
            profile = np.mean(chroma[:, active_frames], axis=1)
            if float(np.std(profile)) < 1e-5:
                segments.append(
                    {
                        "start_us": start_us,
                        "end_us": end_us,
                        "status": "uncertain",
                        "reason": "uniform_chroma",
                    }
                )
                continue
            candidates: list[tuple[float, str]] = []
            centered = profile - np.mean(profile)
            for mode, template in (("major", _MAJOR), ("minor", _MINOR)):
                centered_template = template - np.mean(template)
                denominator = float(np.linalg.norm(centered) * np.linalg.norm(centered_template))
                for tonic in range(12):
                    rotated = np.roll(centered_template, tonic)
                    score = float(np.dot(centered, rotated) / denominator) if denominator else 0.0
                    candidates.append(
                        (score, f"{_NOTES[tonic]} {'major' if mode == 'major' else 'minor'}")
                    )
            candidates.sort(reverse=True)
            best, second = candidates[:2]
            margin = best[0] - second[0]
            status = (
                "available"
                if margin >= float(spec.config.get("minimum_margin", 0.04))
                else "uncertain"
            )
            if status == "available":
                winners.append(best[1])
            useful_frames += sample_count
            segments.append(
                {
                    "start_us": start_us,
                    "end_us": end_us,
                    "status": status,
                    "key": best[1],
                    "profile_correlation": best[0],
                    "runner_up": second[1],
                    "margin": margin,
                }
            )
        observed = SourceRevision.observe(source.path, generation=source.revision.generation)
        if source.revision.looks_modified(observed):
            raise ValueError("The source changed during key analysis.")
        if winners:
            counts = {key: winners.count(key) for key in set(winners)}
            ordered = sorted(counts, key=lambda key: (-counts[key], key))
            key_value = ordered[0]
            disagreement = 1 - counts[key_value] / len(winners)
            status = AnalysisStatus.UNCERTAIN if disagreement > 0.34 else AnalysisStatus.AVAILABLE
            metrics = (
                AnalysisMetric("key", key_value),
                AnalysisMetric("key_runner_up", ordered[1] if len(ordered) > 1 else None),
                AnalysisMetric("segment_disagreement", disagreement, "ratio"),
                AnalysisMetric("segments_with_tonal_content", len(winners), "segments"),
            )
        else:
            status = AnalysisStatus.NOT_APPLICABLE
            metrics = (AnalysisMetric("key", None),)
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
                "n_fft": 4096,
                "hop_length": 512,
                "algorithm": "chroma_stft + Krumhansl-Kessler profiles",
                "profile_source": "Krumhansl & Kessler (1982) published major/minor profiles",
                "margin_is_probability": False,
            },
            status,
            metrics,
            tuple(segments),
            "No segment had enough tonal content for a key estimate." if not winners else "",
            useful_frames / total_frames if total_frames else 0.0,
        )
