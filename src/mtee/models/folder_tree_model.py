"""Virtualized Qt tree over root and folder branches prepared by workers."""

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

__all__ = ["FolderTreeModel"]

_DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_ROOT_INDEX = QModelIndex()


class FolderTreeModel(QAbstractListModel):
    """Flatten only expanded cached branches; repository access stays in workers."""

    rowsChanged = Signal()
    rowsAboutToChange = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._roots: list[dict[str, Any]] = []
        self._branches: dict[str, list[dict[str, Any]]] = {}
        self._expanded: set[str] = set()
        self._loading: set[str] = set()
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
    def snapshot(self) -> list[dict[str, Any]]:
        return self.rows_snapshot()

    def rows_snapshot(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]

    def row_for_id(self, identity: str) -> int:
        return self._row_by_id.get(identity, -1)

    def set_roots(self, roots: list[dict[str, Any]]) -> None:
        self._roots = [dict(root) for root in roots]
        known = {f"root:{root.get('id', '')}" for root in self._roots}
        self._expanded = {
            folder_id for folder_id in self._expanded if _root_key(folder_id) in known
        }
        self._branches = {
            folder_id: rows
            for folder_id, rows in self._branches.items()
            if _root_key(folder_id) in known
        }
        self._loading = {folder_id for folder_id in self._loading if _root_key(folder_id) in known}
        self._rebuild()

    def set_expanded(self, folder_id: str, expanded: bool) -> None:
        if expanded:
            self._expanded.add(folder_id)
        else:
            self._expanded.discard(folder_id)
            self._loading.discard(folder_id)
        self._rebuild()

    def is_expanded(self, folder_id: str) -> bool:
        return folder_id in self._expanded

    def branch_loaded(self, folder_id: str) -> bool:
        return folder_id in self._branches

    def set_loading(self, folder_id: str, loading: bool) -> None:
        if loading:
            self._loading.add(folder_id)
        else:
            self._loading.discard(folder_id)
        self._rebuild()

    def set_branch(self, folder_id: str, rows: list[dict[str, Any]]) -> None:
        self._branches[folder_id] = [dict(row) for row in rows]
        self._loading.discard(folder_id)
        self._rebuild()

    def invalidate_branch(self, folder_id: str) -> None:
        self._branches.pop(folder_id, None)
        if folder_id in self._expanded:
            self._loading.add(folder_id)
        self._rebuild()

    def invalidate_all_branches(self) -> None:
        self._branches.clear()
        self._loading = set(self._expanded)
        self._rebuild()

    def _rebuild(self) -> None:
        rows: list[dict[str, Any]] = []
        for root in self._roots:
            root_id = str(root["id"])
            root_key = f"root:{root_id}"
            rows.append(
                {
                    "kind": "folder",
                    "id": root_key,
                    "rootId": root_id,
                    "name": str(root["name"]),
                    "path": str(root["path"]),
                    "depth": 0,
                    "expanded": root_key in self._expanded,
                    "hasChildren": True,
                    "availability": str(root["availability"]),
                }
            )
            if root_key in self._expanded:
                self._append_branch(rows, root_key, 1)
        self._replace(rows)

    def _append_branch(self, rows: list[dict[str, Any]], branch_key: str, depth: int) -> None:
        if branch_key in self._loading:
            rows.append(
                {
                    "kind": "loading",
                    "id": f"loading:{branch_key}",
                    "name": "Loading…",
                    "depth": depth,
                    "hasChildren": False,
                }
            )
        for child in self._branches.get(branch_key, []):
            item = {**child, "depth": depth}
            if item.get("kind") == "folder":
                item["expanded"] = str(item["id"]) in self._expanded
            rows.append(item)
            child_id = str(item.get("id", ""))
            if item.get("kind") == "folder" and child_id in self._expanded:
                self._append_branch(rows, child_id, depth + 1)

    def _replace(self, rows: list[dict[str, Any]]) -> None:
        target_rows = [dict(row) for row in rows]
        if target_rows == self._rows:
            return

        self.rowsAboutToChange.emit()
        new_ids = [str(row["id"]) for row in target_rows]
        new_set = set(new_ids)
        removed_ranges = []
        cursor = len(self._rows) - 1
        while cursor >= 0:
            if str(self._rows[cursor]["id"]) in new_set:
                cursor -= 1
                continue
            last = cursor
            while cursor >= 0 and str(self._rows[cursor]["id"]) not in new_set:
                cursor -= 1
            removed_ranges.append((cursor + 1, last))
        for first, last in removed_ranges:
            self.beginRemoveRows(_ROOT_INDEX, first, last)
            del self._rows[first : last + 1]
            self.endRemoveRows()

        inserted = False
        moved = False
        for target_index, target in enumerate(target_rows):
            identity = str(target["id"])
            if target_index < len(self._rows) and str(self._rows[target_index]["id"]) == identity:
                continue

            source_index = next(
                (
                    index
                    for index in range(target_index + 1, len(self._rows))
                    if str(self._rows[index]["id"]) == identity
                ),
                -1,
            )
            if source_index < 0:
                self.beginInsertRows(_ROOT_INDEX, target_index, target_index)
                self._rows.insert(target_index, dict(target))
                self.endInsertRows()
                inserted = True
                continue

            if not self.beginMoveRows(
                _ROOT_INDEX, source_index, source_index, _ROOT_INDEX, target_index
            ):
                raise RuntimeError("Could not move a folder tree row to its target position.")
            self._rows.insert(target_index, self._rows.pop(source_index))
            self.endMoveRows()
            moved = True

        changed = []
        target_by_id = {str(row["id"]): row for row in target_rows}
        for row_index, current in enumerate(self._rows):
            target = target_by_id[str(current["id"])]
            if current != target:
                self._rows[row_index] = dict(target)
                changed.append(row_index)
        if changed:
            start = previous = changed[0]
            for row_index in changed[1:]:
                if row_index != previous + 1:
                    self.dataChanged.emit(
                        self.index(start, 0), self.index(previous, 0), [_DATA_ROLE]
                    )
                    start = row_index
                previous = row_index
            self.dataChanged.emit(self.index(start, 0), self.index(previous, 0), [_DATA_ROLE])
        if removed_ranges or inserted or changed or moved:
            self._row_by_id = {identity: index for index, identity in enumerate(new_ids)}
            self.rowsChanged.emit()


def _root_key(folder_id: str) -> str:
    if folder_id.startswith("root:"):
        return folder_id
    if folder_id.startswith("folder:"):
        return "root:" + folder_id.partition(":")[2].partition("/")[0]
    if folder_id.startswith("loading:root:"):
        return folder_id.removeprefix("loading:")
    if folder_id.startswith("loading:folder:"):
        return _root_key(folder_id.removeprefix("loading:"))
    return ""
