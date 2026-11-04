"""Persist and validate the user's Explorer layout and navigation session."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mtee.domain.column_widths import clamp_column_width
from mtee.models import window_layout as layout
from mtee.persistence.database import Database

__all__ = [
    "COLUMN_OPTIONS",
    "DEFAULT_COLUMN_PREFERENCES",
    "DEFAULT_WORKSPACE",
    "V1_BACKUP_NAME",
    "WorkspaceRepository",
    "convert_v1_state",
]

_PLUGIN_ACTIVITY = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_CORE_ACTIVITIES = {"explorer", "playlists", "convert", "tasks", "artists", "plugins"}
_RIGHT_TOOL_WINDOWS = {"info", "queue", "history"}
V1_BACKUP_NAME = "workspace.v1.json"

COLUMN_OPTIONS = (
    ("title", "Title"),
    ("artist", "Artist"),
    ("album", "Album"),
    ("genre", "Genre"),
    ("bpm", "BPM"),
    ("key", "Key"),
    ("duration", "Duration"),
    ("format", "Format"),
    ("filename", "Filename"),
    ("bitrate", "Bitrate"),
    ("fileCreatedAt", "Date created"),
    ("fileModifiedAt", "Date modified"),
    # Listening counts from the play log (plan 115). Hidden by default, also for users whose
    # saved layout predates them.
    ("playCount", "Plays"),
    ("lastPlayed", "Last played"),
)
_COLUMN_KEYS = tuple(key for key, _label in COLUMN_OPTIONS)
_DEFAULT_COLUMN_ORDER = [
    "title",
    "artist",
    "fileCreatedAt",
    "bpm",
    "key",
    "album",
    "genre",
    "duration",
    "format",
    "filename",
    "bitrate",
    "fileModifiedAt",
    "playCount",
    "lastPlayed",
]
_DEFAULT_HIDDEN_COLUMNS = [
    "album",
    "genre",
    "duration",
    "format",
    "filename",
    "bitrate",
    "fileModifiedAt",
    "playCount",
    "lastPlayed",
]
_DEFAULT_COLUMN_WIDTHS = {
    "title": 0,
    "artist": 150,
    "album": 150,
    "genre": 110,
    "bpm": 52,
    "key": 52,
    "duration": 70,
    "format": 72,
    "filename": 180,
    "bitrate": 78,
    "fileCreatedAt": 110,
    "fileModifiedAt": 110,
    "playCount": 64,
    "lastPlayed": 124,
}
DEFAULT_COLUMN_PREFERENCES: dict[str, Any] = {
    "order": list(_DEFAULT_COLUMN_ORDER),
    "hidden": list(_DEFAULT_HIDDEN_COLUMNS),
    "widths": dict(_DEFAULT_COLUMN_WIDTHS),
    "showArtwork": True,
}

DEFAULT_WORKSPACE: dict[str, Any] = {
    "version": 2,
    "roots": [],
    "expanded": [],
    "groups": [{"tabs": [], "active": ""}],
    "center": None,
    "activeGroup": "",
    "nextGroup": 1,
    "selectedByGroup": [[]],
    "docks": {
        "left": layout.DockState("left", True, 240, ("explorer",)).to_dict(),
        "right": layout.DockState("right", False, 360, ("info",)).to_dict(),
    },
    "previewTabs": True,
    "columnPreferences": deepcopy(DEFAULT_COLUMN_PREFERENCES),
}


class WorkspaceRepository:
    """Store one versioned JSON session document in SQLite."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self.load_recovered = False

    def load(self) -> dict[str, Any]:
        row = (
            self._database.connection()
            .execute("SELECT value_json FROM workspace_state WHERE workspace_id='main'")
            .fetchone()
        )
        if row is None:
            self.load_recovered = False
            return deepcopy(DEFAULT_WORKSPACE)
        raw_text = str(row[0])
        try:
            raw = json.loads(raw_text)
        except (TypeError, json.JSONDecodeError):
            self.load_recovered = True
            return deepcopy(DEFAULT_WORKSPACE)
        if isinstance(raw, dict) and raw.get("version") == 1:
            self._backup_v1(raw_text)
            raw = convert_v1_state(raw)
        self.load_recovered = not _has_valid_session_structure(raw)
        return _validated(raw)

    def _backup_v1(self, raw_text: str) -> None:
        """Keep the version 1 state next to the database, once, before it is converted."""
        database_path = Path(str(self._database.path))
        if str(database_path) == ":memory:" or not database_path.exists():
            return
        target = database_path.parent / V1_BACKUP_NAME
        if target.exists():
            return
        try:
            target.write_text(raw_text, encoding="utf-8")
        except OSError:
            # The conversion still runs in memory; the next save replaces the stored state.
            return

    def save(self, state: dict[str, Any]) -> None:
        value = _validated(state)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO workspace_state(workspace_id,value_json,updated_at_utc) "
                "VALUES('main',?,?) "
                "ON CONFLICT(workspace_id) DO UPDATE SET value_json=excluded.value_json,"
                "updated_at_utc=excluded.updated_at_utc",
                (encoded, datetime.now(UTC).isoformat(timespec="seconds")),
            )


def convert_v1_state(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a version 1 workspace state (0.2.0) to version 2, once, in memory.

    The groups get the ids ``g1``, ``g2``... in saved order and sit side by side. The sidebar
    becomes the left dock and the right panel the right dock; ``islandEnabled`` is dropped.
    Unknown values fall back to their defaults.
    """
    result = deepcopy(DEFAULT_WORKSPACE)
    for key in ("roots", "expanded", "previewTabs", "columnPreferences", "selectedByGroup"):
        if key in raw:
            result[key] = raw[key]
    raw_groups = raw.get("groups")
    groups: list[dict[str, Any]] = []
    if isinstance(raw_groups, list):
        for index, group in enumerate(raw_groups):
            if isinstance(group, dict):
                converted = dict(group)
                converted.setdefault("id", f"g{index + 1}")
                groups.append(converted)
    if not groups:
        groups = [{"id": "g1", "tabs": [], "active": ""}]
    ids = [str(group["id"]) for group in groups]
    result["groups"] = groups
    result["center"] = _side_by_side(ids)
    result["nextGroup"] = len(ids) + 1
    saved_index = raw.get("activeGroup", 0)
    if isinstance(saved_index, bool) or not isinstance(saved_index, int):
        saved_index = 0
    result["activeGroup"] = ids[min(max(saved_index, 0), len(ids) - 1)]
    activity = raw.get("activity", "explorer")
    left_window = activity if _valid_activity(activity) else "explorer"
    right_tab = raw.get("rightPanelTab", "info")
    right_window = right_tab if right_tab in _RIGHT_TOOL_WINDOWS else "info"
    result["docks"] = {
        "left": _dock_dict(
            "left",
            raw.get("sidebarVisible", True),
            raw.get("sidebarWidth", 240),
            left_window,
            240,
        ),
        "right": _dock_dict(
            "right",
            raw.get("rightPanelVisible", False),
            raw.get("rightPanelWidth", 360),
            right_window,
            360,
        ),
    }
    return result


def _side_by_side(group_ids: list[str]) -> dict[str, Any]:
    if len(group_ids) == 1:
        return layout.node_to_dict(layout.Leaf(group_ids[0]))
    share = 1 / len(group_ids)
    node = layout.Split(
        "row",
        tuple(layout.Leaf(group_id) for group_id in group_ids),
        tuple(share for _ in group_ids),
    )
    return layout.node_to_dict(node)


def _dock_dict(
    side: str, is_open: Any, width: Any, window: str, default_width: int
) -> dict[str, Any]:
    if isinstance(width, bool) or not isinstance(width, (int, float)):
        width = default_width
    return layout.DockState(
        side,  # type: ignore[arg-type]
        bool(is_open) if isinstance(is_open, bool) else True,
        int(width),
        (window,),
    ).to_dict()


def _valid_activity(activity: Any) -> bool:
    if not isinstance(activity, str):
        return False
    if activity in _CORE_ACTIVITIES:
        return True
    return bool(_PLUGIN_ACTIVITY.match(activity))


def _validated_docks(value: Any) -> dict[str, Any]:
    """Normalize both docks: widths are clamped and only known tool windows are kept."""
    defaults = deepcopy(DEFAULT_WORKSPACE["docks"])
    if not isinstance(value, dict):
        return defaults
    left = layout.DockState.from_dict("left", value.get("left")).to_dict()
    right = layout.DockState.from_dict("right", value.get("right")).to_dict()
    left["windows"] = [name for name in left["windows"] if _valid_activity(name)]
    right["windows"] = [name for name in right["windows"] if name in _RIGHT_TOOL_WINDOWS]
    return {"left": left, "right": right}


def _validated(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("version") != 2:
        return deepcopy(DEFAULT_WORKSPACE)
    result: dict[str, Any] = deepcopy(DEFAULT_WORKSPACE)
    result.update({key: item for key, item in value.items() if key in result})
    result["columnPreferences"] = _validated_column_preferences(value.get("columnPreferences"))
    if not isinstance(result["roots"], list) or not isinstance(result["groups"], list):
        return deepcopy(DEFAULT_WORKSPACE)
    if not result["groups"]:
        result["groups"] = [{"tabs": [], "active": ""}]
    for group in result["groups"]:
        if not isinstance(group, dict) or not isinstance(group.get("tabs"), list):
            return deepcopy(DEFAULT_WORKSPACE)
        group["tabs"] = [
            tab
            for tab in group["tabs"]
            if isinstance(tab, dict) and tab.get("kind") in {"folder", "playlist"}
        ]
        group["active"] = str(group.get("active", ""))
        saved_selections = group.get("selections", {})
        if not isinstance(saved_selections, dict):
            saved_selections = {}
        tab_ids = {str(tab.get("id", "")) for tab in group["tabs"]}
        group_selections: dict[str, dict[str, Any]] = {}
        for tab_id, selected in saved_selections.items():
            if (
                not isinstance(tab_id, str)
                or tab_id not in tab_ids
                or not isinstance(selected, dict)
            ):
                continue
            ids = selected.get("ids", [])
            group_selections[tab_id] = {
                "ids": [str(item) for item in ids if isinstance(item, str)][:10_000]
                if isinstance(ids, list)
                else [],
                "anchor": str(selected.get("anchor", "")),
            }
        group["selections"] = group_selections
    if not isinstance(result["activeGroup"], str):
        result["activeGroup"] = ""
    try:
        result["nextGroup"] = max(int(result["nextGroup"]), 1)
    except (TypeError, ValueError, OverflowError):
        result["nextGroup"] = 1
    legacy_selections = result.get("selectedByGroup", [[]])
    if not isinstance(legacy_selections, list):
        legacy_selections = [[]]
    result["selectedByGroup"] = [
        [str(track_id) for track_id in selected if isinstance(track_id, str)][:10_000]
        if isinstance(selected, list)
        else []
        for selected in legacy_selections[:2]
    ]
    while len(result["selectedByGroup"]) < len(result["groups"]):
        result["selectedByGroup"].append([])
    expanded = result["expanded"]
    result["expanded"] = (
        [str(item) for item in expanded if isinstance(item, str)][:10_000]
        if isinstance(expanded, list)
        else []
    )
    # The window of a plugin is written "<plugin_id>.<window>"; whether that plugin runs is
    # known only once the plugins are loaded, so the saved value is kept.
    result["docks"] = _validated_docks(value.get("docks"))
    result["previewTabs"] = bool(result.get("previewTabs", True))
    return result


def _validated_column_preferences(value: Any) -> dict[str, Any]:
    """Normalize table preferences without invalidating the saved workspace."""
    if not isinstance(value, dict):
        return deepcopy(DEFAULT_COLUMN_PREFERENCES)

    raw_order = value.get("order")
    saved_keys: set[str] = set()
    if isinstance(raw_order, list):
        order = list(
            dict.fromkeys(key for key in raw_order if isinstance(key, str) and key in _COLUMN_KEYS)
        )
        saved_keys = set(order)
        order.extend(key for key in _DEFAULT_COLUMN_ORDER if key not in order)
    else:
        order = list(_DEFAULT_COLUMN_ORDER)

    raw_hidden = value.get("hidden")
    if isinstance(raw_hidden, list):
        hidden = list(
            dict.fromkeys(key for key in raw_hidden if isinstance(key, str) and key in _COLUMN_KEYS)
        )
        # A column added after the layout was saved follows its default visibility.
        hidden.extend(
            key
            for key in _DEFAULT_HIDDEN_COLUMNS
            if saved_keys and key not in saved_keys and key not in hidden
        )
    else:
        hidden = list(_DEFAULT_HIDDEN_COLUMNS)
    if len(hidden) >= len(_COLUMN_KEYS):
        hidden.remove("title")

    widths = dict(_DEFAULT_COLUMN_WIDTHS)
    raw_widths = value.get("widths")
    if isinstance(raw_widths, dict):
        for key in _COLUMN_KEYS:
            raw_width = raw_widths.get(key)
            if raw_width is None or isinstance(raw_width, bool):
                continue
            try:
                width = int(raw_width)
            except (TypeError, ValueError, OverflowError):
                continue
            widths[key] = 0 if key == "title" and width <= 0 else clamp_column_width(key, width)

    show_artwork = value.get("showArtwork", True)
    if not isinstance(show_artwork, bool):
        show_artwork = True
    return {
        "order": order,
        "hidden": hidden,
        "widths": widths,
        "showArtwork": show_artwork,
    }


def _has_valid_session_structure(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("version") != 2:
        return False
    if not isinstance(value.get("roots", []), list):
        return False
    groups = value.get("groups", [])
    if not isinstance(groups, list):
        return False
    if not groups:
        return False
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("tabs"), list):
            return False
        if any(not isinstance(tab, dict) for tab in group["tabs"]):
            return False
    docks = value.get("docks", {})
    if not isinstance(docks, dict):
        return False
    return isinstance(value.get("expanded", []), list)
