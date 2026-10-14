"""Pure helpers of the Explorer workspace: row sorting, listening columns, folder refs."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlparse

from mtee.domain.play_log import format_listened_at
from mtee.persistence.play_log_repository import TrackPlayStats
from mtee.persistence.workspace_repository import DEFAULT_COLUMN_PREFERENCES

__all__ = [
    "SORT_KEYS",
    "camelot_order",
    "copy_column_preferences",
    "folder_from_track",
    "listening_details",
    "local_path",
    "parse_folder_id",
    "parse_folder_ref",
    "sort_rows",
    "with_play_stats",
]

SORT_KEYS = {
    "index",
    "title",
    "artist",
    "album",
    "genre",
    "bpm",
    "key",
    "duration",
    "format",
    "bitrate",
    "filename",
    "fileCreatedAt",
    "fileModifiedAt",
    "playCount",
    "lastPlayed",
}


def parse_folder_id(folder_id: str) -> tuple[str, str] | None:
    if folder_id.startswith("root:"):
        return folder_id.partition(":")[2], ""
    if folder_id.startswith("folder:"):
        return parse_folder_ref(folder_id.partition(":")[2])
    return None


def parse_folder_ref(ref: str) -> tuple[str, str]:
    root_id, separator, relative = ref.partition("/")
    if not root_id or not re.fullmatch(r"[0-9a-fA-F-]{36}", root_id):
        raise ValueError("invalid library root reference")
    if not separator or not relative:
        return root_id, ""
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("invalid relative folder path")
    return root_id, relative_path.as_posix() if separator else ""


def local_path(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        if parsed.netloc:
            path = f"//{parsed.netloc}{path}"
        return path
    return value.strip()


_CAMELOT_CODE = re.compile(r"^(\d{1,2})([AaBb])$")


def camelot_order(row: dict[str, Any]) -> tuple[int, int] | None:
    """Return the Camelot position of a row as (number, letter), or None without a code.

    Within a number, A sorts before B, and 10 comes after 9.
    """
    for value in (row.get("keyCamelot"), row.get("key")):
        match = _CAMELOT_CODE.match(str(value or "").strip())
        if match is not None and 1 <= int(match.group(1)) <= 12:
            return int(match.group(1)), 0 if match.group(2).upper() == "A" else 1
    return None


def with_play_stats(
    rows: list[dict[str, Any]], stats: dict[str, TrackPlayStats]
) -> list[dict[str, Any]]:
    """Copy each row with its listening figures; a track never played has zero plays."""
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        found = stats.get(str(row.get("id", "")))
        item["playCount"] = found.counted_plays if found is not None else 0
        item["lastPlayedNs"] = (
            int(found.last_played.timestamp() * 1_000_000_000) if found is not None else None
        )
        item["lastPlayedText"] = format_listened_at(found.last_played) if found else "—"
        result.append(item)
    return result


def listening_details(stats: TrackPlayStats | None) -> list[dict[str, str]]:
    """The Plays and Last played rows of the details panel; a track never played has none."""
    return [
        {"label": "Plays", "value": str(stats.counted_plays if stats is not None else 0)},
        {
            "label": "Last played",
            "value": format_listened_at(stats.last_played if stats is not None else None),
        },
    ]


def sort_rows(rows: list[dict[str, Any]], key: str, ascending: bool) -> list[dict[str, Any]]:
    if key not in SORT_KEYS or key == "index":
        return list(rows)
    field = {
        "duration": "seconds",
        "fileCreatedAt": "fileCreatedAtNs",
        "fileModifiedAt": "fileModifiedAtNs",
        "lastPlayed": "lastPlayedNs",
    }.get(key, key)
    integer_fields = {"fileCreatedAtNs", "fileModifiedAtNs", "lastPlayedNs"}
    numeric_fields = {*integer_fields, "seconds", "bpm", "bitrate", "playCount"}
    present: list[tuple[object, str, str, dict[str, Any]]] = []
    missing = []
    for row in rows:
        if key == "key":
            # Camelot codes sort by number, then letter: 9B before 10A.
            order = camelot_order(row)
            if order is None:
                missing.append(row)
            else:
                present.append(
                    (order, str(row.get("title", "")).casefold(), str(row.get("id", "")), row)
                )
            continue
        value = row.get(field)
        if value is None or value == "":
            missing.append(row)
            continue
        try:
            sort_value: object = (
                int(value)
                if field in integer_fields
                else float(value)
                if field in numeric_fields
                else str(value).casefold()
            )
        except (TypeError, ValueError):
            missing.append(row)
            continue
        present.append(
            (
                sort_value,
                str(row.get("title", "")).casefold(),
                str(row.get("id", "")),
                row,
            )
        )
    # Stable passes keep title and UUID ties ascending in either direction.
    present.sort(key=lambda item: (item[1], item[2]))
    present.sort(key=lambda item: cast(Any, item[0]), reverse=not ascending)
    missing.sort(key=lambda row: (str(row.get("title", "")).casefold(), str(row.get("id", ""))))
    return [item[3] for item in present] + missing


def copy_column_preferences(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else DEFAULT_COLUMN_PREFERENCES
    return {
        "order": list(source.get("order", DEFAULT_COLUMN_PREFERENCES["order"])),
        "hidden": list(source.get("hidden", DEFAULT_COLUMN_PREFERENCES["hidden"])),
        "widths": dict(source.get("widths", DEFAULT_COLUMN_PREFERENCES["widths"])),
        "showArtwork": bool(source.get("showArtwork", True)),
    }


def folder_from_track(track: dict[str, Any]) -> str:
    return str(track.get("relativePath", "")).rpartition("/")[0]
