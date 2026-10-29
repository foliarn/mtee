"""A small list model of dictionaries, for the rows a plugin shows in a sidebar section or foot."""

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

__all__ = ["PluginRowsModel"]

_DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_ROOT_INDEX = QModelIndex()


class PluginRowsModel(QAbstractListModel):
    """Rows of plain values, read in QML as ``modelData``.

    A sidebar section row has ``id`` and ``name`` and may have ``depth`` (0 by default),
    ``kind`` (``"item"`` or ``"group"``), ``expanded`` (a group, ``True`` by default),
    ``icon`` (an icon name of the core) with ``tone`` (``"secondary"`` for the pink accent),
    ``badge`` (a count in the accent colour) and ``count`` (a muted text on the right).
    A foot row has ``text`` and ``tone`` (``"secondary"``, ``"muted"`` or ``"warning"``).
    ``replace`` may be called from the graphical thread only.
    """

    rowsChanged = Signal()

    def __init__(self, rows: list[dict[str, Any]] | None = None, parent: Any = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = [dict(row) for row in rows or ()]

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

    @Property(int, notify=rowsChanged)
    def count(self) -> int:
        return len(self._rows)

    @Property(list, notify=rowsChanged)
    def items(self) -> list[dict[str, Any]]:
        """The rows as one list, for the QML that folds groups."""
        return self.rows()

    def rows(self) -> list[dict[str, Any]]:
        """Return a copy of the rows."""
        return [dict(row) for row in self._rows]

    def replace(self, rows: list[dict[str, Any]]) -> None:
        """Show ``rows`` instead of the current ones; nothing is emitted when they are equal."""
        wanted = [dict(row) for row in rows]
        if wanted == self._rows:
            return
        self.beginResetModel()
        self._rows = wanted
        self.endResetModel()
        self.rowsChanged.emit()
