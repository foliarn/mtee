"""The status bar under the player bar: the items that plugins show, as the QML reads them.

A plugin declares at most one ``StatusItem`` and fills it with ``PluginContext.status_item``.
``StatusBarModel`` keeps the declared items in plugin load order and lists one row per item that
has a state. With no row the bar is not drawn. The model is changed on the graphical thread only:
``PluginHost`` queues every plugin call there. A click runs the plugin's ``on_click`` inside a
guard, so a failure is logged and announced once, as the other plugin failures are.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from mtee.plugins.api import StatusItem
from mtee.plugins.loader import LoadedPlugin, PluginStatus

__all__ = ["STATUS_TONES", "StatusBarModel", "StatusState", "make_status_state"]

_LOGGER = logging.getLogger(__name__)
STATUS_TONES = ("neutral", "secondary", "warning")
# The roles, in order; QML reads them by name (``model.text``, ``model.progress``...).
_ROLES = ("itemId", "pluginId", "text", "tone", "progress", "tooltip", "icon", "clickable")
_FIRST_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_ROOT_INDEX = QModelIndex()


@dataclass(frozen=True, slots=True)
class StatusState:
    """What a plugin shows in its item: text, tone, progress (0..1 or None), tooltip and icon."""

    text: str
    tone: str
    progress: float | None
    tooltip: str
    icon: str | None


def make_status_state(
    text: str,
    tone: str = "neutral",
    progress: float | None = None,
    tooltip: str = "",
    icon: str | None = None,
) -> StatusState:
    """Check what a plugin passes to ``status_item.update`` and return it as a state.

    Raises ``TypeError`` or ``ValueError`` with a readable reason; the caller is the plugin.
    """
    if not isinstance(text, str):
        raise TypeError("The text of a status item must be a string.")
    if tone not in STATUS_TONES:
        raise ValueError(f"The tone {tone!r} of a status item is not one of {STATUS_TONES}.")
    if progress is not None:
        valid = (
            isinstance(progress, int | float)
            and not isinstance(progress, bool)
            and math.isfinite(progress)
            and 0.0 <= progress <= 1.0
        )
        if not valid:
            raise ValueError("The progress of a status item is a number from 0 to 1, or None.")
        progress = float(progress)
    if not isinstance(tooltip, str):
        raise TypeError("The tooltip of a status item must be a string.")
    if icon is not None and (not isinstance(icon, str) or not icon.strip()):
        raise ValueError("The icon of a status item must be the name of an icon.")
    return StatusState(text, tone, progress, tooltip, icon)


@dataclass(frozen=True, slots=True)
class _Declared:
    """A ``StatusItem`` with the plugin that declares it."""

    plugin_id: str
    plugin_title: str
    item: StatusItem


class StatusBarModel(QAbstractListModel):
    """The visible status items, in plugin load order; one row per item that has a state."""

    countChanged = Signal()
    noticeRaised = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # Declared items in plugin load order; the states of any plugin, declared or not yet.
        self._declared: dict[str, _Declared] = {}
        self._states: dict[str, StatusState] = {}
        self._rows: list[str] = []  # plugin ids of the visible items, in order
        self._reported: set[str] = set()

    # ------------------------------------------------------------------ registration

    def register(self, plugins: Sequence[LoadedPlugin]) -> None:
        """Take the status items of the plugins that run; the others contribute nothing."""
        declared: dict[str, _Declared] = {}
        for record in plugins:
            if record.status is not PluginStatus.RUNNING:
                continue
            for contribution in record.contributions:
                if isinstance(contribution, StatusItem):
                    declared[record.plugin_id] = _Declared(
                        record.plugin_id, record.title, contribution
                    )
        self._declared = declared
        self.beginResetModel()
        self._rows = [plugin_id for plugin_id in declared if plugin_id in self._states]
        self.endResetModel()
        self.countChanged.emit()

    # ------------------------------------------------------------------ changes (graphical thread)

    def set_state(self, plugin_id: str, state: StatusState | None) -> None:
        """Show ``state`` as the item of ``plugin_id``, or hide the item when ``state`` is None."""
        if state is None:
            self._states.pop(plugin_id, None)
        else:
            self._states[plugin_id] = state
        if plugin_id not in self._declared:
            return
        row = self._rows.index(plugin_id) if plugin_id in self._rows else -1
        if state is None:
            if row >= 0:
                self.beginRemoveRows(_ROOT_INDEX, row, row)
                del self._rows[row]
                self.endRemoveRows()
                self.countChanged.emit()
        elif row >= 0:
            index = self.index(row, 0)
            self.dataChanged.emit(index, index)
        else:
            position = self._position_of(plugin_id)
            self.beginInsertRows(_ROOT_INDEX, position, position)
            self._rows.insert(position, plugin_id)
            self.endInsertRows()
            self.countChanged.emit()

    def _position_of(self, plugin_id: str) -> int:
        """Return the row of a new item: after the visible items that load before it."""
        order = list(self._declared)
        wanted = order.index(plugin_id)
        return sum(1 for shown in self._rows if order.index(shown) < wanted)

    # ------------------------------------------------------------------ the model

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            _FIRST_ROLE + offset: QByteArray(name.encode()) for offset, name in enumerate(_ROLES)
        }

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        plugin_id = self._rows[index.row()]
        declared = self._declared[plugin_id]
        state = self._states[plugin_id]
        values: dict[str, Any] = {
            "itemId": declared.item.item_id,
            "pluginId": plugin_id,
            "text": state.text,
            "tone": state.tone,
            "progress": -1.0 if state.progress is None else state.progress,
            "tooltip": state.tooltip,
            "icon": state.icon or declared.item.icon,
            "clickable": declared.item.on_click is not None,
        }
        offset = role - _FIRST_ROLE
        return values[_ROLES[offset]] if 0 <= offset < len(_ROLES) else None

    @Property(int, notify=countChanged)
    def count(self) -> int:
        """How many items are shown; the bar is drawn only while this is above zero."""
        return len(self._rows)

    @Slot(int)
    def activate(self, row: int) -> None:
        """The user clicked the item of ``row``: run its ``on_click`` on the graphical thread."""
        if not 0 <= row < len(self._rows):
            return
        declared = self._declared[self._rows[row]]
        on_click = declared.item.on_click
        if on_click is None:
            return
        self._guard(declared.plugin_title, "clicking a status item", on_click)

    def _guard(self, plugin_title: str, what: str, call: Callable[[], None]) -> None:
        """Run a function of a plugin; a failure is logged and announced once."""
        try:
            call()
        except Exception as error:
            _LOGGER.error("Plugin %s failed while %s.", plugin_title, what, exc_info=error)
            marker = f"{plugin_title}:{what}"
            if marker not in self._reported:
                self._reported.add(marker)
                self.noticeRaised.emit(f"The plugin {plugin_title} failed while {what}: {error}")
