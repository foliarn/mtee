"""Analysis of tracks: tempo, key and waveform, kept permanently.

A track is analyzed only when the user asks. The result is stored beside the tags,
never in place of them; a value the user edited is never replaced, and the tags of
the file change only when the user enabled that option. A field that a file stores
under several tag names is not written by itself: it becomes a tag conflict that the
user can resolve, which deletes the old names and values and writes the new one.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from mtee.domain.analysis import AnalysisSettings, TrackAnalysis, format_bpm
from mtee.domain.conversion import ConversionSource
from mtee.domain.jobs import JobCancelledError
from mtee.domain.metadata_edit import MetadataEditResult, MetadataPatch
from mtee.domain.tag_conflicts import TagConflict, TagConflictEntry
from mtee.domain.tracks import SourceRevision
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.library_repository import LibraryRepository, TrackSource
from mtee.services.audio_analyzer import AudioAnalyzer

__all__ = ["AnalysisBatchError", "AnalysisService", "TagWriter", "TrackReport"]

_WHOLE_NUMBER_BPM_SUFFIXES = {".m4a", ".mp4", ".m4b", ".aac"}


class AnalysisBatchError(RuntimeError):
    """Some tracks of a batch failed; the others keep their stored results."""

    code = "analysis_incomplete"


class TagWriter(Protocol):
    """The part of the metadata edit service used to copy results into tags."""

    def save(
        self,
        track_id: str,
        expected_revision: SourceRevision,
        patch: MetadataPatch,
        draft_id: str,
    ) -> MetadataEditResult: ...

    def tag_conflicts(self, track_id: str, fields: Sequence[str]) -> dict[str, tuple[str, ...]]: ...


@dataclass(frozen=True, slots=True)
class TrackReport:
    """Outcome of one track of a batch."""

    track_id: str
    ok: bool
    message: str = ""
    conflict: TagConflict | None = None


class AnalysisService:
    def __init__(
        self,
        library: LibraryRepository,
        repository: AnalysisRepository,
        analyzer: AudioAnalyzer,
        tag_writer: TagWriter | None = None,
    ) -> None:
        self._library = library
        self._repository = repository
        self._analyzer = analyzer
        self._tag_writer = tag_writer

    def pending(self, track_ids: Sequence[str], *, force: bool) -> list[str]:
        """Return the tracks that need an analysis; ``force`` keeps them all.

        A track also needs one when only its waveform is missing or of an older version:
        it then gets the waveform alone, see ``analyze_track``.
        """
        identities = list(dict.fromkeys(track_ids))
        if force:
            return identities
        stored = self._repository.get_many(identities)
        pending: list[str] = []
        for track_id in identities:
            record = self._library.source_record(track_id)
            duration = _duration_us(record)
            if not self._repository.is_current(
                stored.get(track_id), duration
            ) or not self._repository.has_current_waveform(track_id, duration):
                pending.append(track_id)
        return pending

    def run_batch(
        self,
        track_ids: Sequence[str],
        settings: AnalysisSettings,
        *,
        is_cancelled: Callable[[], bool],
        report_progress: Callable[[float], None],
        on_track_done: Callable[[str], None] = lambda _track_id: None,
        on_conflict: Callable[[TagConflict], None] = lambda _conflict: None,
        report_items: Callable[[int, int, str], None] = lambda _done, _total, _name: None,
        report_failure: Callable[[str, str], None] = lambda _name, _message: None,
        force: bool = False,
    ) -> list[TrackReport]:
        """Analyze ``track_ids``, ``settings.parallel_jobs`` at a time.

        With ``force`` every track is analyzed in full, even one whose results are current.

        Raises ``JobCancelledError`` on cancellation and ``AnalysisBatchError`` at the
        end when some tracks failed; finished tracks are stored either way.
        """
        total = len(track_ids)
        if total == 0:
            return []
        progress = dict.fromkeys(track_ids, 0.0)
        lock = threading.Lock()
        finished = 0

        def file_name(track_id: str) -> str:
            record = self._library.source_record(track_id)
            return record.path.name if record is not None else track_id

        def overall(track_id: str, value: float) -> None:
            with lock:
                progress[track_id] = value
                report_progress(sum(progress.values()) / total)

        def work(track_id: str) -> TrackReport:
            nonlocal finished
            if is_cancelled():
                raise JobCancelledError("analysis cancelled")
            name = file_name(track_id)
            with lock:
                report_items(finished, total, name)
            report = self.analyze_track(
                track_id,
                settings,
                is_cancelled=is_cancelled,
                report_progress=lambda value: overall(track_id, value),
                force=force,
            )
            overall(track_id, 1.0)
            with lock:
                finished += 1
                report_items(finished, total, name)
                if not report.ok:
                    report_failure(name, report.message or "unknown error")
            if report.conflict is not None:
                on_conflict(report.conflict)
            on_track_done(track_id)
            return report

        reports: list[TrackReport] = []
        with ThreadPoolExecutor(
            max_workers=max(1, settings.parallel_jobs), thread_name_prefix="mtee-analysis"
        ) as pool:
            futures = [pool.submit(work, track_id) for track_id in track_ids]
            try:
                for future in futures:
                    reports.append(future.result())
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
        failed = [report for report in reports if not report.ok]
        if failed:
            first = failed[0].message or "unknown error"
            raise AnalysisBatchError(
                f"{len(failed)} of {total} tracks could not be analyzed: {first}"
            )
        return reports

    def analyze_track(
        self,
        track_id: str,
        settings: AnalysisSettings,
        *,
        is_cancelled: Callable[[], bool] = lambda: False,
        report_progress: Callable[[float], None] = lambda _value: None,
        force: bool = False,
    ) -> TrackReport:
        """Analyze one track and store the results.

        When the tempo and key are current but the stored waveform is missing or of an
        older version, only the waveform is computed and saved: the tempo, the key, the
        manual corrections and the tags of the file are left alone. ``force`` skips that
        shortcut and redoes everything.
        """
        record = self._library.source_record(track_id)
        if record is None:
            return TrackReport(track_id, False, "The track is no longer in the library.")
        if record.status != "readable":
            return TrackReport(track_id, False, "This audio file could not be read.")
        duration = _duration_us(record)
        source = ConversionSource(track_id, record.path, record.revision)
        waveform_only = (
            not force
            and self._repository.is_current(self._repository.get(track_id), duration)
            and not self._repository.has_current_waveform(track_id, duration)
        )
        try:
            outcome = self._analyzer.analyze(
                source,
                record.revision,
                tempo_range=(
                    None if waveform_only else (float(settings.bpm_min), float(settings.bpm_max))
                ),
                tonality=not waveform_only,
                expected_duration_us=duration,
                is_cancelled=is_cancelled,
                report_progress=report_progress,
            )
        except JobCancelledError:
            raise
        except Exception as error:
            return TrackReport(track_id, False, f"{record.path.name}: {error}")
        self._repository.save_waveform(track_id, outcome.waveform, duration)
        if waveform_only:
            return TrackReport(track_id, True)
        stored = self._repository.save_result(
            track_id, bpm=outcome.bpm, key=outcome.key, source_duration_us=duration
        )
        conflict = None
        if settings.write_tags:
            message, conflict = self._write_tags(record, stored, settings)
            if message:
                return TrackReport(track_id, False, f"{record.path.name}: {message}", conflict)
        return TrackReport(track_id, True, conflict=conflict)

    def resolve_tag_conflict(self, conflict: TagConflict) -> str:
        """Replace the old tag names and values of a conflict by the waiting values.

        Returns ``""`` on success, else the reason. A value the user edited since the
        conflict was recorded is left alone.
        """
        if self._tag_writer is None:
            return "Writing tags is not available."
        record = self._library.source_record(conflict.track_id)
        if record is None:
            return "The track is no longer in the library."
        stored = self._repository.get(conflict.track_id)
        changes: dict[str, str | None] = {}
        for entry in conflict.entries:
            edited = stored is not None and (
                stored.bpm_user_edited if entry.field == "bpm" else stored.key_user_edited
            )
            if not edited:
                changes[entry.field] = entry.value
        if not changes:
            return ""
        result = self._tag_writer.save(
            conflict.track_id,
            record.revision,
            MetadataPatch.from_mapping(changes, replace_aliases=True),
            str(uuid.uuid4()),
        )
        return "" if result.status == "saved" else (result.message or result.status)

    def _write_tags(
        self, record: TrackSource, stored: TrackAnalysis, settings: AnalysisSettings
    ) -> tuple[str, TagConflict | None]:
        """Copy the calculated values into the tags.

        Returns a failure message (``""`` when none) and the conflict holding the
        values that were not written because the file stores their field ambiguously.
        """
        if self._tag_writer is None:
            return "", None
        changes: dict[str, str | None] = {}
        if stored.bpm is not None and not stored.bpm_user_edited:
            text = bpm_tag_text(stored.bpm, record.path)
            if record.snapshot.bpm != (text,):
                changes["bpm"] = text
        if stored.key is not None and not stored.key_user_edited:
            text = stored.key.text(settings.notation)
            if record.snapshot.key != (text,):
                changes["key"] = text
        if not changes:
            return "", None
        ambiguous = self._tag_writer.tag_conflicts(record.track_id, tuple(changes))
        entries = tuple(
            TagConflictEntry(field, aliases, str(changes.pop(field)))
            for field, aliases in ambiguous.items()
            if field in changes
        )
        conflict = TagConflict(record.track_id, record.path.name, entries) if entries else None
        if not changes:
            return "", conflict
        current = self._library.source_record(record.track_id)
        if current is None:
            return "The track is no longer in the library.", conflict
        result = self._tag_writer.save(
            record.track_id,
            current.revision,
            MetadataPatch.from_mapping(changes),
            str(uuid.uuid4()),
        )
        message = "" if result.status == "saved" else (result.message or result.status)
        return message, conflict


def bpm_tag_text(bpm: float, path: Path) -> str:
    """Return the tempo as written in a tag: a whole number where the format needs one."""
    whole = path.suffix.lower() in _WHOLE_NUMBER_BPM_SUFFIXES
    return str(round(bpm)) if whole else format_bpm(bpm, 2).rstrip("0").rstrip(".")


def _duration_us(record: TrackSource | None) -> int | None:
    return record.snapshot.technical.duration_us if record is not None else None
