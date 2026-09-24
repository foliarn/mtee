"""Virtualized Qt list model for roots, folders and their direct tracks."""

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

from mtee.persistence.library_repository import LibraryRepository

__all__ = ["FolderTreeModel"]

_DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_ROOT_INDEX = QModelIndex()


class FolderTreeModel(QAbstractListModel):
    """Flatten only the expanded portion of the library tree for QML reuse."""

    rowsChanged = Signal()

    def __init__(self, library: LibraryRepository, parent=None) -> None:
        super().__init__(parent)
        self._library = library
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
    def snapshot(self) -> list[dict[str, Any]]:
        return self.rows_snapshot()

    def rows_snapshot(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]

    def refresh(self, expanded: set[str]) -> None:
        rows: list[dict[str, Any]] = []
        for root in self._library.roots():
            root_id = str(root["id"])
            root_key = f"root:{root_id}"
            folders = self._library.folders(root_id)
            children: dict[str, list[str]] = {}
            for folder in folders:
                if not folder:
                    continue
                parent = folder.rpartition("/")[0]
                children.setdefault(parent, []).append(folder)
            rows.append(
                {
                    "kind": "folder",
                    "id": root_key,
                    "name": root["name"],
                    "path": root["path"],
                    "depth": 0,
                    "expanded": root_key in expanded,
                    "hasChildren": True,
                    "availability": root["availability"],
                }
            )
            if root_key not in expanded:
                continue
            self._append_folder(rows, root, "", 1, expanded, children)
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()
        self.rowsChanged.emit()

    def _append_folder(
        self,
        rows: list[dict[str, Any]],
        root: dict[str, Any],
        relative: str,
        depth: int,
        expanded: set[str],
        children: dict[str, list[str]],
    ) -> None:
        root_id = str(root["id"])
        folder_id = f"folder:{root_id}/{relative}"
        direct_tracks = self._library.tracks_in_folder(root_id, relative)
        child_folders = sorted(children.get(relative, []), key=lambda item: (item.casefold(), item))
        if relative:
            rows.append(
                {
                    "kind": "folder",
                    "id": folder_id,
                    "name": relative.rsplit("/", 1)[-1],
                    "path": str(root["path"]),
                    "depth": depth,
                    "expanded": folder_id in expanded,
                    "hasChildren": bool(child_folders or direct_tracks),
                    "availability": root["availability"],
                }
            )
        if relative and folder_id not in expanded:
            return
        for child in child_folders:
            self._append_folder(rows, root, child, depth + 1, expanded, children)
        for track in direct_tracks:
            rows.append(
                {
                    "kind": "track",
                    "id": track["id"],
                    "name": track["title"],
                    "depth": depth + 1,
                    "expanded": False,
                    "hasChildren": False,
                    "folder": folder_id,
                    "status": track["status"],
                }
            )
