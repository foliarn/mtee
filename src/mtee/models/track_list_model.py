"""Reusable list model for one folder tab, with an immutable visible order."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QPersistentModelIndex,
    Slot,
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
        self._row_by_id: dict[str, int] = {}

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

    @Property(list, notify=rowsChanged)
    def rows(self) -> list[dict[str, Any]]:
        return self.rows_snapshot()

    def track_ids_snapshot(self) -> list[str]:
        return [str(row["id"]) for row in self._rows]

    def rows_snapshot(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]

    @Slot(str, result=int)
    def rowForId(self, identity: str) -> int:
        return self._row_by_id.get(identity, -1)

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
        target_ids = [str(row["id"]) for row in numbered]
        target_set = set(target_ids)
        removed_ranges = []
        cursor = len(self._rows) - 1
        while cursor >= 0:
            if str(self._rows[cursor]["id"]) in target_set:
                cursor -= 1
                continue
            last = cursor
            while cursor >= 0 and str(self._rows[cursor]["id"]) not in target_set:
                cursor -= 1
            removed_ranges.append((cursor + 1, last))
        for first, last in removed_ranges:
            self.beginRemoveRows(_ROOT_INDEX, first, last)
            del self._rows[first : last + 1]
            self.endRemoveRows()

        current_ids = {str(row["id"]) for row in self._rows}
        additions = [row for row in numbered if str(row["id"]) not in current_ids]
        if additions:
            first = len(self._rows)
            self.beginInsertRows(_ROOT_INDEX, first, first + len(additions) - 1)
            self._rows.extend(dict(row) for row in additions)
            self.endInsertRows()

        old_ids = [str(row["id"]) for row in self._rows]
        reordered = old_ids != target_ids
        if reordered:
            persistent = self.persistentIndexList()
            persistent_ids = [str(self._rows[index.row()]["id"]) for index in persistent]
            self.layoutAboutToBeChanged.emit()
            rows_by_id = {str(row["id"]): row for row in self._rows}
            self._rows = [rows_by_id[identity] for identity in target_ids]
            new_rows = {identity: index for index, identity in enumerate(target_ids)}
            self.changePersistentIndexList(
                persistent, [self.index(new_rows[identity], 0) for identity in persistent_ids]
            )
            self.layoutChanged.emit()

        changed_rows = []
        targets = {str(row["id"]): row for row in numbered}
        for row_index, current in enumerate(self._rows):
            target = targets[str(current["id"])]
            if current != target:
                self._rows[row_index] = dict(target)
                changed_rows.append(row_index)
        if changed_rows:
            start = previous = changed_rows[0]
            for row_index in changed_rows[1:]:
                if row_index != previous + 1:
                    self.dataChanged.emit(self.index(start, 0), self.index(previous, 0), [_DATA_ROLE])
                    start = row_index
                previous = row_index
            self.dataChanged.emit(self.index(start, 0), self.index(previous, 0), [_DATA_ROLE])
        self._row_by_id = {identity: index for index, identity in enumerate(target_ids)}
        self.rowsChanged.emit()
