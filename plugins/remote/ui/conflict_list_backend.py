"""What the list of every conflict reads (the ``remote.conflicts`` tab, review of 0.3.0).

The bell and the Remote window show the oldest conflicts and one row that opens this list. The rows
are built in a hidden job (a title per track is read from the library), then ``rows`` changes. The
list is read again when the conflicts change, while a tab asked for it at least once. ``open(id)``
opens the tab of one conflict. Graphical thread only.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.plugins.api import PluginContext

from ..conflicts import TAB_KIND, ConflictFeature
from ..tasks import submit


class ConflictListBackend(QObject):
    """The backend of the ``remote.conflicts`` tab."""

    changed = Signal()

    def __init__(self, context: PluginContext, feature: ConflictFeature) -> None:
        super().__init__()
        self._context = context
        self._feature = feature
        self._rows: list[dict[str, Any]] = []
        self._loading = False
        self._wanted = False
        self._again = False
        feature.model.rowsChanged.connect(self._on_conflicts_changed)

    @Property(list, notify=changed)
    def rows(self) -> list[dict[str, Any]]:
        return list(self._rows)

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Slot()
    def load(self) -> None:
        """Build the rows in a job; a request made while one runs runs once more after it."""
        self._wanted = True
        if self._loading:
            self._again = True
            return
        self._loading = True
        self.changed.emit()
        submit(
            self._context,
            "Listing the remote conflicts",
            lambda _job: self._feature.list_rows(),
            self._on_rows,
            visible=False,
        )

    @Slot(str)
    def open(self, conflict_id: str) -> None:
        self._context.open_tab(TAB_KIND, conflict_id)

    def _on_rows(self, rows: list[dict[str, Any]] | None, error: BaseException | None) -> None:
        self._loading = False
        if error is not None:
            self._context.log.warning("Listing the remote conflicts failed: %s", error)
        elif rows is not None:
            self._rows = rows
        self.changed.emit()
        if self._again:
            self._again = False
            self.load()

    def _on_conflicts_changed(self) -> None:
        if self._wanted:
            self.load()
