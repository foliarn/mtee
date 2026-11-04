"""Run drag-and-drop file moves on a worker and report what happened."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from mtee.domain.job_summaries import copied_summary, fixed, moved_summary
from mtee.domain.jobs import JobCancelledError
from mtee.services.file_move_service import (
    FileMoveError,
    FileMoveResult,
    FileMoveService,
    FolderActionResult,
)
from mtee.services.jobs import JobContext, JobService

__all__ = ["FileMoveModel"]

_PROBLEMS = {"conflict", "busy", "failed"}


class FileMoveModel(QObject):
    """Move tracks into a library folder; the files stay on the worker thread."""

    resultsReady = Signal(str, object)
    tracksMoved = Signal(object)
    # Files were copied into a folder: {rootId, relative}; the library reads the new files.
    tracksCopied = Signal(object)
    tracksRenamed = Signal(object)
    renameFinished = Signal(object)
    noticeRaised = Signal(str)
    # A folder was created or renamed on disk: {action, rootId, relative, previous, name}.
    folderChanged = Signal(object)
    folderActionFinished = Signal(object, str, str)

    @Slot(str, str, str)
    def create_folder(self, root_id: str, parent_relative: str, name: str) -> None:
        """Create a folder inside a source as a job; an existing name is refused."""
        identity = str(root_id)
        parent = str(parent_relative)
        wanted = str(name)

        def task(context: JobContext) -> None:
            result = self._service.create_folder(identity, parent, wanted)
            context.report_progress(1.0)
            self.folderActionFinished.emit(result, identity, parent)
            if result.status in _PROBLEMS:
                context.report_failure(result.name or wanted, result.message)
                raise _MoveBatchError(result.message)

        try:
            self._jobs.submit(task, label="Create folder", summary=fixed("Folder created"))
        except RuntimeError as error:
            self.noticeRaised.emit(str(error))

    @Slot(str, str)
    def create_unnamed_folder(self, root_id: str, parent_relative: str) -> None:
        """Create "Unnamed folder NN" (the first free NN) inside a source, without asking a name."""
        identity = str(root_id)
        parent = str(parent_relative)

        def task(context: JobContext) -> None:
            try:
                wanted = self._service.next_folder_name(identity, parent)
            except FileMoveError as error:
                context.report_failure("Unnamed folder", str(error))
                raise _MoveBatchError(str(error)) from error
            result = self._service.create_folder(identity, parent, wanted)
            context.report_progress(1.0)
            # The tree then starts renaming the new folder inline.
            self._rename_created = result.relative if result.status == "created" else ""
            self.folderActionFinished.emit(result, identity, parent)
            if result.status in _PROBLEMS:
                context.report_failure(result.name or wanted, result.message)
                raise _MoveBatchError(result.message)

        try:
            self._jobs.submit(task, label="Create folder", summary=fixed("Folder created"))
        except RuntimeError as error:
            self.noticeRaised.emit(str(error))

    @Slot(str, str, str)
    def rename_folder(self, root_id: str, relative: str, new_name: str) -> None:
        """Rename a folder of a source on disk as a job; the records under it follow."""
        identity = str(root_id)
        folder = str(relative)
        wanted = str(new_name)

        def task(context: JobContext) -> None:
            result = self._service.rename_folder(identity, folder, wanted)
            context.report_progress(1.0)
            self.folderActionFinished.emit(result, identity, folder)
            if result.status in _PROBLEMS:
                context.report_failure(result.name or wanted, result.message)
                raise _MoveBatchError(result.message)

        try:
            self._jobs.submit(task, label="Rename folder", summary=fixed("Folder renamed"))
        except RuntimeError as error:
            self.noticeRaised.emit(str(error))

    @Slot(object, str, str)
    def _on_folder_action_finished(self, result: object, root_id: str, relative: str) -> None:
        if not isinstance(result, FolderActionResult):
            return
        if result.status in {"created", "renamed"}:
            start_rename = result.status == "created" and self._rename_created == result.relative
            self._rename_created = ""
            self.folderChanged.emit(
                {
                    "action": result.status,
                    "rootId": root_id,
                    "previous": result.previous or relative,
                    "relative": result.relative,
                    "name": result.name,
                    "startRename": start_rename,
                }
            )
        self.noticeRaised.emit(result.message)

    def __init__(
        self, service: FileMoveService, jobs: JobService, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._jobs = jobs
        self._rename_created = ""
        self.resultsReady.connect(self._on_results_ready)
        self.renameFinished.connect(self._on_rename_finished)
        self.folderActionFinished.connect(self._on_folder_action_finished)

    @Slot(list, str, str, str)
    def move_tracks(
        self, raw_track_ids: list, root_id: str, relative: str, folder_name: str
    ) -> None:
        self._transfer(raw_track_ids, root_id, relative, folder_name, copy=False)

    @Slot(list, str, str, str)
    def copy_tracks(
        self, raw_track_ids: list, root_id: str, relative: str, folder_name: str
    ) -> None:
        """Copy the files of these tracks into a library folder, never replacing a file."""
        self._transfer(raw_track_ids, root_id, relative, folder_name, copy=True)

    def _transfer(
        self,
        raw_track_ids: list,
        root_id: str,
        relative: str,
        folder_name: str,
        *,
        copy: bool,
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
                    result = (
                        self._service.copy(track_id, folder)
                        if copy
                        else self._service.move(track_id, folder)
                    )
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
                    if copy and any(item.status == "copied" for item in results):
                        self.tracksCopied.emit({"rootId": root_id, "relative": relative})
            if cancelled:
                raise JobCancelledError(str(context.job_id))
            if any(result.status in _PROBLEMS for result in results):
                raise _MoveBatchError(
                    f"One or more files could not be {'copied' if copy else 'moved'}."
                )

        try:
            self._jobs.submit(
                task,
                label=f"{'Copy' if copy else 'Move'} files to {folder_name}",
                summary=copied_summary() if copy else moved_summary(),
            )
        except RuntimeError as error:
            self.noticeRaised.emit(str(error))

    @Slot(str, str)
    def rename_track(self, track_id: str, new_base_name: str) -> None:
        """Rename one track's file in its folder as a job; the extension stays."""
        identity = str(track_id)
        if not identity:
            return

        def task(context: JobContext) -> None:
            result = self._service.rename(identity, str(new_base_name))
            context.report_progress(1.0)
            self.renameFinished.emit(result)
            if result.status in _PROBLEMS:
                context.report_failure(result.name, result.message)
                raise _MoveBatchError(result.message)

        try:
            self._jobs.submit(task, label="Rename file", summary=fixed("File renamed"))
        except RuntimeError as error:
            self.noticeRaised.emit(str(error))

    @Slot(object)
    def _on_rename_finished(self, result: object) -> None:
        if not isinstance(result, FileMoveResult):
            return
        if result.status == "moved":
            self.tracksRenamed.emit([{"trackId": result.track_id, "path": result.path}])
            self.noticeRaised.emit(f"Renamed “{result.name}” to “{Path(result.path).name}”.")
        elif result.status == "unchanged":
            self.noticeRaised.emit(result.message)
        else:
            self.noticeRaised.emit(f"“{result.name}” was not renamed: {result.message}")

    @Slot(str, object)
    def _on_results_ready(self, folder_name: str, results: object) -> None:
        if isinstance(results, str):
            self.noticeRaised.emit(results)
            return
        if not isinstance(results, list):
            return
        moved = [item for item in results if item.status in {"moved", "copied"}]
        problems = [item for item in results if item.status in _PROBLEMS]
        copied = any(item.status == "copied" for item in moved)
        if copied:
            self.noticeRaised.emit(_summary(folder_name, moved, problems, copy=True))
            return
        if moved:
            self.tracksMoved.emit([{"trackId": item.track_id, "path": item.path} for item in moved])
        self.noticeRaised.emit(_summary(folder_name, moved, problems))


def _summary(
    folder_name: str,
    moved: list[FileMoveResult],
    problems: list[FileMoveResult],
    *,
    copy: bool = False,
) -> str:
    if not moved and not problems:
        return f"Already in {folder_name}."
    text = ""
    done = "copied" if copy else "moved"
    if moved:
        what = f"“{moved[0].name}”" if len(moved) == 1 else f"{len(moved)} files"
        text = f"{done.capitalize()} {what} to {folder_name}."
    if problems:
        first = problems[0]
        extra = (
            f"“{first.name}” was not {done}: {first.message}"
            if len(problems) == 1
            else f"{len(problems)} files were not {done}: {first.message}"
        )
        text = f"{text} {extra}".strip()
    return text


class _MoveBatchError(RuntimeError):
    code = "file_move_partial_failure"
