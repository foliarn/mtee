"""Server tracks that are not on this computer (plan 126.4): their track source and their file.

A server item with no linked local track is a *server-only* track. Its row stays in
``remote_server_items``, and ``context.track_sources`` holds the track under the item id as its key,
so the library lists it like any other track. ``ServerTracks`` is the ``TrackSource`` of the plugin:
when such a track is played, it downloads the original into the plugin's cache, verified against the
SHA-256 the server reported, and the player plays that file.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, TypeGuard

from mtee.plugins.api import PlayableSource, PluginContext, SourceTrack

from .connection import ConnectionManager
from .hashing import file_sha256
from .store import RemoteStore, ServerRow, upsert_server_item

CACHE_DIR = "cache"
_MAX_TEXT = 2000
_NOT_CONNECTED = "Connect to MTEE Remote to play this track."
_UNKNOWN = "MTEE Remote does not know this track any more. Fetch to refresh the list of tracks."


class ServerTrackError(Exception):
    """A server-only track that cannot be opened now; the message names the cause."""

    readable = True


def server_row(item: Mapping[str, Any]) -> ServerRow:
    """The row that keeps a server item (as ``GET /api/v1/items/{id}`` or a list returns it)."""
    sha256 = item.get("sha256")
    audio_hash = item.get("audio_hash")
    metadata = item.get("metadata")
    updated = item.get("updated_at_utc")
    return ServerRow(
        item_id=str(item["item_id"]),
        root_id=str(item["root_id"]),
        relative_path=str(item["relative_path"]),
        size_bytes=_count(item.get("size_bytes")),
        sha256=sha256 if isinstance(sha256, str) else None,
        audio_hash=audio_hash if isinstance(audio_hash, str) else None,
        revision=_count(item.get("revision")),
        metadata_json=None
        if metadata is None
        else json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        updated_at_utc=updated if isinstance(updated, str) else "",
    )


def remember_item(store: RemoteStore, item: Mapping[str, Any]) -> None:
    """Store the server view of an item (its row), in one transaction."""
    with store.transaction() as conn:
        upsert_server_item(conn, server_row(item))


def source_track_of(
    item_id: str, relative_path: str, metadata: Mapping[str, Any] | None
) -> SourceTrack:
    """The display record of a server item: its title, artists, album and so on from its tags.

    The server stores the tags of the file as a snapshot (``metadata``): lists of text per field and
    the technical values. A missing field falls back to the file name, or to nothing.
    """
    meta: Mapping[str, Any] = metadata if isinstance(metadata, Mapping) else {}
    technical = meta.get("technical")
    duration_us = technical.get("duration_us") if isinstance(technical, Mapping) else None
    year_text = _first(meta.get("date"))
    number_text = _first(meta.get("track_number"))
    return SourceTrack(
        source_key=item_id,
        title=_clip(_first(meta.get("title")) or PurePosixPath(relative_path).stem),
        artists=_strings(meta.get("artist")),
        album=_clip(_first(meta.get("album"))),
        album_artist=_clip(_first(meta.get("album_artist"))),
        track_number=int(number_text) if number_text.isdigit() else None,
        duration_us=duration_us if _is_count(duration_us) else 0,
        genre=_strings(meta.get("genre")),
        year=int(year_text[:4]) if year_text[:4].isdigit() else None,
    )


def show_as_server_only(
    context: PluginContext,
    store: RemoteStore,
    item_id: str,
    relative_path: str,
    metadata_json: str | None,
) -> str:
    """Store the server-only track of an item (or refresh it); return its ``track_id``."""
    metadata = _metadata_of(metadata_json)
    keys = context.track_sources.upsert([source_track_of(item_id, relative_path, metadata)])
    track_id = keys[item_id]
    with store.transaction() as conn:
        conn.execute(
            "UPDATE remote_server_items SET source_track_id = ? WHERE item_id = ?",
            (track_id, item_id),
        )
    return track_id


def hide_server_only(context: PluginContext, store: RemoteStore, item_id: str) -> None:
    """Make the server-only track of an item unavailable (its row and track id stay).

    The track is stored first when it is not yet, so the row records that it is a track source
    and the refresh of server-only tracks does not show it again.
    """
    row = (
        store.connection()
        .execute(
            "SELECT relative_path, metadata_json, source_track_id FROM remote_server_items"
            " WHERE item_id = ?",
            (item_id,),
        )
        .fetchone()
    )
    if row is None:
        return
    if row["source_track_id"] is None:
        show_as_server_only(
            context, store, item_id, str(row["relative_path"]), row["metadata_json"]
        )
    context.track_sources.remove([item_id])


def unlink_server_only(context: PluginContext, store: RemoteStore, item_id: str) -> None:
    """Remove the server-only track of an item that now has a local file (the link keeps it)."""
    context.track_sources.remove([item_id])
    with store.transaction() as conn:
        conn.execute(
            "UPDATE remote_server_items SET source_track_id = NULL WHERE item_id = ?", (item_id,)
        )


def refresh_server_only(context: PluginContext, store: RemoteStore) -> int:
    """Give every server item with no local file its server-only track; return how many were new.

    Items that the first match registered, and items fetched without a download, get their track
    here. A linked item loses its server-only track. Runs on any thread; one transaction per step.
    """
    conn = store.connection()
    linked = "SELECT item_id FROM remote_links"
    stale = conn.execute(
        f"SELECT item_id FROM remote_server_items WHERE source_track_id IS NOT NULL"
        f" AND item_id IN ({linked})"
    ).fetchall()
    for row in stale:
        unlink_server_only(context, store, str(row["item_id"]))
    pending = conn.execute(
        f"SELECT item_id, relative_path, metadata_json FROM remote_server_items"
        f" WHERE source_track_id IS NULL AND item_id NOT IN ({linked})"
    ).fetchall()
    if not pending:
        return 0
    tracks = [
        source_track_of(
            str(row["item_id"]), str(row["relative_path"]), _metadata_of(row["metadata_json"])
        )
        for row in pending
    ]
    keys = context.track_sources.upsert(tracks)
    with store.transaction() as tx:
        for key, track_id in keys.items():
            tx.execute(
                "UPDATE remote_server_items SET source_track_id = ? WHERE item_id = ?",
                (track_id, key),
            )
    return len(pending)


def server_item_row(conn: sqlite3.Connection, item_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT item_id, root_id, relative_path, sha256, size_bytes, metadata_json"
        " FROM remote_server_items WHERE item_id = ?",
        (item_id,),
    ).fetchone()


class ServerTracks:
    """The ``TrackSource`` of the plugin: opens a server-only track by downloading its original.

    ``open`` runs on a job thread. The original is kept in ``<data-dir>/cache`` under the item id;
    a cached file is used only when its SHA-256 is the one the server reports now, so a new revision
    of the item is downloaded again. A lock per item stops two plays from writing the same part.
    """

    def __init__(
        self, context: PluginContext, store: RemoteStore, connection: ConnectionManager
    ) -> None:
        self._context = context
        self._store = store
        self._connection = connection
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def open(self, source_key: str) -> PlayableSource:
        client = self._connection.client()
        if client is None:
            raise ServerTrackError(_NOT_CONNECTED)
        row = server_item_row(self._store.connection(), source_key)
        if row is None or row["sha256"] is None:
            raise ServerTrackError(_UNKNOWN)
        sha256 = str(row["sha256"])
        target = self._cache_path(source_key, str(row["relative_path"]))
        with self._lock_of(source_key):
            if not _is_verified(target, sha256):
                client.download(source_key, target, expected_sha256=sha256)
        return PlayableSource(path=target)

    def cover(self, source_key: str) -> bytes | None:
        """No cover yet: plan 126.7 adds the covers of the server (the placeholder is shown)."""
        del source_key
        return None

    def _cache_path(self, item_id: str, relative_path: str) -> Path:
        suffix = PurePosixPath(relative_path).suffix.lower()
        folder = self._context.data_dir / CACHE_DIR
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{item_id}{suffix}"

    def _lock_of(self, item_id: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(item_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[item_id] = lock
            return lock


def _is_verified(path: Path, sha256: str) -> bool:
    """True when ``path`` is a file whose bytes have the SHA-256 the server reported."""
    if not path.is_file():
        return False
    return file_sha256(path) == sha256


def _metadata_of(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _first(value: Any) -> str:
    """The first text of a snapshot field (a list of texts), or ``""``."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        for part in value:
            if isinstance(part, str) and part.strip():
                return part.strip()
    return ""


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(_clip(part.strip()) for part in value if isinstance(part, str) and part.strip())


def _clip(text: str) -> str:
    return text[:_MAX_TEXT]


def _count(value: Any) -> int:
    return value if _is_count(value) else 0


def _is_count(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
