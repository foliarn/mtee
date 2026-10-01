"""Watch the folders on display and report changes once they settle."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from PySide6.QtCore import QDir, QFileSystemWatcher, QObject, QTimer, Signal

__all__ = ["MAX_WATCHED", "SETTLE_MS", "FolderWatchService"]

_log = logging.getLogger(__name__)

MAX_WATCHED = 32
SETTLE_MS = 1_200


class FolderWatchService(QObject):
    """Wrap ``QFileSystemWatcher`` with a per-folder settling delay and a cap.

    Copying a file fires several events; ``folderChanged`` is emitted once, after
    ``SETTLE_MS`` without a new event for that folder. Lives on the graphical thread.
    """

    folderChanged = Signal(str)  # noqa: N815

    def __init__(self, parent: QObject | None = None, *, settle_ms: int = SETTLE_MS) -> None:
        super().__init__(parent)
        self._settle_ms = settle_ms
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)
        self._timers: dict[str, QTimer] = {}

    def watched(self) -> list[str]:
        return [QDir.cleanPath(path) for path in self._watcher.directories()]

    def set_watched(self, paths: Iterable[str]) -> None:
        wanted = list(dict.fromkeys(QDir.cleanPath(path) for path in paths))[:MAX_WATCHED]
        current = {QDir.cleanPath(path) for path in self._watcher.directories()}
        stale = [path for path in current if path not in wanted]
        if stale:
            self._watcher.removePaths(stale)
        for path in stale:
            self._drop_timer(path)
        for path in wanted:
            if path in current:
                continue
            if not self._watcher.addPath(path):
                _log.debug("Folder cannot be watched: %s", path)

    def close(self) -> None:
        directories = self._watcher.directories()
        if directories:
            self._watcher.removePaths(directories)
        for path in list(self._timers):
            self._drop_timer(path)

    def _on_directory_changed(self, path: str) -> None:
        timer = self._timers.get(path)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(self._settle_ms)
            timer.timeout.connect(lambda path=path: self._settled(path))
            self._timers[path] = timer
        timer.start()

    def _settled(self, path: str) -> None:
        self.folderChanged.emit(path)

    def _drop_timer(self, path: str) -> None:
        timer = self._timers.pop(path, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
