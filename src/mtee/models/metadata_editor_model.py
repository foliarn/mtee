"""Async metadata drafts, field capabilities, retries, and verified Undo."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.domain.metadata_edit import EDITABLE_METADATA_FIELDS, MetadataEditResult, MetadataPatch
from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.tracks import SourceRevision
from mtee.models.player_model import PlayerModel
from mtee.persistence.library_repository import LibraryRepository, TrackSource
from mtee.services.jobs import JobCancelledError, JobContext, JobId, JobService, UnknownJobError
from mtee.services.metadata_writer import MetadataEditService

__all__ = ["MetadataEditorModel"]

_FIELD_LABELS = {
    "title": "Title",
    "artist": "Artist",
    "album": "Album",
    "genre": "Genre",
    "date": "Date",
    "comment": "Comment",
    "track_number": "Track number",
    "bpm": "BPM",
    "key": "Key",
}
_FIELD_ATTRIBUTES = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "genre": "genre",
    "date": "date",
    "comment": "comment",
    "track_number": "track_number",
    "bpm": "bpm",
    "key": "key",
}


@dataclass(frozen=True, slots=True)
class _EditTarget:
    track_id: str
    revision: SourceRevision


@dataclass(frozen=True, slots=True)
class _EditBatch:
    batch_id: str
    draft_id: str
    field: str
    value: str | None
    targets: tuple[_EditTarget, ...]
    draft_selection: tuple[str, ...]


class MetadataEditorModel(QObject):
    """Capture selected UUIDs on focus and persist edits in background jobs."""

    changed = Signal()
    sourceChanged = Signal()
    batchFinished = Signal(str, object)
    recoveryChecked = Signal(object)
    inspectionFinished = Signal(int, object)

    def __init__(
        self,
        library: LibraryRepository,
        writer: MetadataEditService,
        jobs: JobService,
        selected_ids: Callable[[], list[str]],
        player: PlayerModel | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._library = library
        self._writer = writer
        self._jobs = jobs
        self._selected_ids = selected_ids
        self._player = player
        self._edit_targets: dict[str, tuple[_EditTarget, ...]] = {}
        self._drafts: dict[tuple[str, tuple[str, ...]], str | None] = {}
        self._pending: list[_EditBatch] = []
        self._active: _EditBatch | None = None
        self._save_state = "idle"
        self._save_message = ""
        self._retry_batch: _EditBatch | None = None
        self._undo_operations: list[str] = []
        self._undo_batch_operations: dict[str, tuple[str, ...]] = {}
        self._successful_revisions: dict[str, SourceRevision] = {}
        self._waiting_for_release = ""
        self._recovery_operations: list[dict[str, Any]] = []
        self._inspection_cache: dict[
            tuple[str, int], tuple[MetadataSnapshot, dict[str, tuple[bool, str]]]
        ] = {}
        self._inspection_request = 0
        self._inspection_job_id: JobId | None = None
        self._inspection_targets: tuple[tuple[str, int], ...] = ()
        self.batchFinished.connect(self._on_batch_finished)
        self.recoveryChecked.connect(self._on_recovery_checked)
        self.inspectionFinished.connect(self._on_inspection_finished)
        self._jobs.submit(self._inspect_recovery, label="Inspect metadata recovery")
        if player is not None:
            player.trackAccessReleased.connect(self._on_track_access_released)

    @Property(str, notify=changed)
    def saveState(self) -> str:
        return self._save_state

    @Property(str, notify=changed)
    def saveMessage(self) -> str:
        return self._save_message

    @Property(bool, notify=changed)
    def canStopPlaybackAndSave(self) -> bool:
        if self._player is None or self._retry_batch is None:
            return False
        playing_id = self._player.playing_id_value()
        return any(target.track_id == playing_id for target in self._retry_batch.targets)

    @Property(bool, notify=changed)
    def canUndo(self) -> bool:
        return bool(self._undo_operations) and self._active is None

    @Property(list, notify=changed)
    def recoveryOperations(self) -> list[dict[str, Any]]:
        return list(self._recovery_operations)

    @Property(list, notify=changed)
    def infoFields(self) -> list[dict[str, Any]]:
        selected = tuple(self._selected_ids())
        sources = [self._library.source_record(track_id) for track_id in selected]
        sources = [source for source in sources if source is not None]
        return self._fields_for_sources(sources, selected)

    @Slot(str, result=list)
    def fieldsForTrack(self, track_id: str) -> list[dict[str, Any]]:
        source = self._library.source_record(track_id)
        if source is None:
            return []
        return self._fields_for_sources([source], (track_id,))

    @Slot()
    @Slot(str)
    def prepareTrackInspection(self, track_id: str = "") -> None:
        """Prepare the selected tags and edit capabilities away from the UI thread."""
        track_ids = [track_id] if track_id else list(self._selected_ids())
        self._inspection_request += 1
        request_id = self._inspection_request
        self._cancel_inspection_job()
        sources = [
            source
            for identity in dict.fromkeys(str(value) for value in track_ids)
            if (source := self._library.source_record(identity)) is not None
        ]
        targets = tuple((source.track_id, source.revision.generation) for source in sources)
        self._inspection_targets = targets
        missing = [
            source
            for source in sources
            if (source.track_id, source.revision.generation) not in self._inspection_cache
        ]
        if not missing:
            self.changed.emit()
            return

        def inspect(context: JobContext) -> None:
            results = []
            for source in missing:
                context.raise_if_cancelled()
                try:
                    revision, snapshot, capabilities = self._writer.inspect(source.track_id)
                    results.append((source.track_id, revision, snapshot, capabilities, ""))
                except JobCancelledError:
                    raise
                except Exception as error:
                    results.append((source.track_id, None, None, None, str(error)))
            self.inspectionFinished.emit(request_id, results)

        self._inspection_job_id = self._jobs.submit(
            inspect, label="Prepare metadata view", visible=False
        )
        self.changed.emit()

    @Slot()
    def cancelPendingInspection(self) -> None:
        """Discard and cancel a tag inspection when its panel is closed."""
        self._inspection_request += 1
        self._inspection_targets = ()
        self._cancel_inspection_job()

    def _cancel_inspection_job(self) -> None:
        if self._inspection_job_id is None:
            return
        with suppress(UnknownJobError, ValueError):
            self._jobs.cancel(self._inspection_job_id)
        self._inspection_job_id = None

    @Slot(int, object)
    def _on_inspection_finished(self, request_id: int, values: object) -> None:
        if request_id != self._inspection_request or not isinstance(values, list):
            return
        self._inspection_job_id = None
        self._inspection_targets = ()
        for track_id, revision, snapshot, capabilities, error in values:
            current = self._library.source_record(track_id)
            if current is None:
                continue
            if revision is not None and current.revision != revision:
                continue
            resolved_snapshot = snapshot if isinstance(snapshot, MetadataSnapshot) else current.snapshot
            resolved_capabilities = (
                capabilities
                if isinstance(capabilities, dict)
                else {
                    field: (False, f"Could not inspect tags: {error}")
                    for field in EDITABLE_METADATA_FIELDS
                }
            )
            self._inspection_cache[(track_id, current.revision.generation)] = (
                resolved_snapshot,
                resolved_capabilities,
            )
        self.changed.emit()

    def _fields_for_sources(
        self, sources: list[TrackSource], selected: tuple[str, ...]
    ) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        inspected = [
            self._inspection_cache.get((source.track_id, source.revision.generation))
            for source in sources
        ]
        capabilities_by_source = [
            result[1]
            if result is not None
            else {
                field: (False, "Tags are being prepared before editing is enabled.")
                for field in EDITABLE_METADATA_FIELDS
            }
            for result in inspected
        ]
        snapshots = [result[0] if result is not None else source.snapshot
                     for source, result in zip(sources, inspected, strict=True)]
        for field in EDITABLE_METADATA_FIELDS:
            values = [
                tuple(getattr(snapshot, _FIELD_ATTRIBUTES[field])) for snapshot in snapshots
            ]
            normalized = [" / ".join(value) for value in values]
            unique = set(normalized)
            value = normalized[0] if normalized else ""
            mixed = len(unique) > 1
            if mixed:
                value = ""
            draft_key = (field, selected)
            if draft_key in self._drafts:
                value = self._drafts[draft_key] or ""
            editable, reason = self._capability(field, sources, capabilities_by_source)
            fields.append(
                {
                    "key": field,
                    "label": _FIELD_LABELS[field],
                    "value": value,
                    "mixed": mixed and draft_key not in self._drafts,
                    "editable": editable,
                    "reason": reason,
                }
            )
        return fields

    def refresh_selection(self) -> None:
        """Refresh the displayed values; drafts remain bound to their captured UUIDs."""
        self.changed.emit()

    def _inspect_recovery(self, context: JobContext) -> None:
        try:
            context.raise_if_cancelled()
            operations = self._writer.incomplete_operations()
            summaries = [
                {
                    "operationId": str(operation.get("operation_id", "")),
                    "trackId": str(operation.get("track_id", "")),
                    "fileName": Path(str(operation.get("source_path", ""))).name,
                    "situation": str(operation.get("recovery_situation", "inspect_paths")),
                    "error": str(operation.get("error", "")),
                }
                for operation in operations
            ]
        except Exception as error:
            summaries = [
                {
                    "operationId": "",
                    "fileName": "",
                    "situation": "inspection_failed",
                    "error": f"{type(error).__name__}: {error}",
                }
            ]
        self.recoveryChecked.emit(summaries)

    @Slot(object)
    def _on_recovery_checked(self, operations: object) -> None:
        if isinstance(operations, list):
            self._recovery_operations = [item for item in operations if isinstance(item, dict)]
        self.changed.emit()

    @Slot(str)
    def begin_field_edit(self, field: str) -> None:
        if field not in EDITABLE_METADATA_FIELDS:
            return
        self._capture_targets(field, f"selection:{field}", self._selected_ids())

    @Slot(str, str)
    def beginTrackFieldEdit(self, track_id: str, field: str) -> None:
        if field not in EDITABLE_METADATA_FIELDS:
            return
        self._capture_targets(field, f"track:{track_id}:{field}", [track_id])

    def _capture_targets(self, field: str, context_key: str, track_ids: list[str]) -> None:
        targets: list[_EditTarget] = []
        for track_id in track_ids:
            source = self._library.source_record(track_id)
            if source is not None:
                targets.append(_EditTarget(track_id, source.revision))
        self._edit_targets[context_key] = tuple(targets)

    @Slot(str, str, bool)
    def commit_field(self, field: str, value: str, remove: bool = False) -> None:
        self._commit_field(field, value, remove, f"selection:{field}")

    @Slot(str, str, str, bool)
    def commitTrackField(self, track_id: str, field: str, value: str, remove: bool = False) -> None:
        self._commit_field(field, value, remove, f"track:{track_id}:{field}")

    def _commit_field(self, field: str, value: str, remove: bool, context_key: str) -> None:
        if field not in EDITABLE_METADATA_FIELDS:
            return
        targets = self._edit_targets.pop(context_key, ())
        if not targets:
            track_ids = (
                self._selected_ids()
                if context_key.startswith("selection:")
                else [context_key.split(":", maxsplit=2)[1]]
            )
            self._capture_targets(field, context_key, track_ids)
            targets = self._edit_targets.pop(context_key, ())
        if not targets:
            return
        committed_value = None if remove else value
        selected = tuple(target.track_id for target in targets)
        self._drafts[(field, selected)] = committed_value
        batch = _EditBatch(
            batch_id=str(uuid.uuid4()),
            draft_id=str(uuid.uuid4()),
            field=field,
            value=committed_value,
            targets=targets,
            draft_selection=selected,
        )
        self._retry_batch = None
        self._pending.append(batch)
        if self._active is None:
            self._start_next()
        else:
            self._save_state = "saving"
            self._save_message = ""
            self.changed.emit()

    @Slot()
    def finish_save(self) -> None:
        if self._save_state == "saved":
            self._save_state = "idle"
            self._save_message = ""
            self.changed.emit()

    @Slot()
    def retry_save(self) -> None:
        if self._retry_batch is None or self._active is not None:
            return
        self._pending.insert(0, self._retry_batch)
        self._retry_batch = None
        self._start_next()

    @Slot()
    def retrySave(self) -> None:
        self.retry_save()

    @Slot()
    def stop_playback_and_save(self) -> None:
        if self._player is None or self._retry_batch is None:
            return
        playing_id = self._player.playing_id_value()
        if not playing_id or not any(
            target.track_id == playing_id for target in self._retry_batch.targets
        ):
            self.retry_save()
            return
        self._waiting_for_release = playing_id
        self._save_message = "Stopping playback before saving…"
        self.changed.emit()
        if not self._player.stopAndRelease(playing_id):
            self._waiting_for_release = ""
            self.retry_save()

    @Slot()
    def stopPlaybackAndSave(self) -> None:
        self.stop_playback_and_save()

    @Slot(str)
    def _on_track_access_released(self, track_id: str) -> None:
        if track_id == self._waiting_for_release:
            self._waiting_for_release = ""
            self.retry_save()

    @Slot()
    def undo_save(self) -> None:
        if not self._undo_operations or self._active is not None:
            self._save_state = "error"
            self._save_message = "There is no verified save available to undo."
            self.changed.emit()
            return
        operation_ids = tuple(self._undo_operations)
        batch_id = str(uuid.uuid4())
        draft_id = str(uuid.uuid4())
        self._save_state = "saving"
        self._save_message = "Undoing the last verified save…"
        self.changed.emit()

        def run(context: JobContext) -> None:
            results: list[MetadataEditResult] = []
            for index, operation_id in enumerate(operation_ids):
                try:
                    context.raise_if_cancelled()
                    results.append(self._writer.undo(operation_id, draft_id))
                    context.report_progress((index + 1) / len(operation_ids))
                except Exception as error:
                    results.append(
                        MetadataEditResult(
                            "",
                            "failed",
                            f"Undo stopped: {type(error).__name__}: {error}",
                            operation_id,
                        )
                    )
                    results.extend(
                        MetadataEditResult(
                            "", "failed", "Undo stopped before this file was processed.", rest
                        )
                        for rest in operation_ids[index + 1 :]
                    )
                    break
            self.batchFinished.emit(batch_id, results)

        self._active = _EditBatch(batch_id, draft_id, "", None, (), ())
        self._undo_batch_operations[batch_id] = operation_ids
        self._jobs.submit(run, label="Undo metadata edit")

    @Slot()
    def undoSave(self) -> None:
        self.undo_save()

    def _start_next(self) -> None:
        if self._active is not None or not self._pending:
            return
        batch = self._pending.pop(0)
        targets: list[_EditTarget] = []
        for target in batch.targets:
            recent_revision = self._successful_revisions.get(target.track_id)
            source = self._library.source_record(target.track_id)
            if (
                recent_revision is not None
                and source is not None
                and source.revision.generation == recent_revision.generation
                and source.revision.matches(recent_revision)
            ):
                target = _EditTarget(target.track_id, recent_revision)
            targets.append(target)
        batch = _EditBatch(
            batch.batch_id,
            batch.draft_id,
            batch.field,
            batch.value,
            tuple(targets),
            batch.draft_selection,
        )
        self._active = batch
        self._save_state = "saving"
        self._save_message = "Saving…"
        self.changed.emit()

        def run(context: JobContext) -> None:
            results: list[MetadataEditResult] = []
            total = max(1, len(batch.targets))
            for index, target in enumerate(batch.targets):
                try:
                    context.raise_if_cancelled()
                    patch = MetadataPatch.one(batch.field, batch.value)
                    results.append(
                        self._writer.save(
                            target.track_id,
                            target.revision,
                            patch,
                            batch.draft_id,
                        )
                    )
                    context.report_progress((index + 1) / total)
                except Exception as error:
                    results.append(
                        MetadataEditResult(
                            target.track_id,
                            "failed",
                            f"Save stopped: {type(error).__name__}: {error}",
                        )
                    )
                    results.extend(
                        MetadataEditResult(
                            remaining.track_id,
                            "failed",
                            "Save stopped before this file was processed.",
                        )
                        for remaining in batch.targets[index + 1 :]
                    )
                    break
            self.batchFinished.emit(batch.batch_id, results)

        self._jobs.submit(run, label="Save metadata")

    @Slot(str, object)
    def _on_batch_finished(self, batch_id: str, raw_results: object) -> None:
        batch = self._active
        if batch is None or batch.batch_id != batch_id:
            return
        results = list(raw_results) if isinstance(raw_results, list) else []
        self._active = None
        successful = [item for item in results if item.status == "saved"]
        failed = [item for item in results if item.status != "saved"]
        if not batch.field:
            operation_ids = self._undo_batch_operations.pop(batch.batch_id, ())
            self._undo_operations = [
                operation_id
                for operation_id, result in zip(operation_ids, results, strict=False)
                if result.status != "saved"
            ]
            self._retry_batch = None
            self._save_state = "saved" if not failed else "error"
            self._save_message = (
                "Undo completed." if not failed else "; ".join(item.message for item in failed)
            )
            if successful:
                self.sourceChanged.emit()
            self.changed.emit()
            if self._pending:
                self._start_next()
            return
        self._undo_operations = [item.operation_id for item in successful if item.operation_id]
        for result in successful:
            if result.revision is not None:
                self._successful_revisions[result.track_id] = result.revision

        draft_key = (batch.field, batch.draft_selection)
        newer_same_draft = any(
            queued.field == batch.field and queued.draft_selection == batch.draft_selection
            for queued in self._pending
        )
        if not failed and not newer_same_draft and self._drafts.get(draft_key) == batch.value:
            self._drafts.pop(draft_key, None)

        if failed:
            self._save_state = "busy" if all(item.status == "busy" for item in failed) else "error"
            details = "; ".join(dict.fromkeys(item.message for item in failed if item.message))
            self._save_message = (
                f"Saved {len(successful)} of {len(results)} tracks. {details}"
                if successful
                else details or "Could not save the metadata."
            )
            self._retry_batch = _EditBatch(
                batch_id=str(uuid.uuid4()),
                draft_id=batch.draft_id,
                field=batch.field,
                value=batch.value,
                targets=tuple(
                    target
                    for target, result in zip(batch.targets, results, strict=False)
                    if result.status != "saved"
                ),
                draft_selection=batch.draft_selection,
            )
        else:
            self._save_state = "saved"
            self._save_message = (
                f"Saved changes to {len(successful)} track(s)." if len(successful) > 1 else "Saved."
            )
            self._retry_batch = None
        if successful:
            self.sourceChanged.emit()
        self.changed.emit()
        if self._pending:
            self._start_next()

    @staticmethod
    def _capability(
        field: str,
        sources: list[TrackSource],
        capabilities_by_source: list[dict[str, tuple[bool, str]]],
    ) -> tuple[bool, str]:
        if not sources:
            return False, "Select a track to edit its tags."
        if any(source.status != "readable" for source in sources):
            return False, "Unreadable audio files are read-only."
        reasons: list[str] = []
        for source, capabilities in zip(sources, capabilities_by_source, strict=True):
            if source.status != "readable":
                reasons.append("Unreadable audio files are read-only.")
                continue
            editable, reason = capabilities.get(
                field, (False, "Writing is not verified for this field.")
            )
            if editable:
                return True, ""
            reasons.append(reason)
        return False, next(
            (reason for reason in reasons if reason), "No selected file is editable."
        )
