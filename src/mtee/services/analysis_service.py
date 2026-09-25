"""Preview and execute reproducible local analysis jobs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mtee.domain.analysis import (
    AnalysisOverride,
    AnalysisResult,
    AnalysisSpec,
    AnalysisStatus,
    new_analysis_id,
)
from mtee.domain.conversion import ConversionSource
from mtee.domain.jobs import JobCancelledError
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.analyzers.base import Analyzer, AnalyzerContext
from mtee.services.ffmpeg_runtime import FfmpegRuntime
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.media_decode_service import MediaDecodeService
from mtee.services.media_probe import MediaProbeService

__all__ = ["AnalysisBatchPreview", "AnalysisService"]


@dataclass(frozen=True, slots=True)
class AnalysisBatchPreview:
    preview_id: str
    sources: tuple[ConversionSource, ...]
    specs: tuple[AnalysisSpec, ...]


class AnalysisService:
    def __init__(
        self,
        library: LibraryRepository,
        repository: AnalysisRepository,
        file_access: FileAccessCoordinator,
        *,
        runtime: FfmpegRuntime | None = None,
    ) -> None:
        self._library = library
        self._repository = repository
        self._file_access = file_access
        self._runtime = runtime or FfmpegRuntime()
        self._probe = MediaProbeService(self._runtime)
        self._decoder = MediaDecodeService(file_access, runtime=self._runtime)
        self._loaded_analyzers: dict[str, Analyzer] | None = None

    def preview(self, track_ids: list[str], specs: list[AnalysisSpec]) -> AnalysisBatchPreview:
        if not track_ids:
            raise ValueError("Select at least one track to analyze.")
        if not specs:
            raise ValueError("Select at least one analysis method.")
        if len({spec.analyzer for spec in specs}) != len(specs):
            raise ValueError("An analysis method can appear only once per run.")
        sources: list[ConversionSource] = []
        for track_id in dict.fromkeys(track_ids):
            record = self._library.source_record(track_id)
            if record is None or record.status != "readable":
                raise ValueError(f"Track {track_id} is no longer available in the library.")
            observed = SourceRevision.observe(record.path, generation=record.revision.generation)
            if record.revision.looks_modified(observed):
                raise ValueError(f"Track {track_id} changed. Rescan the library before analysis.")
            sources.append(ConversionSource(track_id, Path(record.path), record.revision))
        return AnalysisBatchPreview(str(uuid.uuid4()), tuple(sources), tuple(specs))

    def execute(self, preview: AnalysisBatchPreview, context: Any) -> None:
        total = len(preview.sources) * len(preview.specs)
        complete = 0
        for source in preview.sources:
            context.raise_if_cancelled()
            current = self._library.source_record(source.track_id)
            if (
                current is None
                or Path(current.path) != source.path
                or _revision_is_stale(current.revision, source.revision)
                or source.revision.looks_modified(
                    SourceRevision.observe(source.path, generation=source.revision.generation)
                )
            ):
                raise ValueError(f"Track {source.track_id} changed after the analysis preview.")
            run_id = str(uuid.uuid4())
            self._repository.begin_run(run_id, source.track_id, source.revision)
            failures = 0
            try:
                for spec in preview.specs:
                    context.raise_if_cancelled()
                    analyzer = self._analyzers()[spec.analyzer]
                    child_context = AnalyzerContext(
                        run_id,
                        lambda: context.is_cancelled,
                        lambda progress, done=complete: context.report_progress(
                            min(0.99, (done + progress) / total)
                        ),
                    )
                    try:
                        if spec.analyzer in {"technical", "silence", "loudness"}:
                            with self._file_access.acquire_read(
                                TrackId.parse(source.track_id), "audio analysis"
                            ):
                                result = analyzer.analyze(source, spec, child_context)
                        else:
                            result = analyzer.analyze(source, spec, child_context)
                        if _revision_is_stale(
                            result.source_revision,
                            SourceRevision.observe(
                                source.path, generation=source.revision.generation
                            ),
                        ):
                            result = _failure_result(
                                source,
                                spec,
                                run_id,
                                analyzer.version,
                                AnalysisStatus.STALE,
                                "Source changed while the analysis was running.",
                            )
                            failures += 1
                    except JobCancelledError:
                        raise
                    except Exception as error:
                        current_revision = SourceRevision.observe(
                            source.path, generation=source.revision.generation
                        )
                        changed = _revision_is_stale(source.revision, current_revision)
                        result = _failure_result(
                            source,
                            spec,
                            run_id,
                            analyzer.version,
                            AnalysisStatus.STALE if changed else AnalysisStatus.FAILED,
                            "Source changed while the analysis was running."
                            if changed
                            else f"{type(error).__name__}: {error}",
                        )
                        failures += 1
                    self._repository.save_result(result)
                    complete += 1
                    context.report_progress(complete / total)
            except JobCancelledError:
                self._repository.finish_run(run_id, "cancelled")
                raise
            self._repository.finish_run(run_id, "partial" if failures else "succeeded")
        context.report_progress(1.0)

    def results(self, track_id: str) -> list[dict[str, Any]]:
        current = self._library.source_record(track_id)
        current_revision = _observed_revision(current)
        values = self._repository.results(track_id)
        for item in values:
            revision = SourceRevision(
                int(item["source_size_bytes"]),
                int(item["source_mtime_ns"]),
                item["source_file_id"],
                int(item["source_generation"]),
            )
            item["source_stale"] = current_revision is None or current_revision.looks_modified(
                revision
            )
            if item["source_stale"] and item["status"] not in {"failed", "stale"}:
                item["status"] = AnalysisStatus.STALE.value
        return values

    def overrides(self, track_id: str) -> list[dict[str, Any]]:
        current = self._library.source_record(track_id)
        current_revision = _observed_revision(current)
        values = self._repository.overrides(track_id)
        for item in values:
            revision = SourceRevision(
                int(item["source_size_bytes"]),
                int(item["source_mtime_ns"]),
                item["source_file_id"],
                int(item["source_generation"]),
            )
            item["source_stale"] = current_revision is None or current_revision.looks_modified(
                revision
            )
        return values

    def confirm(self, track_id: str, field_name: str, value: float | str | None) -> None:
        if field_name not in {"tempo_bpm", "key"}:
            raise ValueError(f"Manual confirmation is unsupported for {field_name}.")
        record = self._library.source_record(track_id)
        if record is None:
            raise ValueError("The track is no longer available in the library.")
        observed = SourceRevision.observe(record.path, generation=record.revision.generation)
        if _revision_is_stale(record.revision, observed):
            raise ValueError("The track changed. Rescan the library before confirming a value.")
        if field_name == "tempo_bpm" and (not isinstance(value, (int, float)) or value <= 0):
            raise ValueError("Tempo must be a positive number of beats per minute.")
        if field_name == "key" and (not isinstance(value, str) or not value.strip()):
            raise ValueError("Enter a tonal key name.")
        self._repository.save_override(
            AnalysisOverride(new_analysis_id(), track_id, field_name, value, record.revision)
        )

    def clear_override(self, track_id: str, field_name: str) -> None:
        self._repository.clear_override(track_id, field_name)

    def _analyzers(self) -> dict[str, Analyzer]:
        if self._loaded_analyzers is None:
            # Import numerical runtimes from the analysis worker, not GUI startup.
            from mtee.services.analyzers.key import KeyAnalyzer
            from mtee.services.analyzers.loudness import LoudnessAnalyzer
            from mtee.services.analyzers.silence import SilenceAnalyzer
            from mtee.services.analyzers.technical import TechnicalAnalyzer
            from mtee.services.analyzers.tempo import TempoAnalyzer

            self._loaded_analyzers = {
                "technical": TechnicalAnalyzer(self._probe),
                "silence": SilenceAnalyzer(self._runtime, self._probe),
                "loudness": LoudnessAnalyzer(self._runtime),
                "tempo": TempoAnalyzer(self._decoder),
                "key": KeyAnalyzer(self._decoder),
            }
        return self._loaded_analyzers


def _failure_result(
    source: ConversionSource,
    spec: AnalysisSpec,
    run_id: str,
    version: str,
    status: AnalysisStatus,
    message: str,
) -> AnalysisResult:
    return AnalysisResult(
        new_analysis_id(),
        run_id,
        source.track_id,
        spec.analyzer,
        version,
        source.revision,
        dict(spec.config),
        status,
        diagnostics=message,
    )


def _revision_is_stale(saved: SourceRevision, current: SourceRevision) -> bool:
    return saved.generation != current.generation or saved.looks_modified(current)


def _observed_revision(record: Any) -> SourceRevision | None:
    if record is None:
        return None
    return SourceRevision.observe(record.path, generation=record.revision.generation)
