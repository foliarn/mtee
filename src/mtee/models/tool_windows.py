"""Registry of the tool windows: the buttons of the left and right bars and their panes.

A tool window is an entry of the registry: core windows (Explorer, Playlists...) and the
windows of plugins (``PluginActivity``) are listed here, and the bars and the docks read the
list. The registry holds no pane; the QML side chooses the pane by ``id``.

Each entry is a dict with the keys ``id``, ``title``, ``icon``, ``side`` (``left`` or
``right``), ``place`` (``top`` or ``bottom`` of its bar), ``kind`` (``window`` opens a pane,
``action`` runs a slot), ``badge`` (a count, 0 when hidden), ``tip``, ``shortcut`` and
``owner`` (``""`` for MTEE, the plugin id otherwise).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.plugins.registry import plugin_ui_enabled

__all__ = ["ToolWindowRegistry", "core_tool_windows", "tool_window_entries"]

# The left windows that have an Alt+number shortcut, in bar order.
LEFT_NUMBER_SHORTCUTS = 5

SIDES = ("left", "right")


def _entry(
    window_id: str,
    title: str,
    icon: str,
    side: str,
    place: str,
    *,
    kind: str = "window",
    owner: str = "",
    tip: str = "",
    shortcut: str = "",
) -> dict[str, Any]:
    return {
        "id": window_id,
        "title": title,
        "icon": icon,
        "side": side,
        "place": place,
        "kind": kind,
        "badge": 0,
        "tip": tip or title,
        "shortcut": shortcut,
        "owner": owner,
    }


def core_tool_windows(*, convert_enabled: bool) -> list[dict[str, Any]]:
    """The MTEE tool windows in bar order (the Convert window only when its plugin is on)."""
    entries = [
        _entry("explorer", "Explorer", "explorer", "left", "top", shortcut="Ctrl+Shift+E"),
        _entry("playlists", "Playlists", "playlists", "left", "top"),
        _entry("artists", "Artists", "artists", "left", "top"),
    ]
    if convert_enabled:
        entries.append(_entry("convert", "Convert", "convert", "left", "top"))
    entries.append(_entry("plugins", "Plugins", "plugins", "left", "bottom"))
    entries.extend(
        [
            _entry("info", "Info", "info", "right", "top", shortcut="Ctrl+I"),
            _entry("queue", "Queue", "queue", "right", "top", shortcut="Alt+Q"),
            _entry("history", "History", "history", "right", "top", shortcut="Alt+H"),
            _entry(
                "settings",
                "Settings",
                "settings",
                "right",
                "bottom",
                kind="action",
                shortcut="Ctrl+,",
            ),
        ]
    )
    return entries


def tool_window_entries(
    plugin_activities: Iterable[dict[str, str]], *, convert_enabled: bool
) -> list[dict[str, Any]]:
    """The core windows followed by the plugin windows, each plugin window in its own bar side.

    ``plugin_activities`` are the ``activities`` of the plugin UI model: ``id``, ``tip``,
    ``icon`` and ``side``. A plugin window goes to the top of its side, after the core ones.
    """
    entries = core_tool_windows(convert_enabled=convert_enabled)
    for activity in plugin_activities:
        side = activity.get("side", "left")
        if side not in SIDES:
            side = "left"
        owner = activity["id"].partition(".")[0]
        title = activity.get("tip", activity["id"])
        entries.append(
            _entry(
                activity["id"],
                title,
                activity.get("icon", ""),
                side,
                "top",
                owner=owner,
                tip=title,
            )
        )
    # Top windows of a bar come first, its bottom windows after; the order inside each group holds.
    ordered = sorted(entries, key=lambda entry: entry["place"] == "bottom")
    # Alt+1 to Alt+5 open the first five left windows in bar order (plan 131.10, P4).
    numbered = [entry for entry in ordered if entry["side"] == "left" and entry["kind"] == "window"]
    for number, entry in enumerate(numbered[:LEFT_NUMBER_SHORTCUTS], start=1):
        entry["shortcut"] = f"Alt+{number}"
    return ordered


class ToolWindowRegistry(QObject):
    """The tool windows of the running build, exposed to QML as ``toolWindows``."""

    changed = Signal()

    def __init__(self, plugin_ui: Any = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._plugin_ui = plugin_ui
        if plugin_ui is not None and hasattr(plugin_ui, "changed"):
            plugin_ui.changed.connect(self.changed.emit)

    def _current(self) -> list[dict[str, Any]]:
        plugin_activities: list[dict[str, str]] = []
        if self._plugin_ui is not None:
            plugin_activities = list(getattr(self._plugin_ui, "activities", []))
        return tool_window_entries(plugin_activities, convert_enabled=plugin_ui_enabled())

    @Property(list, notify=changed)
    def entries(self) -> list[dict[str, Any]]:
        return self._current()

    @Slot(str, result=str)
    def sideOf(self, window_id: str) -> str:
        """The bar side of a window, or an empty string when no such window exists."""
        return self.side_of(window_id) or ""

    def side_of(self, window_id: str) -> str | None:
        for entry in self._current():
            if entry["id"] == window_id:
                return str(entry["side"])
        return None

    def has(self, window_id: str) -> bool:
        return self.side_of(window_id) is not None

    def is_pane(self, window_id: str) -> bool:
        """Whether the window opens a pane in a dock (not an action such as Settings)."""
        return any(
            entry["id"] == window_id and entry["kind"] == "window" for entry in self._current()
        )
