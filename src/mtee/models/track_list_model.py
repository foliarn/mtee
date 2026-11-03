"""Reusable list model for one folder tab, with an immutable visible order."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

__all__ = ["TrackListModel", "track_id_of_row"]

_DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_ROOT_INDEX = QModelIndex()


def track_id_of_row(row: Mapping[str, Any]) -> str:
    """Return the library track of a row: ``trackId`` of a playlist or plugin row, else ``id``."""
    return str(row["trackId"] if "trackId" in row else row.get("id", ""))


class TrackListModel(QAbstractListModel):
    """Keep row data in a Qt model while ListView/GridView recycle delegates.

    The rows given to ``replace`` are kept whole; the rows shown leave out the tracks that
    ``set_hidden_ids`` names (plan 125.3), and ``hiddenCount`` says how many were left out.
    """

    rowsChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._row_by_id: dict[str, int] = {}
        # Every row as it was given, hidden ones included, and the function that names the
        # track identifiers to hide (None hides nothing: no question is asked at all).
        self._source: list[dict[str, Any]] = []
        self._hidden_ids: Callable[[Sequence[str]], frozenset[str]] | None = None
        self._hidden_count = 0

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

    def row_for_id(self, identity: str) -> int:
        return self._row_by_id.get(identity, -1)

    @Slot(str, result=int)
    def rowForId(self, identity: str) -> int:
        """Expose the row lookup to QML while keeping a Python-style helper."""
        return self.row_for_id(identity)

    @Slot(list, bool, result=dict)
    def dragPayload(self, selected_ids: list, is_playlist: bool) -> dict[str, Any]:
        """Describe the selected rows in one call; iterating the lists from QML is quadratic."""
        selected = {str(identity) for identity in selected_ids}
        chosen = [row for row in self._rows if str(row["id"]) in selected]
        entry_ids: list[Any] = []
        track_ids: list[Any] = []
        for row in chosen:
            entry_id = row.get("entryId")
            if entry_id:
                entry_ids.append(entry_id)
            track_id = row.get("trackId") if is_playlist else row.get("id")
            if track_id:
                track_ids.append(track_id)
        first = chosen[0] if chosen else {}
        return {
            "entryIds": entry_ids,
            "trackIds": track_ids,
            "canAdd": len(track_ids) == len(chosen)
            and all(row.get("available") is not False for row in chosen),
            "count": len(chosen),
            "title": str(first.get("title") or ""),
            "artist": str(first.get("artist") or ""),
        }

    @Property(int, notify=rowsChanged)
    def count(self) -> int:
        return len(self._rows)

    @Property(int, notify=rowsChanged)
    def hiddenCount(self) -> int:
        """How many rows the filter leaves out; the meta line of the list says so."""
        return self._hidden_count

    def set_hidden_ids(self, hidden_ids: Callable[[Sequence[str]], frozenset[str]] | None) -> None:
        """Set the function that names the tracks to leave out, and apply it at once."""
        self._hidden_ids = hidden_ids
        self.refresh_filter()

    def refresh_filter(self, changed: Collection[str] | None = None) -> None:
        """Apply the filter again to the rows given last.

        With ``changed`` (track identifiers) the rows are asked again only when one of them is
        in this list; None asks again in every case.
        """
        if changed is not None and not any(track_id_of_row(row) in changed for row in self._source):
            return
        self._show(self._source)

    def source_rows_snapshot(self) -> list[dict[str, Any]]:
        """Return the rows as they were given, hidden ones included."""
        return [dict(row) for row in self._source]

    def replace(self, rows: list[dict[str, Any]]) -> None:
        self._source = [dict(row) for row in rows]
        self._show(self._source)

    def _show(self, rows: list[dict[str, Any]]) -> None:
        """Show ``rows`` less the hidden ones, numbered from 1, changing only what differs."""
        hidden: frozenset[str] = frozenset()
        if self._hidden_ids is not None and rows:
            hidden = self._hidden_ids([track_id_of_row(row) for row in rows])
        visible = [row for row in rows if track_id_of_row(row) not in hidden]
        if len(rows) - len(visible) != self._hidden_count:
            self._hidden_count = len(rows) - len(visible)
            self.rowsChanged.emit()
        numbered: list[dict[str, Any]] = []
        for index, row in enumerate(visible, start=1):
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
                    self.dataChanged.emit(
                        self.index(start, 0), self.index(previous, 0), [_DATA_ROLE]
                    )
                    start = row_index
                previous = row_index
            self.dataChanged.emit(self.index(start, 0), self.index(previous, 0), [_DATA_ROLE])
        self._row_by_id = {identity: index for index, identity in enumerate(target_ids)}
        self.rowsChanged.emit()
