"""Confirm, execute, and report Windows recycle-bin operations."""

from __future__ import annotations

import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.domain.jobs import JobCancelledError, JobId
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.models.player_model import PlayerModel
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.trash_repository import TrashRepository
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError
from mtee.services.jobs import JobContext, JobService
from mtee.services.trash_service import TrashService

__all__ = ["TrashModel"]


@dataclass(frozen=True, slots=True)
class _Candidate:
    track_id: str
    path: Path
    revision: SourceRevision
    root_id: str
    parent_relative: str


class TrashModel(QObject):
    """Keep confirmation in Qt and run each Shell operation on one worker."""

    changed = Signal()
    dialogRequested = Signal()
    resultsReady = Signal(int, object)
    preparationReady = Signal(int, object, object)
    preparationFailed = Signal(int, str, bool)
    interruptedReady = Signal(object)
    tracksRecycled = Signal(object)

    def __init__(
        self,
        library: LibraryRepository,
        jobs: JobService,
        service: TrashService,
        file_access: FileAccessCoordinator,
        journal: TrashRepository,
        player: PlayerModel | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._library = library
        self._jobs = jobs
        self._service = service
        self._file_access = file_access
        self._journal = journal
        self._player = player
        self._requested_ids: list[str] = []
        self._candidates: tuple[_Candidate, ...] = ()
        self._state = "idle"
        self._message = ""
        self._results: list[dict[str, Any]] = []
        self._busy_ids: set[str] = set()
        self._generation = 0
        self._active_job_id = ""
        self._waiting_for_release = ""
        self._retry_prefix: list[dict[str, Any]] = []
        self._new_result_start = 0
        self.resultsReady.connect(self._on_results_ready)
        self.preparationReady.connect(self._on_preparation_ready)
        self.preparationFailed.connect(self._on_preparation_failed)
        self.interruptedReady.connect(self._on_interrupted_ready)
        if player is not None:
            player.trackAccessReleased.connect(self._on_track_access_released)
            player.playbackChanged.connect(self.changed.emit)
        try:

            def inspect_interrupted(_context: JobContext) -> None:
                self.interruptedReady.emit(self._journal.interrupted())

            self._jobs.submit(inspect_interrupted, label="Inspect recycle history", visible=False)
        except RuntimeError:
            pass

    @Property(str, notify=changed)
    def state(self) -> str:
        return self._state

    @Property(str, notify=changed)
    def message(self) -> str:
        return self._message

    @Property(int, notify=changed)
    def selectedCount(self) -> int:
        return len(self._candidates) if self._state == "confirm" else len(self._requested_ids)

    @Property(list, notify=changed)
    def results(self) -> list[dict[str, Any]]:
        return [dict(result) for result in self._results]

    @Property(bool, notify=changed)
    def canConfirm(self) -> bool:
        return self._state == "confirm" and bool(self._requested_ids)

    @Property(bool, notify=changed)
    def canStopPlaybackAndContinue(self) -> bool:
        if self._player is None:
            return False
        playing_id = self._player.playing_id_value()
        return bool(playing_id and playing_id in self._busy_ids)

    @Property(bool, notify=changed)
    def hasBusyFiles(self) -> bool:
        return bool(self._busy_ids)

    @Property(bool, notify=changed)
    def canCancel(self) -> bool:
        return bool(self._active_job_id)

    @Slot(list)
    def request_recycle(self, raw_track_ids: list) -> None:
        if self._state in {"preparing", "running"}:
            return
        ids = list(dict.fromkeys(str(value) for value in raw_track_ids if str(value)))
        if not ids:
            return
        self._generation += 1
        generation = self._generation
        self._requested_ids = ids
        self._candidates = ()
        self._retry_prefix = []
        self._results = []
        self._busy_ids.clear()
        self._state = "preparing"
        self._message = f"Preparing {len(ids)} file(s) for confirmation…"
        self.changed.emit()

        def prepare(context: JobContext) -> None:
            candidates: list[_Candidate] = []
            failures: list[dict[str, Any]] = []
            try:
                for track_id in ids:
                    context.raise_if_cancelled()
                    source = self._library.source_record(track_id)
                    row = self._library.track(track_id)
                    if source is None or source.status != "readable" or not row:
                        failures.append(
                            {
                                "trackId": track_id,
                                "source": source.path.name if source else track_id,
                                "status": "conflict",
                                "message": "The file is no longer available in the library.",
                            }
                        )
                        continue
                    relative = str(row.get("relativePath", ""))
                    candidates.append(
                        _Candidate(
                            track_id,
                            source.path,
                            source.revision,
                            str(row.get("rootId", "")),
                            relative.rpartition("/")[0],
                        )
                    )
                self.preparationReady.emit(generation, candidates, failures)
            except JobCancelledError:
                self.preparationFailed.emit(generation, "Recycle preparation was cancelled.", False)
                raise
            except Exception as error:
                self.preparationFailed.emit(
                    generation, f"Could not prepare the recycle operation: {error}", True
                )
                raise

        try:
            self._active_job_id = str(self._jobs.submit(prepare, label="Prepare recycle operation"))
        except RuntimeError as error:
            self._active_job_id = ""
            self._state = "result"
            self._message = str(error)
            self.changed.emit()

    @Slot()
    def confirm(self) -> None:
        if not self.canConfirm or not self._candidates:
            return
        self._busy_ids.clear()
        self._retry_prefix = []
        self._submit(list(self._candidates), self._results)

    @Slot()
    def retry_busy(self) -> None:
        if self._state == "running" or not self._busy_ids:
            return
        ids = sorted(self._busy_ids)
        self._retry_prefix = [dict(item) for item in self._results if item.get("status") != "busy"]
        self._requested_ids = ids
        self._candidates = tuple(
            candidate for candidate in self._candidates if candidate.track_id in self._busy_ids
        )
        self._results = [dict(item) for item in self._retry_prefix]
        self._busy_ids.clear()
        self._submit(list(self._candidates), self._retry_prefix)

    @Slot()
    def stop_playback_and_continue(self) -> None:
        if self._player is None:
            return
        playing_id = self._player.playing_id_value()
        if not playing_id or playing_id not in self._busy_ids:
            return
        self._waiting_for_release = playing_id
        self._message = "Stopping playback before retrying the recycle operation…"
        self.changed.emit()
        if not self._player.stopAndRelease(playing_id):
            self._waiting_for_release = ""
            self.retry_busy()

    @Slot(str)
    def _on_track_access_released(self, track_id: str) -> None:
        if track_id != self._waiting_for_release:
            return
        self._waiting_for_release = ""
        self.retry_busy()

    @Slot()
    def cancel(self) -> None:
        if not self._active_job_id:
            return
        with suppress(LookupError, ValueError):
            self._jobs.cancel(JobId.parse(self._active_job_id))
        self._message = "Stopping after the current Shell operation…"
        self.changed.emit()

    def _submit(self, candidates: list[_Candidate], initial_results: list[dict[str, Any]]) -> None:
        self._generation += 1
        generation = self._generation
        self._state = "running"
        self._message = f"Recycling {len(candidates)} audio file(s)…"
        frozen_results = tuple(dict(item) for item in initial_results)
        self._new_result_start = len(frozen_results)
        self.changed.emit()

        def task(context: JobContext) -> None:
            results = [dict(item) for item in frozen_results]
            cancelled = False
            try:
                total = max(1, len(candidates))
                for index, candidate in enumerate(candidates):
                    context.raise_if_cancelled()
                    operation_id = str(uuid.uuid4())
                    self._journal.prepare(
                        operation_id,
                        candidate.track_id,
                        str(candidate.path),
                        candidate.revision,
                    )
                    result = self._recycle_one(candidate, operation_id, context)
                    results.append(result)
                    context.report_progress((index + 1) / total)
                    context.report_items(index + 1, len(candidates), candidate.path.name)
                    if result.get("status") in {"failed", "conflict", "busy"}:
                        context.report_failure(
                            candidate.path.name,
                            str(result.get("message") or result.get("status")),
                        )
            except JobCancelledError:
                cancelled = True
            finally:
                self.resultsReady.emit(generation, results)
            if cancelled:
                raise JobCancelledError(str(context.job_id))
            if any(result.get("status") in {"failed", "conflict", "busy"} for result in results):
                raise _TrashBatchError("One or more files could not be recycled safely.")

        try:
            self._active_job_id = str(self._jobs.submit(task, label="Move audio to Recycle Bin"))
        except RuntimeError as error:
            self._active_job_id = ""
            self._state = "result"
            self._message = str(error)
        self.changed.emit()

    @Slot(int, object, object)
    def _on_preparation_ready(self, generation: int, candidates: object, failures: object) -> None:
        if generation != self._generation or not isinstance(candidates, list):
            return
        self._active_job_id = ""
        self._candidates = tuple(item for item in candidates if isinstance(item, _Candidate))
        self._results = (
            [dict(item) for item in failures if isinstance(item, dict)]
            if isinstance(failures, list)
            else []
        )
        if self._candidates:
            self._state = "confirm"
            self._message = (
                "Review the selected files, then confirm moving them to the Windows Recycle Bin."
            )
        else:
            self._state = "result"
            self._message = "No selected audio files are available to recycle."
        self.dialogRequested.emit()
        self.changed.emit()

    @Slot(int, str, bool)
    def _on_preparation_failed(self, generation: int, message: str, show: bool) -> None:
        if generation != self._generation:
            return
        self._active_job_id = ""
        self._state = "result"
        self._message = message
        if show:
            # The dialog only opens on request: without it the error would stay unseen.
            self.dialogRequested.emit()
        self.changed.emit()

    @Slot(object)
    def _on_interrupted_ready(self, rows: object) -> None:
        if not isinstance(rows, list) or not rows or self._state != "idle":
            return
        self._results = [
            {
                "trackId": str(row.get("track_id", "")),
                "operationId": str(row.get("operation_id", "")),
                "source": str(row.get("source_path", "")),
                "recycleItemIdentity": str(row.get("recycle_item_identity", "")),
                "status": "interrupted",
                "message": (
                    "The previous recycle result was not recorded. Check the Windows Recycle Bin; "
                    "MTEE did not infer success from a missing source path."
                ),
            }
            for row in rows
            if isinstance(row, dict)
        ]
        self._state = "result"
        self._message = f"{len(self._results)} interrupted recycle operation(s) need inspection."
        self.changed.emit()
        self.dialogRequested.emit()

    def _recycle_one(
        self, candidate: _Candidate, operation_id: str, context: JobContext
    ) -> dict[str, Any]:
        base = {
            "operationId": operation_id,
            "trackId": candidate.track_id,
            "source": str(candidate.path),
            "rootId": candidate.root_id,
            "parentRelative": candidate.parent_relative,
        }
        try:
            current = self._library.source_record(candidate.track_id)
            observed = SourceRevision.observe(
                candidate.path, generation=candidate.revision.generation
            )
            if (
                current is None
                or current.path.resolve(strict=False) != candidate.path.resolve(strict=False)
                or not candidate.revision.matches(current.revision)
                or not candidate.revision.matches(observed)
            ):
                self._journal.finish(operation_id, "conflict", "The file revision changed.")
                return {
                    **base,
                    "status": "conflict",
                    "message": "The file changed after confirmation.",
                }
            context.raise_if_cancelled()
            with self._file_access.acquire(
                TrackId.parse(candidate.track_id), "recycle audio file", timeout_seconds=0
            ):
                current = self._library.source_record(candidate.track_id)
                observed = SourceRevision.observe(
                    candidate.path, generation=candidate.revision.generation
                )
                if (
                    current is None
                    or not candidate.revision.matches(current.revision)
                    or not candidate.revision.matches(observed)
                ):
                    self._journal.finish(operation_id, "conflict", "The file revision changed.")
                    return {
                        **base,
                        "status": "conflict",
                        "message": "The file changed before recycling.",
                    }
                context.raise_if_cancelled()
                recycle_item_identity = self._service.recycle(candidate.path)
            message = "Moved to the Windows Recycle Bin."
            try:
                self._journal.finish(
                    operation_id,
                    "recycled",
                    message,
                    recycle_item_identity=recycle_item_identity,
                )
            except Exception:
                # Already recycled: any failure only flags the journal, never fails the result.
                message += " The recycle was confirmed, but its journal needs inspection."
            try:
                updated = self._library.mark_recycled(candidate.track_id, candidate.revision)
            except Exception:
                # Already recycled: any failure only flags the library, never fails the result.
                updated = False
                message += (
                    " The library could not be updated; it will be reconciled on the next scan."
                )
            if not updated and "reconciled" not in message:
                message += " The library record will be reconciled on the next scan."
            return {
                **base,
                "status": "recycled",
                "message": message,
                "recycleItemIdentity": recycle_item_identity,
            }
        except FileAccessTimeoutError:
            message = "The file is in use. Stop playback, then retry this file."
            self._journal.finish(operation_id, "failed", message)
            return {**base, "status": "busy", "message": message}
        except JobCancelledError:
            raise
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            self._journal.finish(operation_id, "failed", message)
            return {**base, "status": "failed", "message": message}

    @Slot(int, object)
    def _on_results_ready(self, generation: int, results: object) -> None:
        if generation != self._generation or not isinstance(results, list):
            return
        self._active_job_id = ""
        self._results = [dict(item) for item in results if isinstance(item, dict)]
        self._busy_ids = {
            str(item["trackId"]) for item in self._results if item.get("status") == "busy"
        }
        new_results = self._results[self._new_result_start :]
        recycled = [item for item in new_results if item.get("status") == "recycled"]
        if recycled:
            self.tracksRecycled.emit(recycled)
        self._state = "result"
        if self._busy_ids:
            self._message = "Stop playback and retry the files that are still in use."
        else:
            failed = sum(item.get("status") in {"failed", "conflict"} for item in self._results)
            count = len(recycled)
            self._message = (
                f"Recycled {count} file(s). {failed} need attention."
                if failed
                else f"Recycled {count} file(s) to the Windows Recycle Bin."
            )
        self.changed.emit()


class _TrashBatchError(RuntimeError):
    code = "trash_partial_failure"
