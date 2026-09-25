"""Snapshot selected track UUIDs for file copy and move keyboard commands."""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

__all__ = ["FileClipboardModel"]


class FileClipboardModel(QObject):
    """Keep a file-operation selection separate from playlist assignments."""

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mode = ""
        self._track_ids: list[str] = []

    @Property(str, notify=changed)
    def mode(self) -> str:
        return self._mode

    @Property(list, notify=changed)
    def trackIds(self) -> list[str]:
        return list(self._track_ids)

    @Slot(list)
    def copySelection(self, track_ids: list) -> None:
        self._store("copy", track_ids)

    @Slot(list)
    def cutSelection(self, track_ids: list) -> None:
        self._store("move", track_ids)

    @Slot(list)
    def removeCompleted(self, track_ids: list) -> None:
        completed = {str(track_id) for track_id in track_ids}
        self._track_ids = [track_id for track_id in self._track_ids if track_id not in completed]
        if not self._track_ids:
            self._mode = ""
        self.changed.emit()

    def _store(self, mode: str, track_ids: list) -> None:
        unique_ids = dict.fromkeys(str(track_id) for track_id in track_ids if str(track_id))
        self._track_ids = list(unique_ids)
        self._mode = mode if self._track_ids else ""
        self.changed.emit()
