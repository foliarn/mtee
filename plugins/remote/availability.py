"""The availability of the tracks (plan 126.4): on this device, synced, or server only.

- A local track with a link is **synced** when the SHA-256 the cache holds for its file is the
  one of its link; otherwise it is **local** (a change is waiting to be sent).
- A server-only track (a track source of this plugin) is **remote**.
- Any other track is **local**.

The answer is read from the plugin's tables and the hash cache only, so it is cheap: the cache is
the one the detection pass refreshes, so a file changed a moment ago shows as synced until the
next pass hashes it. ``TrackAvailability.status`` runs on the graphical thread; the badge column
runs on a job thread. Both call ``availability_of``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from mtee.plugins.api import Availability, CellValue, PluginContext, Tone, TrackColumn

from .store import RemoteStore

LOCAL: Availability = "local"
SYNCED: Availability = "synced"
REMOTE: Availability = "remote"
COLUMN_ID = "availability"
COLUMN_TITLE = "Availability"
_BADGES: dict[Availability, tuple[str, Tone]] = {
    LOCAL: ("On this device", "neutral"),
    SYNCED: ("Synced", "neutral"),
    REMOTE: ("Server only", "secondary"),
}
_CHUNK = 400


def availability_of(
    context: PluginContext, store: RemoteStore, track_ids: Sequence[str]
) -> dict[str, Availability]:
    """The availability of each track; a track not listed here is local."""
    ids = list(dict.fromkeys(track_ids))
    if not ids:
        return {}
    conn = store.connection()
    links: dict[str, str] = {}
    server: set[str] = set()
    for chunk in _chunks(ids):
        for row in conn.execute(
            f"SELECT track_id, local_sha256 FROM remote_links WHERE track_id IN ({_marks(chunk)})",
            chunk,
        ):
            links[str(row["track_id"])] = str(row["local_sha256"])
        for row in conn.execute(
            "SELECT source_track_id FROM remote_server_items"
            f" WHERE source_track_id IN ({_marks(chunk)})",
            chunk,
        ):
            server.add(str(row["source_track_id"]))
    paths = _paths_of(context, [track_id for track_id in ids if track_id in links])
    cached = _cached_hashes(store, set(paths.values()))
    result: dict[str, Availability] = {}
    for track_id in ids:
        if track_id in links:
            path = paths.get(track_id)
            current = cached.get(path) if path is not None else None
            result[track_id] = SYNCED if current == links[track_id] else LOCAL
        elif track_id in server:
            result[track_id] = REMOTE
        else:
            result[track_id] = LOCAL
    return result


def availability_status(
    context: PluginContext, store: RemoteStore
) -> Callable[[Sequence[str]], Mapping[str, Availability]]:
    """The ``status`` of the ``TrackAvailability`` contribution."""

    def status(track_ids: Sequence[str]) -> Mapping[str, Availability]:
        return availability_of(context, store, track_ids)

    return status


def availability_column(context: PluginContext, store: RemoteStore) -> TrackColumn:
    """The badge of the availability, shown in playlists until the person hides it."""

    def value_of(row: Mapping[str, Any]) -> CellValue | None:
        track_id = row.get("trackId")
        if not isinstance(track_id, str) or not track_id:
            return None
        state = availability_of(context, store, [track_id]).get(track_id, LOCAL)
        text, tone = _BADGES[state]
        return CellValue(text=text, tone=tone)

    return TrackColumn(COLUMN_ID, COLUMN_TITLE, value_of, default_visible_for=("playlist",))


def _paths_of(context: PluginContext, track_ids: Iterable[str]) -> dict[str, str]:
    """The normalised path of each library track among ``track_ids`` (the cache is keyed by it)."""
    ids = list(track_ids)
    if not ids:
        return {}
    return {
        track.track_id: os.path.normcase(os.path.abspath(track.path))
        for track in context.library.tracks(ids)
    }


def _cached_hashes(store: RemoteStore, paths: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    keys = sorted(paths)
    conn = store.connection()
    for chunk in _chunks(keys):
        for row in conn.execute(
            f"SELECT path, sha256 FROM remote_hash_cache WHERE path IN ({_marks(chunk)})", chunk
        ):
            found[str(row["path"])] = str(row["sha256"])
    return found


def _chunks(values: Sequence[str]) -> list[list[str]]:
    return [list(values[start : start + _CHUNK]) for start in range(0, len(values), _CHUNK)]


def _marks(values: Sequence[str]) -> str:
    return ", ".join("?" for _ in values)
