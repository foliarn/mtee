"""Asynchronous file-operation previews and results exposed to QML."""

from __future__ import annotations

from functools import partial
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.domain.file_operations import FileOperationPreview, FileOperationResult
from mtee.domain.jobs import JobId, JobState, JobStatus
from mtee.models.player_model import PlayerModel
from mtee.services.file_operation_service import FileOperationService
from mtee.services.jobs import JobContext, JobService

__all__ = ["FileOperationModel"]


class FileOperationModel(QObject):
    """Capture selected UUIDs, preview paths, then mutate them on job workers."""

    changed = Signal()
    dialogRequested = Signal()
    operationFinished = Signal()
    recoveryChecked = Signal(object)
    recoveryResolved = Signal(object)
    undoableChecked = Signal(str)

    def __init__(
        self,
        service: FileOperationService,
        jobs: JobService,
        player: PlayerModel | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._jobs = jobs
        self._player = player
        self._track_ids: list[str] = []
        self._kind = ""
        self._preview: FileOperationPreview | None = None
        self._preview_target = ""
        self._state = "idle"
        self._message = ""
        self._results: list[dict[str, Any]] = []
        self._progress = 0.0
        self._recovery: list[dict[str, Any]] = []
        self._undo_ids: list[str] = []
        self._busy_ids: set[str] = set()
        self._waiting_for_release = ""
        self._active_job_id: JobId | None = None
        self._can_cancel = False
        self.batchFinished.connect(self._on_batch_finished)
        self.recoveryChecked.connect(self._on_recovery_checked)
        self.recoveryResolved.connect(self._on_recovery_resolved)
        self.undoableChecked.connect(self._on_undoable_checked)
        self._jobs.jobUpdated.connect(self._on_job_updated)
        if player is not None:
            player.trackAccessReleased.connect(self._on_track_access_released)
        self._jobs.submit(self._inspect_recovery, label="Inspect file operation recovery")

    batchFinished = Signal(str, object)

    @Property(str, notify=changed)
    def state(self) -> str:
        return self._state

    @Property(str, notify=changed)
    def message(self) -> str:
        return self._message

    @Property(float, notify=changed)
    def progress(self) -> float:
        return self._progress

    @Property(str, notify=changed)
    def kind(self) -> str:
        return self._kind

    @Property(str, notify=changed)
    def previewTarget(self) -> str:
        return self._preview_target

    @Property(list, notify=changed)
    def previewTargets(self) -> list[dict[str, Any]]:
        return self._preview.to_dict()["targets"] if self._preview else []

    @Property(bool, notify=changed)
    def canExecute(self) -> bool:
        return bool(self._preview and self._preview.executable and self._state == "preview")

    @Property(bool, notify=changed)
    def canStopPlaybackAndContinue(self) -> bool:
        if self._player is None:
            return False
        playing_id = self._player.playing_id_value()
        return bool(playing_id and playing_id in self._busy_track_ids())

    @Property(list, notify=changed)
    def results(self) -> list[dict[str, Any]]:
        return list(self._results)

    @Property(list, notify=changed)
    def recoveryOperations(self) -> list[dict[str, Any]]:
        return list(self._recovery)

    @Property(bool, notify=changed)
    def canUndo(self) -> bool:
        return bool(self._undo_ids) and self._state != "running"

    @Property(bool, notify=changed)
    def canCancel(self) -> bool:
        return self._can_cancel and self._state == "running"

    @Property(bool, notify=changed)
    def trashAvailable(self) -> bool:
        return False

    @Slot(str, str, list, result=bool)
    def openOperation(self, kind: str, target: str, track_ids: list) -> bool:
        """Capture the current UUIDs and open the preview/confirmation dialog."""
        if self._state == "running":
            return False
        captured = list(dict.fromkeys(str(track_id) for track_id in track_ids if str(track_id)))
        if not captured:
            self._message = "Select at least one track first."
            self._state = "error"
            self.changed.emit()
            return False
        if kind == "rename" and len(captured) != 1:
            self._message = "Rename one track at a time."
            self._state = "error"
            self.changed.emit()
            return False
        self._track_ids = captured
        self._kind = kind
        self._preview_target = target
        self._results = []
        self._busy_ids.clear()
        self._message = ""
        self._state = "preview"
        self._refresh_preview()
        self.dialogRequested.emit()
        return True

    @Slot(str)
    def setPreviewTarget(self, target: str) -> None:
        if not self._track_ids or self._state == "running":
            return
        self._preview_target = target
        self._state = "preview"
        self._refresh_preview()

    @Slot()
    def execute(self) -> None:
        preview = self._preview
        if preview is None or not preview.executable or self._state == "running":
            return
        captured_preview = preview
        self._state = "running"
        self._progress = 0.0
        self._can_cancel = True
        self._message = "Working…"
        self.changed.emit()

        def task(context: JobContext) -> None:
            results: list[FileOperationResult] = []
            failure: Exception | None = None
            try:
                for index, target in enumerate(captured_preview.targets):
                    if context.is_cancelled:
                        break
                    target_count = max(1, len(captured_preview.targets))
                    results.append(
                        self._service.execute_target(
                            captured_preview.kind,
                            target,
                            is_cancelled=lambda: context.is_cancelled,
                            report_progress=partial(
                                _report_target_progress,
                                context,
                                index,
                                target_count,
                            ),
                        )
                    )
                    context.report_progress(len(results) / target_count)
            except Exception as error:
                failure = error
                remaining = next(
                    (
                        target
                        for target in captured_preview.targets
                        if target.track_id not in {result.track_id for result in results}
                    ),
                    None,
                )
                if remaining is not None:
                    results.append(
                        FileOperationResult(
                            remaining.track_id,
                            "",
                            "failed",
                            f"{type(error).__name__}: {error}",
                            remaining.source,
                            remaining.destination,
                        )
                    )
            self.batchFinished.emit(captured_preview.preview_id, results)
            if context.is_cancelled:
                context.raise_if_cancelled()
            if failure is not None:
                raise failure

        self._active_job_id = self._jobs.submit(task, label=f"{preview.kind.title()} audio files")

    @Slot()
    def cancel(self) -> None:
        if self._active_job_id is None:
            return
        try:
            self._jobs.cancel(self._active_job_id)
        except LookupError:
            return
        self._can_cancel = False
        self._message = "Stopping at the next safe point…"
        self.changed.emit()

    @Slot()
    def retryBusy(self) -> None:
        if self._preview is None or self._state == "running" or not self._busy_ids:
            return
        self._retry_after_playback_stop(next(iter(self._busy_ids)))

    @Slot()
    def stopPlaybackAndContinue(self) -> None:
        if self._player is None:
            return
        playing_id = self._player.playing_id_value()
        if not playing_id or playing_id not in self._busy_track_ids():
            return
        self._waiting_for_release = playing_id
        self._message = "Stopping playback before continuing…"
        self.changed.emit()
        if not self._player.stopAndRelease(playing_id):
            self._waiting_for_release = ""
            self._retry_after_playback_stop(playing_id)

    @Slot(str)
    def _on_track_access_released(self, track_id: str) -> None:
        if track_id == self._waiting_for_release:
            self._waiting_for_release = ""
            self._retry_after_playback_stop(track_id)

    @Slot()
    def undo(self) -> None:
        if not self._undo_ids or self._state == "running":
            return
        operation_id = self._undo_ids[-1]
        self._state = "running"
        self._can_cancel = False
        self._message = "Undoing the last move…"
        self.changed.emit()

        def task(_context: JobContext) -> None:
            result = self._service.undo_move(operation_id)
            self.batchFinished.emit(f"undo:{operation_id}", [result])

        self._active_job_id = self._jobs.submit(task, label="Undo file move")

    @Slot()
    def refreshRecovery(self) -> None:
        self._jobs.submit(self._inspect_recovery, label="Inspect file operation recovery")

    @Slot(str)
    def completeRecoveryToDestination(self, operation_id: str) -> None:
        """Explicitly adopt a verified destination-only recovery."""
        if self._state == "running" or not any(
            item.get("operationId") == operation_id and item.get("canCompleteDestination")
            for item in self._recovery
        ):
            return
        self._state = "running"
        self._message = "Rechecking the verified destination…"
        self.changed.emit()

        def task(_context: JobContext) -> None:
            result = self._service.complete_recovery_to_destination(operation_id)
            self.recoveryResolved.emit(result)

        self._active_job_id = self._jobs.submit(task, label="Complete verified file recovery")

    def _refresh_preview(self) -> None:
        self._preview = self._service.preview(
            self._current_kind(), self._track_ids, self._preview_target
        )
        self.changed.emit()

    def _current_kind(self) -> str:
        return self._kind

    def _inspect_recovery(self, context: JobContext) -> None:
        try:
            context.raise_if_cancelled()
            operations = self._service.incomplete_operations()
            undoable = self._service.latest_undoable_operation_id()
            summaries = [
                {
                    "operationId": str(operation.get("operation_id", "")),
                    "trackId": str(operation.get("track_id", "")),
                    "source": str(operation.get("source_path", "")),
                    "destination": str(operation.get("destination_path", "")),
                    "recoveryPath": str(operation.get("recovery_path", "") or ""),
                    "situation": str(operation.get("recovery_situation", "inspect_paths")),
                    "error": str(operation.get("error", "")),
                    "canCompleteDestination": (
                        operation.get("recovery_situation") == "destination_present"
                        and operation.get("kind") != "copy"
                        and operation.get("undo_of") is None
                    ),
                }
                for operation in operations
            ]
        except Exception as error:
            undoable = ""
            summaries = [
                {
                    "operationId": "",
                    "situation": "inspection_failed",
                    "error": f"{type(error).__name__}: {error}",
                }
            ]
        self.recoveryChecked.emit(summaries)
        self.undoableChecked.emit(undoable)

    @Slot(object)
    def _on_recovery_checked(self, operations: object) -> None:
        if isinstance(operations, list):
            self._recovery = [item for item in operations if isinstance(item, dict)]
        self.changed.emit()

    @Slot(object)
    def _on_recovery_resolved(self, value: object) -> None:
        if not isinstance(value, FileOperationResult):
            return
        self._active_job_id = None
        self._can_cancel = False
        self._state = "result" if value.status == "completed" else "recovery"
        self._message = value.message
        if (
            value.status == "completed"
            and value.operation_id
            and value.operation_id not in self._undo_ids
        ):
            self._undo_ids.append(value.operation_id)
        if value.track_id:
            self._results = [
                item for item in self._results if item.get("trackId") != value.track_id
            ]
            self._results.append(
                {
                    "trackId": value.track_id,
                    "operationId": value.operation_id,
                    "status": value.status,
                    "message": value.message,
                    "source": str(value.source or ""),
                    "destination": str(value.destination or ""),
                }
            )
        self.operationFinished.emit()
        self.changed.emit()
        self.refreshRecovery()

    @Slot(str)
    def _on_undoable_checked(self, operation_id: str) -> None:
        if operation_id and operation_id not in self._undo_ids:
            self._undo_ids.append(operation_id)
            self.changed.emit()

    @Slot(object)
    def _on_job_updated(self, value: object) -> None:
        if not isinstance(value, JobStatus) or value.job_id != self._active_job_id:
            return
        self._progress = value.progress
        self.changed.emit()
        if value.state is JobState.CANCELLED:
            self._active_job_id = None
            self._can_cancel = False
            if self._state == "running":
                self._state = "cancelled"
                self._message = "Stopped before any files were changed."
            self.changed.emit()
        elif value.state is JobState.FAILED:
            self._active_job_id = None
            self._can_cancel = False
            self._state = "error"
            self._message = value.error.message if value.error else "The file operation failed."
            self.changed.emit()

    @Slot(str, object)
    def _on_batch_finished(self, preview_id: str, values: object) -> None:
        is_undo = preview_id.startswith("undo:")
        if self._preview is None or (preview_id != self._preview.preview_id and not is_undo):
            return
        results = values if isinstance(values, list) else []
        self._active_job_id = None
        self._can_cancel = False
        incoming = [
            {
                "trackId": result.track_id,
                "operationId": result.operation_id,
                "status": result.status,
                "message": result.message,
                "source": str(result.source or ""),
                "destination": str(result.destination or ""),
            }
            for result in results
            if isinstance(result, FileOperationResult)
        ]
        merged = {str(item.get("trackId", "")): item for item in self._results}
        merged.update({str(item.get("trackId", "")): item for item in incoming})
        self._results = list(merged.values())
        self._busy_ids = {
            str(item.get("trackId", "")) for item in self._results if item.get("status") == "busy"
        }
        completed = [
            result.operation_id
            for result in results
            if isinstance(result, FileOperationResult)
            and result.status == "completed"
            and result.operation_id
        ]
        if is_undo:
            original_id = preview_id.removeprefix("undo:")
            if completed and original_id in self._undo_ids:
                self._undo_ids.remove(original_id)
        else:
            if self._kind != "copy":
                self._undo_ids.extend(completed)
        has_recovery = any(
            isinstance(result, FileOperationResult) and result.status == "recovery"
            for result in results
        )
        has_failed = any(
            isinstance(result, FileOperationResult) and result.status == "failed"
            for result in results
        )
        has_cancelled = any(
            isinstance(result, FileOperationResult) and result.status == "cancelled"
            for result in results
        )
        was_cancelled = (
            (len(results) < len(self._preview.targets) or has_cancelled)
            and not is_undo
            and not has_failed
        )
        self._state = "recovery" if has_recovery else "cancelled" if was_cancelled else "result"
        if was_cancelled:
            self._message = (
                "The copy was cancelled; its source and library location were left unchanged."
                if has_cancelled
                else "Stopped after the current file. Unprocessed files were left unchanged."
            )
        else:
            self._message = _result_message(self._results)
            if has_failed and len(results) < len(self._preview.targets):
                self._message += ". Remaining files were left unchanged."
        self.operationFinished.emit()
        self.changed.emit()
        self.refreshRecovery()

    def _busy_track_ids(self) -> set[str]:
        return self._busy_ids

    def _retry_after_playback_stop(self, track_id: str) -> None:
        if self._preview is None or track_id not in self._busy_ids:
            return
        self._track_ids = [track_id]
        self._refresh_preview()
        self.execute()


def _result_message(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No file operation completed."
    counts: dict[str, int] = {}
    for result in results:
        status = str(result.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return " · ".join(f"{count} {status}" for status, count in counts.items())


def _report_target_progress(
    context: JobContext,
    index: int,
    target_count: int,
    copied: int,
    total: int,
) -> None:
    """Combine byte progress for one file with progress across its batch."""
    fraction = min(1.0, copied / max(1, total))
    context.report_progress((index + fraction) / target_count)
