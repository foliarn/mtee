"""Reusable list model for one folder tab, with an immutable visible order."""

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

__all__ = ["TrackListModel"]

_DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_ROOT_INDEX = QModelIndex()


class TrackListModel(QAbstractListModel):
    """Keep row data in a Qt model while ListView/GridView recycle delegates."""

    rowsChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

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
        return len(self._rows)

    def replace(self, rows: list[dict[str, Any]]) -> None:
        numbered = []
        for index, row in enumerate(rows, start=1):
            item = dict(row)
            item["number"] = index
            numbered.append(item)
        if numbered == self._rows:
            return
        self.beginResetModel()
        self._rows = numbered
        self.endResetModel()
        self.rowsChanged.emit()
