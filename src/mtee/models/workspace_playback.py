"""Playback routing, queue sequencing, and playlist playback coordination."""

from __future__ import annotations

import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mtee.domain.playlists import reorder_entries
from mtee.models.workspace_rows import folder_from_track, parse_folder_id, sort_rows

__all__ = [
    "EnqueueTracker",
    "build_playlist_track_playback",
    "filter_enqueue_targets",
    "format_playback_source_title",
    "prepare_playlist_playback_rows",
    "reorder_playlist_items",
    "resolve_folder_playback_rows",
]


class EnqueueTracker:
    """Tracks sequence numbers and buffers out-of-order ready queue additions."""

    def __init__(self) -> None:
        self.sequence: int = 0
        self.ready: dict[int, dict[str, Any]] = {}
        self.next_to_apply: int = 1

    def next_sequence(self) -> int:
        """Bump and return the next sequence number."""
        self.sequence += 1
        return self.sequence

    def record_ready(self, sequence: int, result: object) -> list[dict[str, Any]]:
        """Record a completed enqueue batch and return consecutive ready batches in order."""
        self.ready[sequence] = (
            result if isinstance(result, dict) else {"error": "Invalid queue batch"}
        )
        consecutive: list[dict[str, Any]] = []
        while self.next_to_apply in self.ready:
            ready_batch = self.ready.pop(self.next_to_apply)
            self.next_to_apply += 1
            consecutive.append(ready_batch)
        return consecutive


def filter_enqueue_targets(
    targets: list[dict[str, Any]],
    source: str,
    source_title: str,
    check_cancelled: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Filter and validate track targets for enqueueing into the playback queue.

    Returns payload dict with 'rows', 'rejected', 'source', 'source_title'.
    """
    accepted: list[dict[str, Any]] = []
    rejected = 0

    for row in targets:
        if check_cancelled is not None:
            check_cancelled()
        if not isinstance(row, dict):
            rejected += 1
            continue

        track_id = str(row.get("trackId") or row.get("id") or "")
        path = str(row.get("path", ""))
        available = bool(
            track_id
            and row.get("available", row.get("status") == "readable")
            and path
            and Path(path).is_file()
        )
        if not available:
            rejected += 1
            continue

        accepted.append(dict(row) | {"id": track_id})

    return {
        "rows": accepted,
        "rejected": rejected,
        "source": source,
        "source_title": source_title,
    }


def prepare_playlist_playback_rows(rows: list[Any], *, shuffled: bool) -> list[dict[str, Any]]:
    """Filter available tracks from playlist rows and optionally shuffle them."""
    available = [
        dict(r) | {"id": r["trackId"]}
        for r in rows
        if isinstance(r, dict) and r.get("available") and r.get("trackId")
    ]
    if shuffled:
        random.shuffle(available)
    return available


def build_playlist_track_playback(
    captured: list[dict[str, Any]],
    track_id: str,
    playlist_name: str,
    source: str,
) -> tuple[list[str], int, str, list[dict[str, Any]]] | None:
    """Build playlist queue arguments (ids, chosen_index, title, playable).

    Returns None if the chosen track is unavailable or not found.
    """
    chosen = next((r for r in captured if r.get("id") == track_id), None)
    if chosen is None or not chosen.get("available"):
        return None

    playable = [
        dict(r) | {"id": r["trackId"]} for r in captured if r.get("available") and r.get("trackId")
    ]
    ids = [str(r["id"]) for r in playable]
    if chosen["trackId"] not in ids:
        return None

    chosen_index = ids.index(chosen["trackId"])
    title = str(playlist_name or "Playlist")
    return ids, chosen_index, title, playable


def resolve_folder_playback_rows(
    supplied_rows: list[dict[str, Any]] | None,
    model_rows: list[dict[str, Any]] | None,
    track: dict[str, Any],
    folder: tuple[str, str] | None,
    library_query_fn: Callable[[str, str], list[dict[str, Any]]],
    tab_state: dict[str, Any] | None,
    track_id: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Resolve track rows and playback order for playing from a folder source."""
    if supplied_rows is not None:
        folder_rows = supplied_rows
        order = [str(row.get("id", "")) for row in folder_rows if row.get("id")]
        return order, folder_rows

    if model_rows is not None:
        order = [str(row["id"]) for row in model_rows]
        return order, model_rows

    if folder is not None:
        root_id, relative = folder
    elif track:
        root_id, relative = str(track.get("rootId", "")), folder_from_track(track)
    else:
        root_id, relative = "", ""

    if root_id:
        folder_rows = library_query_fn(root_id, relative)
        state = tab_state or {}
        query = str(state.get("searchQuery", "")).casefold().strip()
        if query:
            folder_rows = [
                row
                for row in folder_rows
                if query
                in " ".join(
                    str(row.get(key, ""))
                    for key in ("title", "artist", "album", "genre", "filename")
                ).casefold()
            ]
        folder_rows = sort_rows(
            folder_rows,
            str(state.get("sortKey", "fileCreatedAt")),
            bool(state.get("sortAscending", False)),
        )
        order = [str(row["id"]) for row in folder_rows]
    else:
        order = [track_id]
        folder_rows = [track] if track else []

    return order, folder_rows


def format_playback_source_title(
    source: str,
    track: dict[str, Any],
    roots_by_id: dict[str, Any],
    artist_entry_fn: Callable[[str], Any | None],
    plugin_artist_name_fn: Callable[[str], str],
) -> str:
    """Format human-readable title for the playback source."""
    try:
        folder = parse_folder_id(source)
    except ValueError:
        folder = None
    if folder is not None:
        root_id, relative = folder
        if relative:
            return Path(relative).name
        root = roots_by_id.get(root_id, {})
        return str(root.get("name") or track.get("title") or "Folder")

    kind, _, reference = source.partition(":")
    if kind == "artist":
        entry = artist_entry_fn(reference)
        return str(
            entry.name if entry is not None else plugin_artist_name_fn(reference) or "Artist"
        )

    return str(track.get("album") or track.get("title") or "Library")


def reorder_playlist_items(
    entries: list[str],
    entry_ids: list[str],
    before: str,
) -> list[str]:
    """Reorder playlist items placing entry_ids before the designated item."""
    return reorder_entries(entries, entry_ids, before)
