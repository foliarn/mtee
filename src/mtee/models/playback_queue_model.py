"""Observable queue rows for the current immutable playback snapshot."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    Signal,
)

from mtee.services.player_service import PlayerService

__all__ = ["PlaybackQueueModel"]

_DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_GROUP_ROLE = _DATA_ROLE + 1
_ROOT_INDEX = QModelIndex()


class PlaybackQueueModel(QAbstractListModel):
    """Expose one row per queue entry, including missing sources."""

    rowsChanged = Signal()

    def __init__(self, service: PlayerService, parent=None, *, upcoming_only: bool = False) -> None:
        super().__init__(parent)
        self._service = service
        self._upcoming_only = upcoming_only
        self._rows: list[dict[str, Any]] = []
        service.queueChanged.connect(self.refresh)
        self.refresh()

    def roleNames(self) -> dict[int, QByteArray]:
        return {_DATA_ROLE: QByteArray(b"modelData"), _GROUP_ROLE: QByteArray(b"queueGroup")}

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        if role == _GROUP_ROLE:
            return row.get("queueGroup", "")
        return row if role in (_DATA_ROLE, int(Qt.ItemDataRole.DisplayRole)) else None

    @Property(list, notify=rowsChanged)
    def trackIds(self) -> list[str]:
        return self.track_ids_snapshot()

    def track_ids_snapshot(self) -> list[str]:
        return [str(row["id"]) for row in self._rows]

    @Property(int, notify=rowsChanged)
    def count(self) -> int:
        return self.count_value()

    def count_value(self) -> int:
        return len(self._rows)

    def rows_snapshot(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]

    def refresh(self) -> None:
        rows = self._service.up_next() if self._upcoming_only else self._service.queue_rows()
        if self._upcoming_only:
            rows = _with_groups(rows)
        if rows == self._rows:
            return
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()
        self.rowsChanged.emit()


def _with_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark each upcoming row ``next`` or ``from`` for the sections of the queue view.

    ``next`` is the uninterrupted run of manually added occurrences that opens the queue;
    ``from`` is everything after it, including a manual occurrence the user moved there.
    """
    leading = True
    grouped = []
    for row in rows:
        leading = leading and row.get("origin") == "manual"
        grouped.append({**row, "queueGroup": "next" if leading else "from"})
    return grouped
