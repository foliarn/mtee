"""Server tracks that are not on this computer (plan 126.4): their track source and their file.

A server item with no linked local track is a *server-only* track. Its row stays in
``remote_server_items``, and ``context.track_sources`` holds the track under the item id as its key,
so the library lists it like any other track. ``ServerTracks`` is the ``TrackSource`` of the plugin:
when such a track is played, it plays a copy from the stream cache (``cache.py``) when there is a
verified one, else the server's stream at the chosen level (plan 127.5). Its cover is read from the
server once and kept under ``<data-dir>/covers``.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, TypeGuard

from mtee.plugins.api import JobContext, PlayableSource, PluginContext, SourceTrack

from .cache import StreamCache, ext_of, open_cache
from .client import ApiError, DownloadError, NetworkError, RemoteClient
from .connection import ConnectionManager
from .store import RemoteStore, ServerRow, upsert_server_item
from .tasks import submit

COVER_DIR = "covers"
STREAM_LEVEL_SETTING = "stream_level"
STREAM_LEVELS = ("original", "lossless", "320", "128")
# The codecs a desktop accepts from the server: FLAC as stored, Opus for the lossy levels.
PLAY_CODECS = ("flac", "opus")
PREPARE_TIMEOUT_S = 60.0
# How long ``open`` downloads an original itself before it streams it instead (see _fetch_quickly).
HEAD_START_S = 1.5
HEAD_START_CHUNK = 256 * 1024
PREPARE_POLL_S = 0.5
_MAX_TEXT = 2000
OFFLINE_TEXT = "Not available offline."
_UNKNOWN = "MTEE Remote does not know this track any more. Fetch to refresh the list of tracks."
_NOT_READY = "MTEE Remote is still preparing this track. Try again in a moment."


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
        "SELECT item_id, root_id, relative_path, sha256, size_bytes, revision, metadata_json"
        " FROM remote_server_items WHERE item_id = ?",
        (item_id,),
    ).fetchone()


def stream_level(context: PluginContext) -> str:
    """The level of a server track played on this computer; *original* unless the setting says."""
    value = context.settings.get(STREAM_LEVEL_SETTING, "original") or "original"
    return value if value in STREAM_LEVELS else "original"


def set_stream_level(context: PluginContext, value: str) -> None:
    """Store the level of a server track played here; another value raises ``ValueError``."""
    if value not in STREAM_LEVELS:
        raise ValueError("The streaming quality must be Original, Lossless, 320 kbps or 128 kbps.")
    context.settings.set(STREAM_LEVEL_SETTING, value)


class ServerTracks:
    """The ``TrackSource`` of the plugin: opens a server-only track for playback (plan 127.5).

    ``open`` runs on a job thread and keeps nothing it returns:

    - a copy in the stream cache whose SHA-256 is the one the server reports is played from this
      computer, also offline;
    - otherwise, with no connection, the track is *not available offline*;
    - at the *Original* level the server's stream is played, and a background job keeps a verified
      copy in the cache, so the next play is local;
    - at the other levels the server prepares the transcode (polled, at most 60 seconds) and its
      stream at that level is played. Transcodes are not kept on this computer.

    The device token goes only in the ``Authorization`` header of the player's request: never in a
    URL, a log line or a message.
    """

    def __init__(
        self, context: PluginContext, store: RemoteStore, connection: ConnectionManager
    ) -> None:
        self._context = context
        self._store = store
        self._connection = connection
        self._keeping: set[tuple[str, str]] = set()
        self._guard = threading.Lock()

    def open(self, source_key: str) -> PlayableSource:
        row = server_item_row(self._store.connection(), source_key)
        if row is None or row["sha256"] is None:
            raise ServerTrackError(_UNKNOWN)
        item_id = str(row["item_id"])
        sha256 = str(row["sha256"])
        ext = ext_of(str(row["relative_path"]))
        cache = open_cache(self._context)
        cached = cache.lookup(item_id, sha256, ext)
        if cached is not None:
            return PlayableSource(path=cached)
        client = self._connection.client()
        if client is None or self._connection.state == "offline":
            raise ServerTrackError(OFFLINE_TEXT)
        level = stream_level(self._context)
        headers = client.authorization_headers()
        if level == "original":
            # One transfer when the network is fast: the copy comes first and plays from disk.
            local = self._fetch_quickly(client, cache, item_id, sha256, ext)
            if local is not None:
                return PlayableSource(path=local)
            # Slower: the stream plays now, and the copy goes on from the bytes it already has.
            self._keep_copy(client, cache, item_id, sha256, ext)
            return PlayableSource(url=client.stream_url(item_id, level), headers=headers)
        _wait_until_prepared(client, item_id, level)
        return PlayableSource(url=client.stream_url(item_id, level, PLAY_CODECS), headers=headers)

    def cover(self, source_key: str) -> bytes | None:
        """The medium cover of the item, kept under ``covers``; None when it has none."""
        row = server_item_row(self._store.connection(), source_key)
        if row is None:
            return None
        item_id = str(row["item_id"])
        path = self._cover_path(item_id, int(row["revision"]))
        if path.is_file():
            return path.read_bytes()
        client = self._connection.client()
        if client is None or self._connection.state == "offline":
            return None
        try:
            data = client.cover(item_id, "m")
        except NetworkError:
            return None
        if data is None:
            return None
        part = path.with_name(path.name + ".part")
        part.write_bytes(data)
        os.replace(part, path)
        return data

    def _fetch_quickly(
        self, client: RemoteClient, cache: StreamCache, item_id: str, sha256: str, ext: str
    ) -> Path | None:
        """Download the original for ``HEAD_START_S`` at most; its cached copy, or None.

        On a home network most originals arrive in that time, and the track then plays from the
        cache: one transfer instead of a stream and a download side by side. When the time runs
        out, the part already written stays, and ``_keep_copy`` resumes it with a Range request.
        Nothing is tried while a copy of the same item is already being kept.
        """
        if HEAD_START_S <= 0:
            return None
        key = (item_id, sha256)
        with self._guard:
            if key in self._keeping:
                return None
            self._keeping.add(key)
        try:
            incoming = cache.incoming_dir() / f"{item_id}-{sha256}{ext}"
            quick = client.with_timeout(HEAD_START_S)
            quick.download(
                item_id,
                incoming,
                expected_sha256=sha256,
                chunk=HEAD_START_CHUNK,
                job=_Deadline(HEAD_START_S),
            )
            kept = cache.add(item_id, sha256, incoming)
            if kept is not None:
                cache.evict(keep=kept)
            return kept
        except _TooSlowError:
            return None
        except (NetworkError, ApiError, DownloadError, OSError) as error:
            self._context.log.info("The quick copy of a server track did not finish: %s", error)
            return None
        finally:
            with self._guard:
                self._keeping.discard(key)

    def _keep_copy(
        self, client: RemoteClient, cache: StreamCache, item_id: str, sha256: str, ext: str
    ) -> None:
        """Start the download of the original into the cache, unless one is already running."""
        key = (item_id, sha256)
        with self._guard:
            if key in self._keeping:
                return
            self._keeping.add(key)

        def keep(job: JobContext) -> None:
            del job
            try:
                incoming = cache.incoming_dir() / f"{item_id}-{sha256}{ext}"
                client.download(item_id, incoming, expected_sha256=sha256)
                kept = cache.add(item_id, sha256, incoming)
                if kept is not None:
                    cache.evict(keep=kept)
            finally:
                with self._guard:
                    self._keeping.discard(key)

        try:
            submit(self._context, "Keeping a copy of a server track", keep, _nothing, visible=False)
        except BaseException:
            with self._guard:
                self._keeping.discard(key)
            raise

    def _cover_path(self, item_id: str, revision: int) -> Path:
        folder = self._context.data_dir / COVER_DIR
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{item_id}-{revision}.jpg"


def _wait_until_prepared(client: RemoteClient, item_id: str, level: str) -> None:
    """Ask the server to prepare the transcode, and poll until it is ready (60 seconds at most)."""
    deadline = time.monotonic() + PREPARE_TIMEOUT_S
    while not client.prepare_stream(item_id, level, PLAY_CODECS):
        if time.monotonic() >= deadline:
            raise ServerTrackError(_NOT_READY)
        time.sleep(PREPARE_POLL_S)


class _TooSlowError(Exception):
    """The quick copy of ``_fetch_quickly`` ran out of time."""


class _Deadline:
    """Stands in for a job in a download: it stops the download once the time is over."""

    def __init__(self, seconds: float) -> None:
        self._end = time.monotonic() + seconds

    def raise_if_cancelled(self) -> None:
        if time.monotonic() >= self._end:
            raise _TooSlowError

    def report_progress(self, progress: float) -> None:
        del progress


def _nothing(result: object, error: BaseException | None) -> None:
    """The graphical-thread answer of a background job: nothing to show."""
    del result, error


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
