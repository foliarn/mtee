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
_ROOT_INDEX = QModelIndex()


class PlaybackQueueModel(QAbstractListModel):
    """Expose one row per queue entry, including missing sources."""

    rowsChanged = Signal()

    def __init__(self, service: PlayerService, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._rows: list[dict[str, Any]] = []
        service.queueChanged.connect(self.refresh)
        self.refresh()

    def roleNames(self) -> dict[int, QByteArray]:
        return {_DATA_ROLE: QByteArray(b"modelData")}

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        return (
            self._rows[index.row()]
            if role in (_DATA_ROLE, int(Qt.ItemDataRole.DisplayRole))
            else None
        )

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
        rows = self._service.queue_rows()
        if rows == self._rows:
            return
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()
        self.rowsChanged.emit()
