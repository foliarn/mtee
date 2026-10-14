"""List of tracks whose calculated tags wait for the user's choice to replace old ones.

The list is filled when an analysis could not write a field that its file stores under
several tag names. Nothing is written until the user asks; replacing runs as a task,
one track at a time, and the entry disappears once the file has been verified.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from mtee.domain.jobs import JobCancelledError
from mtee.domain.tag_conflicts import TagConflict
from mtee.services.jobs import JobContext, JobService

__all__ = ["TagConflictRole", "TagConflictsModel"]


class TagConflictRole(IntEnum):
    """Roles exposed to QML."""

    TRACK_ID = int(Qt.ItemDataRole.UserRole) + 1
    FILE_NAME = int(Qt.ItemDataRole.UserRole) + 2
    SUMMARY = int(Qt.ItemDataRole.UserRole) + 3
    STATE = int(Qt.ItemDataRole.UserRole) + 4
    ERROR_MESSAGE = int(Qt.ItemDataRole.UserRole) + 5


class _Bridge(QObject):
    """Carry the end of a replacement from its worker thread to the graphical thread."""

    finished = Signal(str, str)


class TagConflictsModel(QAbstractListModel):
    """Conflicts waiting to be resolved, newest first."""

    countChanged = Signal()
    resolved = Signal(list)
    noticeRaised = Signal(str)

    def __init__(
        self,
        jobs: JobService | None = None,
        resolver: Callable[[TagConflict], str] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._jobs = jobs
        self._resolver = resolver
        self._conflicts: list[TagConflict] = []
        self._states: dict[str, str] = {}
        self._errors: dict[str, str] = {}
        self._bridge = _Bridge(self)
        self._bridge.finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)

    # ------------------------------------------------------------------ model

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._conflicts)

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            int(TagConflictRole.TRACK_ID): QByteArray(b"trackId"),
            int(TagConflictRole.FILE_NAME): QByteArray(b"fileName"),
            int(TagConflictRole.SUMMARY): QByteArray(b"summary"),
            int(TagConflictRole.STATE): QByteArray(b"conflictState"),
            int(TagConflictRole.ERROR_MESSAGE): QByteArray(b"errorMessage"),
        }

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ):
        if not index.isValid() or not 0 <= index.row() < len(self._conflicts):
            return None
        conflict = self._conflicts[index.row()]
        match role:
            case TagConflictRole.TRACK_ID:
                return conflict.track_id
            case TagConflictRole.FILE_NAME | Qt.ItemDataRole.DisplayRole:
                return conflict.file_name
            case TagConflictRole.SUMMARY:
                return conflict.summary
            case TagConflictRole.STATE:
                return self._states.get(conflict.track_id, "pending")
            case TagConflictRole.ERROR_MESSAGE:
                return self._errors.get(conflict.track_id, "")
            case _:
                return None

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._conflicts)

    # ---------------------------------------------------------------- actions

    @Slot(object)
    def add(self, conflict: object) -> None:
        """Record a conflict; a newer one for the same track replaces the older."""
        if not isinstance(conflict, TagConflict) or not conflict.entries:
            return
        row = self._row_of(conflict.track_id)
        if row is not None and self._states.get(conflict.track_id) == "working":
            return
        self._errors.pop(conflict.track_id, None)
        self._states[conflict.track_id] = "pending"
        if row is None:
            self.beginInsertRows(QModelIndex(), 0, 0)
            self._conflicts.insert(0, conflict)
            self.endInsertRows()
        else:
            self._conflicts[row] = conflict
            self._changed(row)
        self.countChanged.emit()
        count = len(self._conflicts)
        self.noticeRaised.emit(
            f"{count} track{'s' if count != 1 else ''} with tags stored under several names. "
            "Open Tasks to replace the old values."
        )

    @Slot(str)
    def resolve(self, track_id: str) -> None:
        """Delete the old names and values of one track and write the new ones."""
        row = self._row_of(track_id)
        if row is None or self._states.get(track_id) == "working":
            return
        if self._jobs is None or self._resolver is None:
            return
        conflict = self._conflicts[row]
        resolver = self._resolver
        self._states[track_id] = "working"
        self._errors.pop(track_id, None)
        self._changed(row)

        def task(context: JobContext) -> None:
            try:
                context.raise_if_cancelled()
                message = resolver(conflict)
            except JobCancelledError as error:
                # Free the row for a retry, then let the job end as cancelled, not failed.
                self._bridge.finished.emit(track_id, f"{type(error).__name__}: {error}")
                raise
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
            self._bridge.finished.emit(track_id, message)
            if message:
                raise RuntimeError(message)

        self._jobs.submit(task, label=f"Replace tags: {conflict.file_name}")

    @Slot()
    def resolveAll(self) -> None:
        for conflict in list(self._conflicts):
            self.resolve(conflict.track_id)

    @Slot(str)
    def dismiss(self, track_id: str) -> None:
        """Forget a conflict without writing anything."""
        row = self._row_of(track_id)
        if row is None or self._states.get(track_id) == "working":
            return
        self._remove(row)

    @Slot()
    def dismissAll(self) -> None:
        for conflict in list(self._conflicts):
            self.dismiss(conflict.track_id)

    # --------------------------------------------------------------- internals

    @Slot(str, str)
    def _on_finished(self, track_id: str, message: str) -> None:
        row = self._row_of(track_id)
        if row is None:
            return
        if message:
            self._states[track_id] = "error"
            self._errors[track_id] = message
            self._changed(row)
            return
        self._remove(row)
        self.resolved.emit([track_id])

    def _remove(self, row: int) -> None:
        track_id = self._conflicts[row].track_id
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._conflicts[row]
        self.endRemoveRows()
        self._states.pop(track_id, None)
        self._errors.pop(track_id, None)
        self.countChanged.emit()

    def _changed(self, row: int) -> None:
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, list(self.roleNames().keys()))

    def _row_of(self, track_id: str) -> int | None:
        for row, conflict in enumerate(self._conflicts):
            if conflict.track_id == track_id:
                return row
        return None
