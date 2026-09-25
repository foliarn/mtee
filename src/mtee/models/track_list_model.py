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
        numbered: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            item = dict(row)
            item["number"] = index
            numbered.append(item)
        if numbered == self._rows:
            return

        changed_rows: set[int] = set()
        for target_row, item in enumerate(numbered):
            if target_row < len(self._rows) and self._rows[target_row].get("id") == item.get("id"):
                if self._rows[target_row] != item:
                    self._rows[target_row] = item
                    changed_rows.add(target_row)
                continue

            source_row = next(
                (
                    index
                    for index in range(target_row + 1, len(self._rows))
                    if self._rows[index].get("id") == item.get("id")
                ),
                -1,
            )
            if source_row >= 0:
                destination = target_row if source_row > target_row else target_row + 1
                if self.beginMoveRows(
                    _ROOT_INDEX, source_row, source_row, _ROOT_INDEX, destination
                ):
                    moved = self._rows.pop(source_row)
                    self._rows.insert(target_row, moved)
                    self.endMoveRows()
                else:
                    raise RuntimeError("Qt refused to move a row in the track model.")
                self._rows[target_row] = item
                changed_rows.add(target_row)
                continue

            self.beginInsertRows(_ROOT_INDEX, target_row, target_row)
            self._rows.insert(target_row, item)
            self.endInsertRows()

        if len(self._rows) > len(numbered):
            first_removed = len(numbered)
            last_removed = len(self._rows) - 1
            self.beginRemoveRows(_ROOT_INDEX, first_removed, last_removed)
            del self._rows[first_removed:]
            self.endRemoveRows()

        for row in sorted(changed_rows):
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [_DATA_ROLE])
        self.rowsChanged.emit()
