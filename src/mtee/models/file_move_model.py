"""Run drag-and-drop file moves on a worker and report what happened."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from mtee.domain.jobs import JobCancelledError
from mtee.services.file_move_service import FileMoveError, FileMoveResult, FileMoveService
from mtee.services.jobs import JobContext, JobService

__all__ = ["FileMoveModel"]

_PROBLEMS = {"conflict", "busy", "failed"}


class FileMoveModel(QObject):
    """Move tracks into a library folder; the files stay on the worker thread."""

    resultsReady = Signal(str, object)
    tracksMoved = Signal(object)
    noticeRaised = Signal(str)

    def __init__(
        self, service: FileMoveService, jobs: JobService, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._jobs = jobs
        self.resultsReady.connect(self._on_results_ready)

    @Slot(list, str, str, str)
    def move_tracks(
        self, raw_track_ids: list, root_id: str, relative: str, folder_name: str
    ) -> None:
        ids = list(dict.fromkeys(str(value) for value in raw_track_ids if str(value)))
        if not ids:
            return

        def task(context: JobContext) -> None:
            results: list[FileMoveResult] = []
            cancelled = False
            try:
                try:
                    folder = self._service.resolve_folder(root_id, relative)
                except FileMoveError as error:
                    self.resultsReady.emit(folder_name, str(error))
                    raise _MoveBatchError(str(error)) from error
                for index, track_id in enumerate(ids):
                    context.raise_if_cancelled()
                    result = self._service.move(track_id, folder)
                    results.append(result)
                    context.report_progress((index + 1) / len(ids))
                    context.report_items(index + 1, len(ids), result.name)
                    if result.status in _PROBLEMS:
                        context.report_failure(result.name, result.message)
            except JobCancelledError:
                cancelled = True
            finally:
                if results:
                    self.resultsReady.emit(folder_name, results)
            if cancelled:
                raise JobCancelledError(str(context.job_id))
            if any(result.status in _PROBLEMS for result in results):
                raise _MoveBatchError("One or more files could not be moved.")

        try:
            self._jobs.submit(task, label=f"Move files to {folder_name}")
        except RuntimeError as error:
            self.noticeRaised.emit(str(error))

    @Slot(str, object)
    def _on_results_ready(self, folder_name: str, results: object) -> None:
        if isinstance(results, str):
            self.noticeRaised.emit(results)
            return
        if not isinstance(results, list):
            return
        moved = [item for item in results if item.status == "moved"]
        problems = [item for item in results if item.status in _PROBLEMS]
        if moved:
            self.tracksMoved.emit([{"trackId": item.track_id, "path": item.path} for item in moved])
        self.noticeRaised.emit(_summary(folder_name, moved, problems))


def _summary(folder_name: str, moved: list[FileMoveResult], problems: list[FileMoveResult]) -> str:
    if not moved and not problems:
        return f"Already in {folder_name}."
    text = ""
    if moved:
        what = f"“{moved[0].name}”" if len(moved) == 1 else f"{len(moved)} files"
        text = f"Moved {what} to {folder_name}."
    if problems:
        first = problems[0]
        extra = (
            f"“{first.name}” was not moved: {first.message}"
            if len(problems) == 1
            else f"{len(problems)} files were not moved: {first.message}"
        )
        text = f"{text} {extra}".strip()
    return text


class _MoveBatchError(RuntimeError):
    code = "file_move_partial_failure"
