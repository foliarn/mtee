"""Persist and validate the user's Explorer layout and navigation session."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from mtee.persistence.database import Database

__all__ = [
    "COLUMN_OPTIONS",
    "DEFAULT_COLUMN_PREFERENCES",
    "DEFAULT_WORKSPACE",
    "WorkspaceRepository",
]

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
]
_DEFAULT_HIDDEN_COLUMNS = [
    "album",
    "genre",
    "duration",
    "format",
    "filename",
    "bitrate",
    "fileModifiedAt",
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
    "fileCreatedAt": 155,
    "fileModifiedAt": 155,
}
DEFAULT_COLUMN_PREFERENCES: dict[str, Any] = {
    "order": list(_DEFAULT_COLUMN_ORDER),
    "hidden": list(_DEFAULT_HIDDEN_COLUMNS),
    "widths": dict(_DEFAULT_COLUMN_WIDTHS),
    "showArtwork": True,
}

DEFAULT_WORKSPACE: dict[str, Any] = {
    "version": 1,
    "roots": [],
    "expanded": [],
    "groups": [{"tabs": [], "active": ""}],
    "activeGroup": 0,
    "selectedByGroup": [[]],
    "activity": "explorer",
    "sidebarVisible": True,
    "rightPanelVisible": False,
    "rightPanelTab": "info",
    "sidebarWidth": 240,
    "rightPanelWidth": 360,
    "islandEnabled": True,
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
        try:
            raw = json.loads(str(row[0]))
        except (TypeError, json.JSONDecodeError):
            self.load_recovered = True
            return deepcopy(DEFAULT_WORKSPACE)
        self.load_recovered = not _has_valid_session_structure(raw)
        return _validated(raw)

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


def _validated(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("version") != 1:
        return deepcopy(DEFAULT_WORKSPACE)
    result: dict[str, Any] = deepcopy(DEFAULT_WORKSPACE)
    result.update({key: item for key, item in value.items() if key in result})
    result["columnPreferences"] = _validated_column_preferences(value.get("columnPreferences"))
    if not isinstance(result["roots"], list) or not isinstance(result["groups"], list):
        return deepcopy(DEFAULT_WORKSPACE)
    if not result["groups"]:
        result["groups"] = [{"tabs": [], "active": ""}]
    result["groups"] = result["groups"][:2]
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
    try:
        result["activeGroup"] = min(max(int(result["activeGroup"]), 0), len(result["groups"]) - 1)
        result["sidebarWidth"] = min(max(int(result["sidebarWidth"]), 180), 420)
        result["rightPanelWidth"] = min(max(int(result["rightPanelWidth"]), 260), 480)
    except (TypeError, ValueError, OverflowError):
        return deepcopy(DEFAULT_WORKSPACE)
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
    if not isinstance(result["activity"], str) or result["activity"] not in {
        "explorer",
        "playlists",
        "convert",
        "tasks",
        "plugins",
        "profile",
    }:
        result["activity"] = "explorer"
    if not isinstance(result["rightPanelTab"], str) or result["rightPanelTab"] not in {
        "info",
        "queue",
    }:
        result["rightPanelTab"] = "info"
    result["islandEnabled"] = bool(result.get("islandEnabled", True))
    return result


def _validated_column_preferences(value: Any) -> dict[str, Any]:
    """Normalize table preferences without invalidating the saved workspace."""
    if not isinstance(value, dict):
        return deepcopy(DEFAULT_COLUMN_PREFERENCES)

    raw_order = value.get("order")
    if isinstance(raw_order, list):
        order = list(
            dict.fromkeys(key for key in raw_order if isinstance(key, str) and key in _COLUMN_KEYS)
        )
        order.extend(key for key in _DEFAULT_COLUMN_ORDER if key not in order)
    else:
        order = list(_DEFAULT_COLUMN_ORDER)

    raw_hidden = value.get("hidden")
    if isinstance(raw_hidden, list):
        hidden = list(
            dict.fromkeys(key for key in raw_hidden if isinstance(key, str) and key in _COLUMN_KEYS)
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
            if isinstance(raw_width, bool):
                continue
            try:
                width = int(raw_width)
            except (TypeError, ValueError, OverflowError):
                continue
            widths[key] = 0 if key == "title" and width <= 0 else min(max(width, 44), 640)

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
    if not isinstance(value, dict) or value.get("version") != 1:
        return False
    if not isinstance(value.get("roots", []), list):
        return False
    groups = value.get("groups", [])
    if not isinstance(groups, list) or len(groups) > 2:
        return False
    if not groups:
        return False
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("tabs"), list):
            return False
        if any(not isinstance(tab, dict) for tab in group["tabs"]):
            return False
    try:
        int(value.get("activeGroup", 0))
        int(value.get("sidebarWidth", 240))
        int(value.get("rightPanelWidth", 360))
    except (TypeError, ValueError, OverflowError):
        return False
    return isinstance(value.get("expanded", []), list)
