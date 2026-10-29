"""Columns that plugins add to the track lists: their keys, saved layout and cell values.

A plugin column is identified in the table by ``"<plugin_id>.<column_id>"``. The layout of a
list (order, hidden columns, widths) is stored like the layout of the core columns: for local
playlists in the playlist preferences, for a plugin tab kind in the application settings.
A column the layout has never mentioned follows ``TrackColumn.default_visible_for``; once the
user shows or hides it, the layout holds the choice.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from mtee.domain.playlists import is_plugin_column_key
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import TrackColumn

__all__ = [
    "PluginColumnStore",
    "RegisteredColumn",
    "column_options",
    "decorate_rows",
    "effective_hidden",
    "is_plugin_column_key",
    "toggled_columns",
]

_LOGGER = logging.getLogger(__name__)

SETTINGS_PREFIX = "tabs.columns."
# What a plugin track list shows by default besides the plugin columns.
_DEFAULT_ORDER = ["title", "artist", "album", "bpm", "key", "duration"]
_DEFAULT_HIDDEN = ["bpm", "key"]
_DEFAULT_WIDTHS = {"title": 0, "artist": 150, "album": 150, "bpm": 52, "key": 52, "duration": 70}
_MIN_WIDTH = 44
_MAX_WIDTH = 640


@dataclass(frozen=True, slots=True)
class RegisteredColumn:
    """A plugin column with the plugin that provides it."""

    key: str
    plugin_id: str
    plugin_title: str
    column: TrackColumn


def column_options(columns: Iterable[RegisteredColumn]) -> list[dict[str, Any]]:
    """The entries the column picker adds, with the plugin name shown on the right."""
    return [
        {
            "key": item.key,
            "label": item.column.title,
            "plugin": item.plugin_title,
            "width": item.column.width,
        }
        for item in columns
    ]


def effective_hidden(
    preferences: Mapping[str, Any], columns: Iterable[RegisteredColumn], kind: str
) -> list[str]:
    """The hidden columns of a layout, plus the unmentioned plugin columns that start hidden."""
    order = list(preferences.get("order", []))
    hidden = list(preferences.get("hidden", []))
    for item in columns:
        if (
            item.key not in order
            and item.key not in hidden
            and kind not in item.column.default_visible_for
        ):
            hidden.append(item.key)
    return hidden


def toggled_columns(
    preferences: Mapping[str, Any],
    columns: Collection[RegisteredColumn],
    kind: str,
    key: str,
) -> dict[str, Any]:
    """Return the layout with the visibility of the plugin column ``key`` reversed."""
    result = dict(preferences)
    order = list(preferences.get("order", []))
    hidden = effective_hidden(preferences, columns, kind)
    if key not in order:
        order.append(key)
    if key in hidden:
        hidden.remove(key)
    else:
        hidden.append(key)
    result["order"] = order
    result["hidden"] = hidden
    return result


def decorate_rows(
    rows: list[dict[str, Any]],
    columns: Collection[RegisteredColumn],
    kind: str = "",
    ref: str = "",
) -> list[dict[str, Any]]:
    """Return the rows with the cell of every plugin column, and the inline button of the row.

    ``plugin`` maps a column key to ``{"text", "tone"}``; ``rowAction`` is the label of the
    inline button and ``rowActionColumn`` the column that handles it. Every row also carries
    ``tabKind`` and ``tabRef``, the list it belongs to (``"playlist"`` and the playlist
    identifier, or a plugin tab kind and its ref), so a column can tell lists apart. A column
    that fails is logged and leaves its cells empty.
    """
    if not columns:
        return rows
    broken: set[str] = set()
    decorated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["tabKind"] = kind
        item["tabRef"] = ref
        cells: dict[str, dict[str, str]] = {}
        for registered in columns:
            if registered.key in broken:
                continue
            try:
                value = registered.column.value_fn(item)
            except Exception as error:
                broken.add(registered.key)
                _LOGGER.error("Plugin column %s failed.", registered.key, exc_info=error)
                continue
            if value is None:
                continue
            cells[registered.key] = {"text": value.text, "tone": value.tone}
            if value.action and "rowAction" not in item:
                item["rowAction"] = value.action
                item["rowActionColumn"] = registered.key
        item["plugin"] = cells
        decorated.append(item)
    return decorated


class PluginColumnStore:
    """The saved column layout of each plugin tab kind."""

    def __init__(self, settings: SettingsRepository | None) -> None:
        self._settings = settings
        self._memory: dict[str, dict[str, Any]] = {}

    def preferences(self, kind: str) -> dict[str, Any]:
        """Return the layout of ``kind``; the default one when nothing valid was saved."""
        if kind in self._memory:
            return self._memory[kind]
        saved = self._settings.get_json(SETTINGS_PREFIX + kind, None) if self._settings else None
        self._memory[kind] = _validated(saved)
        return self._memory[kind]

    def save(self, kind: str, preferences: Mapping[str, Any]) -> dict[str, Any]:
        """Keep a layout, validated, and write it to the settings."""
        value = _validated(preferences)
        self._memory[kind] = value
        if self._settings is not None:
            self._settings.set_json(SETTINGS_PREFIX + kind, value)
        return value

    def reset(self, kind: str) -> dict[str, Any]:
        return self.save(kind, default_preferences())

    def resize(self, kind: str, key: str, width: int) -> dict[str, Any]:
        value = dict(self.preferences(kind))
        widths = dict(value["widths"])
        widths[key] = min(max(int(width), _MIN_WIDTH), _MAX_WIDTH)
        value["widths"] = widths
        return self.save(kind, value)

    def move(self, kind: str, key: str, offset: int, known: Collection[str]) -> dict[str, Any]:
        value = dict(self.preferences(kind))
        order = _with_known(value["order"], known)
        if key in order and offset in {-1, 1}:
            index = order.index(key)
            order.insert(min(max(index + offset, 0), len(order) - 1), order.pop(index))
        value["order"] = order
        return self.save(kind, value)

    def move_relative(
        self, kind: str, key: str, target: str, after: bool, known: Collection[str]
    ) -> dict[str, Any]:
        value = dict(self.preferences(kind))
        order = _with_known(value["order"], known)
        if key in order and target in order and key != target:
            order.remove(key)
            order.insert(order.index(target) + int(after), key)
        value["order"] = order
        return self.save(kind, value)


def default_preferences() -> dict[str, Any]:
    return {
        "order": list(_DEFAULT_ORDER),
        "hidden": list(_DEFAULT_HIDDEN),
        "widths": dict(_DEFAULT_WIDTHS),
        "showArtwork": True,
    }


def _with_known(order: Iterable[str], known: Collection[str]) -> list[str]:
    """The order, followed by the columns it does not list yet."""
    result = list(order)
    result.extend(key for key in known if key not in result)
    return result


def _validated(value: Any) -> dict[str, Any]:
    """Normalise a stored layout; anything that is not a layout reads as the default one."""
    defaults = default_preferences()
    if not isinstance(value, dict):
        return defaults
    order = value.get("order")
    hidden = value.get("hidden")
    widths = value.get("widths")
    result = dict(defaults)
    if isinstance(order, list):
        result["order"] = [
            key
            for key in dict.fromkeys(order)
            if isinstance(key, str) and (key in _DEFAULT_ORDER or is_plugin_column_key(key))
        ]
        result["order"].extend(key for key in _DEFAULT_ORDER if key not in result["order"])
    if isinstance(hidden, list):
        result["hidden"] = [
            key
            for key in dict.fromkeys(hidden)
            if isinstance(key, str) and (key in _DEFAULT_ORDER or is_plugin_column_key(key))
        ]
    if isinstance(widths, dict):
        for key, width in widths.items():
            if isinstance(key, str) and (key in _DEFAULT_WIDTHS or is_plugin_column_key(key)):
                try:
                    number = int(width)
                except (TypeError, ValueError, OverflowError):
                    continue
                result["widths"][key] = (
                    0
                    if key == "title" and number <= 0
                    else min(max(number, _MIN_WIDTH), _MAX_WIDTH)
                )
    result["showArtwork"] = bool(value.get("showArtwork", True))
    return result
