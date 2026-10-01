"""Qt model that launches and follows the analysis jobs started by the user."""

from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from mtee.domain.analysis import AnalysisSettings
from mtee.models.analysis_settings_model import AnalysisSettingsModel
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.analysis_service import AnalysisService
from mtee.services.jobs import JobContext, JobService

__all__ = ["AnalysisModel"]

_REFRESH_INTERVAL_MS = 1000


class _AnalysisBridge(QObject):
    """Carry worker-thread events to the graphical thread."""

    trackDone = Signal(str)
    notice = Signal(str)
    conflict = Signal(object)


class AnalysisModel(QObject):
    """Start analysis on tracks or folders; results appear through ``resultsChanged``."""

    resultsChanged = Signal(list)
    noticeRaised = Signal(str)
    conflictFound = Signal(object)

    def __init__(
        self,
        library: LibraryRepository,
        service: AnalysisService,
        jobs: JobService,
        settings: AnalysisSettingsModel,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._library = library
        self._service = service
        self._jobs = jobs
        self._settings = settings
        self._pending_ids: set[str] = set()
        self._pending_lock = threading.Lock()
        self._bridge = _AnalysisBridge(self)
        self._bridge.trackDone.connect(self._on_track_done, Qt.ConnectionType.QueuedConnection)
        self._bridge.notice.connect(self.noticeRaised, Qt.ConnectionType.QueuedConnection)
        self._bridge.conflict.connect(self.conflictFound, Qt.ConnectionType.QueuedConnection)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(_REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._flush)

    @Slot(list, bool)
    def analyzeTracks(self, track_ids: list, force: bool) -> None:
        """Analyze these tracks; ``force`` redoes those that already have a result."""
        identities = [str(value) for value in track_ids if str(value)]
        if not identities:
            return
        label = "Analyze 1 track" if len(identities) == 1 else f"Analyze {len(identities)} tracks"
        self._submit(label, lambda: identities, bool(force))

    @Slot(str, str, bool)
    def analyzeTree(self, root_id: str, relative_folder: str, force: bool) -> None:
        """Analyze every track of a folder and of all the folders inside it."""
        name = relative_folder.rsplit("/", 1)[-1] if relative_folder else "library folder"
        self._submit(
            f"Analyze {name}",
            lambda: self._library.track_ids_in_tree(root_id, relative_folder),
            bool(force),
        )

    def _submit(self, label: str, resolve: Callable[[], list[str]], force: bool) -> None:
        settings: AnalysisSettings = self._settings.settings

        def task(context: JobContext) -> None:
            candidates = resolve()
            context.raise_if_cancelled()
            if not candidates:
                self._bridge.notice.emit("No audio track to analyze here.")
                return
            todo = self._service.pending(candidates, force=force)
            context.raise_if_cancelled()
            if not todo:
                self._bridge.notice.emit(
                    "Nothing to analyze: every track already has its result. "
                    "Use Re-analyze to compute them again."
                )
                return
            self._service.run_batch(
                todo,
                settings,
                is_cancelled=lambda: context.is_cancelled,
                report_progress=context.report_progress,
                report_items=context.report_items,
                report_failure=context.report_failure,
                on_track_done=self._bridge.trackDone.emit,
                on_conflict=self._bridge.conflict.emit,
                force=force,
            )

        self._jobs.submit(task, label=label)

    @Slot(str)
    def _on_track_done(self, track_id: str) -> None:
        with self._pending_lock:
            self._pending_ids.add(track_id)
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    @Slot()
    def _flush(self) -> None:
        with self._pending_lock:
            ids = sorted(self._pending_ids)
            self._pending_ids.clear()
        if ids:
            self.resultsChanged.emit(ids)

    def flush_now(self) -> None:
        """Publish pending results immediately instead of waiting for the timer."""
        self._refresh_timer.stop()
        self._flush()
