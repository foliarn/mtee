"""Conflicts of MTEE Remote: two versions of a track that the sync cannot settle alone (plan 126.6).

A row of ``remote_conflicts`` is written by the push (``path_taken``, ``stale_revision``,
``conflict``), by the fetch (``both_changed``, ``deleted_on_server``) and by the first match
(``decide_later``: the tags differ). The kind is kept in ``local_json["kind"]``; a first-match row
has no kind and is a ``decide_later`` conflict.

States: ``open`` waits for the person. ``decide_later`` is listed too, except a dismissed one
(``local_json["dismissed_at_utc"]``), which is hidden from Tasks until a change on either side
reopens it. ``resolved`` keeps the chosen action in ``local_json["resolved_action"]`` and the
sentence that says what was done in ``local_json["outcome"]``.

A resolution is a job (``ConflictWork.resolve``). It first checks that the situation still holds;
when it does not, the conflict resolves as ``obsolete``. A failure keeps the conflict open with the
readable message in ``local_json["last_error"]``. Nothing on the server is overwritten: every upload
carries the revision it replaces, and a copy that the server holds under a name taken is never
replaced. Local files change only through ``context.files``: a replacement keeps the old file in the
Recycle Bin, and "Remove from this computer" opens the core confirmation.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import re
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import mutagen
from PySide6.QtCore import QObject, Signal

from mtee.domain.jobs import JobCancelledError
from mtee.plugins.api import (
    JobContext,
    LibraryTrack,
    PluginContext,
    PluginRowsModel,
    TabRequest,
)

from .client import ApiError, NetworkError, RemoteClient, UploadOffsetError
from .hashing import FileHashes, hash_tracks
from .offload import format_size
from .push import DEFAULT_CHUNK_BYTES
from .records import (
    KIND_PLAYLIST,
    PlaylistObsoleteError,
    PlaylistRefusedError,
    resolve_playlist_conflict,
)
from .sources import server_row, show_as_server_only, unlink_server_only
from .store import (
    CONFLICT_DECIDE_LATER,
    CONFLICT_OPEN,
    CONFLICT_RESOLVED,
    DISMISSED_KEY,
    CachedHashes,
    FolderMapping,
    RemoteStore,
    insert_conflict,
    upsert_server_item,
    utc_now,
    write_log,
)
from .tasks import submit

TAB_KIND = "remote.conflict"

KIND_BOTH = "both_changed"
KIND_STALE = "stale_revision"
KIND_UPLOAD = "conflict"
KIND_TAGS = "decide_later"
KIND_PATH = "path_taken"
KIND_DELETED = "deleted_on_server"

KEEP_LOCAL = "keep_local"
KEEP_SERVER = "keep_server"
KEEP_BOTH = "keep_both"
OTHER_NAME = "other_name"
LINK_EXISTING = "link_existing"
SKIP = "skip"
UPLOAD_AGAIN = "upload_again"
REMOVE_HERE = "remove_here"
KEEP_ONLY_HERE = "keep_only_here"
OBSOLETE = "obsolete"

ERROR_KEY = "last_error"
OUTCOME_KEY = "outcome"
ACTION_KEY = "resolved_action"
AWAITING_KEY = "awaiting_recycle"

_PUSH_KINDS = ("upload", "replace", "move")
_NAME_CHARS = re.compile(r'[\\/:*?"<>|]')
_CHUNK_STALLS = 3

_NETWORK_TEXT = "The server cannot be reached. Nothing was changed; try again when it is back."
_NOT_CONNECTED = "Connect to MTEE Remote first. Nothing was changed."
_NO_FOLDER = (
    "No folder of this computer is linked with a server folder for this track. Link it in "
    "Settings > Remote. Nothing was changed."
)
_UNREADABLE = "The file of this track could not be read. Nothing was changed."
_CHANGED = "The file changed while it was sent. Nothing was changed on the server; try again."
_STALLED = "The server keeps refusing the bytes of this upload. Nothing was changed on the server."
_GONE = "The server copy is no longer there. Fetch the changes to see what happened."
_SAME = "Both sides already have this file."
_REMOVED = "The file went to the Recycle Bin, so the track left this computer."
_AWAITING = (
    "Confirm the Recycle Bin dialog. This conflict closes when the file has left this computer."
)
_SUBTITLES = {
    KIND_BOTH: "Changed on both sides",
    KIND_STALE: "Changed on both sides",
    KIND_UPLOAD: "Changed on both sides",
    KIND_TAGS: "Tags differ",
    KIND_PATH: "A file with this name exists on the server",
    KIND_DELETED: "Deleted on the server",
    KIND_PLAYLIST: "Changed on both sides",
}
_REASONS = {
    KIND_BOTH: "Changed on both sides since the last sync. Nothing changes until you choose.",
    KIND_STALE: "The server file changed after this computer last saw it. Nothing was replaced.",
    KIND_UPLOAD: "The server refused this file because it changed there. Nothing was overwritten.",
    KIND_TAGS: "The same audio, with different tags on each side. Nothing changes until "
    "you choose.",
    KIND_PATH: "A file with this name already exists on the server. Nothing was uploaded and "
    "nothing was overwritten.",
    KIND_DELETED: "The file was deleted on the server. The file here is kept until you choose.",
    KIND_PLAYLIST: "The playlist changed on this computer and on the server. Nothing changes until "
    "you choose.",
}
_IDENTICAL_AUDIO = (
    "The audio is identical (same audio hash). Only the tags differ, and both sides changed them "
    "after the last sync."
)
_KIND_ACTIONS: dict[str, tuple[str, ...]] = {
    KIND_BOTH: (KEEP_LOCAL, KEEP_SERVER, KEEP_BOTH),
    KIND_STALE: (KEEP_LOCAL, KEEP_SERVER, KEEP_BOTH),
    KIND_UPLOAD: (KEEP_LOCAL, KEEP_SERVER, KEEP_BOTH),
    KIND_TAGS: (KEEP_LOCAL, KEEP_SERVER, KEEP_BOTH),
    KIND_PATH: (OTHER_NAME, LINK_EXISTING, SKIP),
    KIND_DELETED: (UPLOAD_AGAIN, REMOVE_HERE, KEEP_ONLY_HERE),
    KIND_PLAYLIST: (KEEP_LOCAL, KEEP_SERVER, KEEP_BOTH),
}
_LABELS = {
    KEEP_LOCAL: "Keep this computer's",
    KEEP_SERVER: "Keep the server's",
    KEEP_BOTH: "Keep both",
    OTHER_NAME: "Use another name on the server",
    LINK_EXISTING: "Link to the existing file",
    SKIP: "Skip",
    UPLOAD_AGAIN: "Upload it again",
    REMOVE_HERE: "Remove from this computer",
    KEEP_ONLY_HERE: "Keep only on this computer",
}
_TEXTS = {
    KEEP_LOCAL: "The server copy is replaced by this file as a new revision. The previous "
    "revision stays in the server's history.",
    KEEP_SERVER: "This file goes to the Recycle Bin and the server's copy is downloaded in its "
    "place.",
    KEEP_BOTH: 'Nothing is lost. This file is uploaded as "{name}"; the server\'s copy stays and '
    "arrives as a second track.",
    OTHER_NAME: "This file is uploaded under the next free name in the same folder. The file on "
    "the server keeps its name.",
    LINK_EXISTING: "The file on the server has the same audio. This track is linked to it, and "
    "nothing is uploaded.",
    SKIP: "This track is left out of the sync. Both files stay where they are.",
    UPLOAD_AGAIN: "This file is uploaded again at the same path, as a new item on the server.",
    REMOVE_HERE: "This file goes to the Recycle Bin after you confirm. The server copy stays in "
    "the server trash.",
    KEEP_ONLY_HERE: "This file stays on this computer and is left out of the sync. The server "
    "copy stays in the server trash.",
}
_DANGER = frozenset({KEEP_LOCAL, KEEP_SERVER, REMOVE_HERE})
_PLAYLIST_TEXTS = {
    KEEP_LOCAL: "The server's copy of the playlist gets this computer's tracks as a new revision. "
    "The previous revision stays in the server's history.",
    KEEP_SERVER: "This computer's playlist gets the server's tracks. No track is deleted, and the "
    "name stays as it is here.",
    KEEP_BOTH: "This computer's playlist goes to the server. The server's version is kept here and "
    'on the server as "{name}".',
}
_LIST_LIMIT = 300


class ConflictError(Exception):
    """A resolution that did not happen. The conflict stays open, and the sentence says why."""

    readable = True


class _ObsoleteError(Exception):
    """The situation no longer holds: the conflict resolves as obsolete, with this sentence."""


@dataclass(frozen=True)
class Conflict:
    """One row of ``remote_conflicts``, with its two JSON documents read."""

    conflict_id: str
    track_id: str | None
    item_id: str | None
    state: str
    local: dict[str, Any]
    server: dict[str, Any]

    @property
    def kind(self) -> str:
        for source in (self.local, self.server):
            kind = source.get("kind")
            if isinstance(kind, str) and kind:
                return kind
        return KIND_TAGS

    @property
    def dismissed(self) -> bool:
        return self.state == CONFLICT_DECIDE_LATER and bool(self.local.get(DISMISSED_KEY))

    @property
    def visible(self) -> bool:
        """Shown in Tasks and counted in the status: open, or a decide-later one not dismissed."""
        return self.state == CONFLICT_OPEN or (
            self.state == CONFLICT_DECIDE_LATER and not self.dismissed
        )

    def path_hint(self) -> str:
        for source in (self.local, self.server):
            value = source.get("relative_path")
            if isinstance(value, str) and value:
                return value
        return ""


# -- reads -----------------------------------------------------------------------------------
def _conflict_of(row: sqlite3.Row) -> Conflict:
    return Conflict(
        conflict_id=str(row["conflict_id"]),
        track_id=row["track_id"],
        item_id=row["item_id"],
        state=str(row["state"]),
        local=_load(row["local_json"]),
        server=_load(row["server_json"]),
    )


def read_conflicts(conn: sqlite3.Connection) -> list[Conflict]:
    rows = conn.execute(
        "SELECT * FROM remote_conflicts ORDER BY created_at_utc, conflict_id"
    ).fetchall()
    return [_conflict_of(row) for row in rows]


def visible_conflicts(conn: sqlite3.Connection) -> list[Conflict]:
    return [conflict for conflict in read_conflicts(conn) if conflict.visible]


def open_count(conn: sqlite3.Connection) -> int:
    """How many conflicts wait for the person: the status item says ``N conflicts``."""
    return len(visible_conflicts(conn))


# -- the job side ----------------------------------------------------------------------------
@dataclass(frozen=True)
class _Local:
    """The local side of a conflict: the file's tags, size and time, and its hashes."""

    path: str | None
    tags: dict[str, list[str]]
    size: int | None
    mtime: float | None
    hashes: FileHashes | None


class ConflictWork:
    """The reads and the resolutions of the conflicts. Resolutions run on a job thread.

    ``link`` is the connection: ``client()`` gives a client while the device is signed in.
    """

    def __init__(
        self,
        context: PluginContext,
        store: RemoteStore,
        link: Any,
        device_name: Callable[[], str],
    ) -> None:
        self._context = context
        self._store = store
        self._link = link
        self._device_name = device_name

    # -- reads (any thread) ----------------------------------------------------------------
    def conflict(self, conflict_id: str) -> Conflict | None:
        row = (
            self._store.connection()
            .execute("SELECT * FROM remote_conflicts WHERE conflict_id = ?", (conflict_id,))
            .fetchone()
        )
        return None if row is None else _conflict_of(row)

    def track(self, track_id: str | None) -> LibraryTrack | None:
        if not track_id:
            return None
        found = self._context.library.tracks([track_id])
        return found[0] if found else None

    def device(self) -> str:
        return _NAME_CHARS.sub("", self._device_name()).strip() or "this computer"

    # -- the view of a conflict (job thread) -----------------------------------------------
    def build_view(self, conflict_id: str, job: JobContext) -> dict[str, Any]:
        """Both versions, the reason and the choices of one conflict; reads and hashes the file."""
        conflict = self.conflict(conflict_id)
        if conflict is None:
            raise ConflictError("This conflict no longer exists.")
        if conflict.kind == KIND_PLAYLIST:
            return _playlist_view(conflict)
        track = self.track(conflict.track_id)
        target = _mapped_optional(self._store.mappings(), track)
        local = self._local(track, job)
        item, offline = self._server_item(conflict, target)
        cached = self._cached_item(conflict.item_id)
        server = _server_facts(item, cached)
        file_name = _file_name(conflict, track, server)
        title = _title_of(track, file_name)
        can_link = _can_link(conflict, local, item)
        stem, ext = PurePosixPath(file_name).stem, PurePosixPath(file_name).suffix
        new_name = f"{stem} ({self.device()}){ext}"
        return {
            "kind": conflict.kind,
            "title": title,
            "summary": file_name,
            "reason": _identical_or_reason(conflict, local, server),
            "thisSide": {
                "caption": "This computer",
                "sub": f"{self.device()} · changed {_when(local.mtime)}"
                if local.path is not None and local.mtime is not None
                else "Not on this computer any more",
            },
            "serverSide": {
                "caption": "Server",
                "sub": _server_sub(server, item, offline),
            },
            "rows": _rows(local, server),
            "choices": _choices(conflict.kind, new_name, can_link),
            "canLink": can_link,
        }

    def _local(self, track: LibraryTrack | None, job: JobContext) -> _Local:
        if track is None or not track.readable:
            return _Local(None, {}, None, None, None)
        tags: dict[str, list[str]] = {}
        size: int | None = None
        mtime: float | None = None
        try:
            with self._context.files.read_lease(track.track_id) as path:
                info = os.stat(path)
                size, mtime = info.st_size, info.st_mtime
                tags = _easy_tags(path)
        except (OSError, LookupError, TimeoutError, ValueError):
            tags = {}
        hashes = hash_tracks(self._context, [track.track_id], job).hashes.get(track.track_id)
        return _Local(str(track.path), tags, size, mtime, hashes)

    def _server_item(
        self, conflict: Conflict, target: tuple[str, str] | None
    ) -> tuple[dict[str, Any] | None, bool]:
        client = self._link.client()
        if client is None:
            return None, False
        try:
            if conflict.item_id:
                return _get_or_none(client, conflict.item_id), False
            if target is not None:
                return _item_at(client, target[0], target[1]), False
            return None, False
        except NetworkError:
            return None, True

    def _cached_item(self, item_id: str | None) -> dict[str, Any] | None:
        if not item_id:
            return None
        row = (
            self._store.connection()
            .execute("SELECT * FROM remote_server_items WHERE item_id = ?", (item_id,))
            .fetchone()
        )
        if row is None:
            return None
        return {
            "relative_path": row["relative_path"],
            "size_bytes": row["size_bytes"],
            "sha256": row["sha256"],
            "audio_hash": row["audio_hash"],
            "revision": row["revision"],
            "updated_at_utc": row["updated_at_utc"],
            "metadata": _load(row["metadata_json"]),
        }

    # -- resolutions (job thread) ----------------------------------------------------------
    def resolve(self, conflict_id: str, action: str, job: JobContext) -> str:
        """Carry out ``action`` on a conflict; return the sentence for the person.

        Raises ``ConflictError`` with the readable reason when nothing could be done; the conflict
        then stays open.
        """
        conflict = self.conflict(conflict_id)
        if conflict is None:
            raise ConflictError("This conflict no longer exists.")
        if conflict.state == CONFLICT_RESOLVED:
            raise ConflictError("This conflict is already resolved.")
        if action not in _KIND_ACTIONS.get(conflict.kind, ()):
            raise ConflictError("This choice does not apply to this conflict.")
        if conflict.kind == KIND_PLAYLIST:
            return self._resolve_playlist(conflict, action)
        handlers: dict[str, Callable[[Conflict, JobContext], str]] = {
            KEEP_LOCAL: self._keep_local,
            KEEP_SERVER: self._keep_server,
            KEEP_BOTH: self._keep_both,
            OTHER_NAME: self._other_name,
            LINK_EXISTING: self._link_existing,
            SKIP: self._skip,
            UPLOAD_AGAIN: self._upload_again,
            KEEP_ONLY_HERE: self._keep_only_here,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ConflictError("This choice is not done by a job.")
        try:
            text = handler(conflict, job)
        except _ObsoleteError as stale:
            self._finish(conflict, OBSOLETE, str(stale))
            return str(stale)
        except JobCancelledError:
            raise
        except Exception as error:
            message = _readable(error)
            self._fail(conflict, message)
            raise ConflictError(message) from error
        self._finish(conflict, action, text)
        return text

    def forget_removed(self, conflict: Conflict) -> None:
        """The file of a conflict went to the Recycle Bin: the link goes and the conflict closes."""
        with self._store.transaction() as conn:
            if conflict.track_id is not None:
                conn.execute("DELETE FROM remote_links WHERE track_id = ?", (conflict.track_id,))
                _drop_queue(conn, conflict.track_id)
        self._finish(conflict, REMOVE_HERE, _REMOVED)

    def mark(self, conflict: Conflict, updates: Mapping[str, Any]) -> None:
        """Write keys of the local JSON of a conflict (no state change)."""
        local = dict(conflict.local)
        local.update(updates)
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE remote_conflicts SET local_json = ? WHERE conflict_id = ?",
                (_dump(local), conflict.conflict_id),
            )

    def dismiss(self, conflict: Conflict) -> None:
        """Keep the conflict as decide-later: hidden from Tasks until a change reopens it."""
        with self._store.transaction() as conn:
            local = dict(conflict.local)
            local[DISMISSED_KEY] = utc_now()
            conn.execute(
                "UPDATE remote_conflicts SET state = ?, local_json = ? WHERE conflict_id = ?",
                (CONFLICT_DECIDE_LATER, _dump(local), conflict.conflict_id),
            )

    def reopen(self, conflict: Conflict) -> None:
        """A dismissed conflict whose file changed again shows in Tasks once more."""
        local = {key: value for key, value in conflict.local.items() if key != DISMISSED_KEY}
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE remote_conflicts SET state = ?, local_json = ? WHERE conflict_id = ?",
                (CONFLICT_OPEN, _dump(local), conflict.conflict_id),
            )
            write_log(conn, f"{_name_of(conflict)} changed again: it is shown in Tasks.")

    def has_newer_push(self, conflict: Conflict) -> bool:
        """True when this computer queued a change of the track after the conflict was dismissed."""
        since = conflict.local.get(DISMISSED_KEY)
        if conflict.track_id is None or not isinstance(since, str):
            return False
        placeholders = ", ".join("?" for _ in _PUSH_KINDS)
        row = (
            self._store.connection()
            .execute(
                "SELECT 1 FROM remote_queue WHERE track_id = ? AND created_at_utc > ?"
                f" AND kind IN ({placeholders})",
                (conflict.track_id, since, *_PUSH_KINDS),
            )
            .fetchone()
        )
        return row is not None

    def _resolve_playlist(self, conflict: Conflict, action: str) -> str:
        """A playlist changed on both sides (plan 126.7): the choice runs in records.py."""
        try:
            text = resolve_playlist_conflict(
                self._context, self._store, self._client(), conflict.local, action
            )
        except PlaylistObsoleteError as stale:
            self._finish(conflict, OBSOLETE, str(stale))
            return str(stale)
        except PlaylistRefusedError as refused:
            self._fail(conflict, str(refused))
            raise ConflictError(str(refused)) from refused
        except JobCancelledError:
            raise
        except Exception as error:
            message = _readable(error)
            self._fail(conflict, message)
            raise ConflictError(message) from error
        self._finish(conflict, action, text)
        return text

    def _keep_local(self, conflict: Conflict, job: JobContext) -> str:
        track = self._need_track(conflict)
        client = self._client()
        root, path = self._mapped(track)
        item = self._item_of(client, conflict, root, path)
        if item is None:
            if conflict.kind != KIND_UPLOAD or conflict.item_id:
                raise _ObsoleteError(_GONE)
            hashes = self._hashes(track, job)
            sent = self._upload(track, root, path, hashes, job)
            self._relink(track, sent, hashes, path)
            return f"Sent this file to the server as {path}."
        hashes = self._hashes(track, job)
        if hashes.sha256 == item.get("sha256"):
            self._relink(track, item, hashes, path)
            return _SAME
        # The revision is the one the server has now: a change made since the conflict fails here.
        sent = self._upload(track, root, str(item["relative_path"]), hashes, job, base=item)
        self._relink(track, sent, hashes, path)
        return f"The server copy is replaced by this file (revision {sent.get('revision')})."

    def _keep_server(self, conflict: Conflict, job: JobContext) -> str:
        track = self._need_track(conflict)
        client = self._client()
        root, path = self._mapped(track)
        item = self._item_of(client, conflict, root, path)
        if item is None:
            raise _ObsoleteError(_GONE)
        hashes = self._hashes(track, job)
        server_sha = str(item.get("sha256") or "")
        server_audio = _text_or_none(item.get("audio_hash"))
        if hashes.sha256 == server_sha:
            self._relink(track, item, hashes, path)
            return _SAME
        revision = _count(item.get("revision"))
        suffix = PurePosixPath(str(item["relative_path"])).suffix
        incoming = self._context.data_dir / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        target = incoming / f"{item['item_id']}-{revision}{suffix}"
        client.download(str(item["item_id"]), target, expected_sha256=server_sha, job=job)
        new_path = self._context.files.replace_content(track.track_id, target)
        info = os.stat(new_path)
        self._store.remember_hashes(
            _key(new_path), info.st_size, info.st_mtime_ns, CachedHashes(server_sha, server_audio)
        )
        self._relink(track, item, FileHashes(server_sha, server_audio), path)
        return (
            "This computer now has the server's file. The file that was here is in the Recycle Bin."
        )

    def _keep_both(self, conflict: Conflict, job: JobContext) -> str:
        track = self._need_track(conflict)
        client = self._client()
        root, path = self._mapped(track)
        item = self._item_of(client, conflict, root, path)
        if item is None:
            raise _ObsoleteError(_GONE)
        hashes = self._hashes(track, job)
        folder, stem, ext = _split(path)
        new_path = _free_path(
            _taken_in(client, root, folder),
            folder,
            f"{stem} ({self.device()})",
            ext,
            first_plain=True,
        )
        sent = self._upload(track, root, new_path, hashes, job)
        with self._store.transaction() as conn:
            _set_link(conn, track.track_id, sent, hashes, path)
            upsert_server_item(conn, server_row(sent))
            upsert_server_item(conn, server_row(item))
            _drop_queue(conn, track.track_id)
        show_as_server_only(
            self._context,
            self._store,
            str(item["item_id"]),
            str(item["relative_path"]),
            _dump_or_none(item.get("metadata")),
        )
        return (
            f"This file is on the server as {new_path}. The server's copy stays and arrives as a "
            "second track."
        )

    def _other_name(self, conflict: Conflict, job: JobContext) -> str:
        track = self._need_track(conflict)
        client = self._client()
        root, path = self._mapped(track)
        folder, stem, ext = _split(path)
        new_path = _free_path(_taken_in(client, root, folder), folder, stem, ext, first_plain=False)
        hashes = self._hashes(track, job)
        sent = self._upload(track, root, new_path, hashes, job)
        self._relink(track, sent, hashes, path)
        return f"Sent this file to the server as {new_path}. The file on the server keeps its name."

    def _link_existing(self, conflict: Conflict, job: JobContext) -> str:
        track = self._need_track(conflict)
        client = self._client()
        root, path = self._mapped(track)
        item = _item_at(client, root, path)
        if item is None:
            raise _ObsoleteError(
                "Nothing is at that path on the server any more. The next sync sends it."
            )
        hashes = self._hashes(track, job)
        if hashes.audio_hash is None or hashes.audio_hash != item.get("audio_hash"):
            raise ConflictError(
                "The file on the server does not have the same audio, so it cannot be linked. "
                "Choose another name, or skip this track. Nothing was changed."
            )
        differs = hashes.sha256 != item.get("sha256")
        with self._store.transaction() as conn:
            _set_link(conn, track.track_id, item, hashes, path)
            upsert_server_item(conn, server_row(item))
            _drop_queue(conn, track.track_id)
            if differs:
                insert_conflict(
                    conn,
                    track_id=track.track_id,
                    item_id=str(item["item_id"]),
                    local={
                        "relative_path": path,
                        "sha256": hashes.sha256,
                        "audio_hash": hashes.audio_hash,
                    },
                    server=_server_view(item),
                    state=CONFLICT_DECIDE_LATER,
                )
        unlink_server_only(self._context, self._store, str(item["item_id"]))
        if differs:
            return (
                "Linked to the file on the server. The tags differ, so the track stays in "
                "Conflicts."
            )
        return "Linked to the file on the server. Nothing was uploaded."

    def _skip(self, conflict: Conflict, job: JobContext) -> str:
        del job
        track = self._need_track(conflict)
        with self._store.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO remote_excluded (track_id, reason, at_utc)"
                " VALUES (?, 'skipped by the person', ?)",
                (track.track_id, utc_now()),
            )
            _drop_queue(conn, track.track_id)
        return "Left out of the sync. Both files stay where they are."

    def _upload_again(self, conflict: Conflict, job: JobContext) -> str:
        track = self._need_track(conflict)
        client = self._client()
        root, path = self._mapped(track)
        if conflict.item_id and _get_or_none(client, conflict.item_id) is not None:
            raise _ObsoleteError("The server has this file again, so there is nothing to upload.")
        hashes = self._hashes(track, job)
        sent = self._upload(track, root, path, hashes, job)
        self._relink(track, sent, hashes, path)
        return f"Uploaded again to {path} as a new item."

    def _keep_only_here(self, conflict: Conflict, job: JobContext) -> str:
        track = self._need_track(conflict)
        client = self._link.client()
        if client is not None and conflict.item_id and _get_or_none(client, conflict.item_id):
            raise _ObsoleteError("The server has this file again, so it stays in sync.")
        del job
        with self._store.transaction() as conn:
            conn.execute("DELETE FROM remote_links WHERE track_id = ?", (track.track_id,))
            conn.execute(
                "INSERT OR REPLACE INTO remote_excluded (track_id, reason, at_utc)"
                " VALUES (?, 'kept only on this computer', ?)",
                (track.track_id, utc_now()),
            )
            _drop_queue(conn, track.track_id)
        return "This file stays on this computer and is left out of the sync."

    # -- helpers of the resolutions --------------------------------------------------------
    def _need_track(self, conflict: Conflict) -> LibraryTrack:
        track = self.track(conflict.track_id)
        if track is None or not track.readable:
            raise _ObsoleteError(
                "The file of this track is no longer in the library, so there is nothing to "
                "choose between."
            )
        return track

    def _client(self) -> RemoteClient:
        client = self._link.client()
        if client is None:
            raise ConflictError(_NOT_CONNECTED)
        return client

    def _mapped(self, track: LibraryTrack) -> tuple[str, str]:
        target = _mapped_optional(self._store.mappings(), track)
        if target is None:
            raise ConflictError(_NO_FOLDER)
        return target

    def _hashes(self, track: LibraryTrack, job: JobContext) -> FileHashes:
        hashes = hash_tracks(self._context, [track.track_id], job).hashes.get(track.track_id)
        if hashes is None:
            raise ConflictError(_UNREADABLE)
        return hashes

    def _item_of(
        self, client: RemoteClient, conflict: Conflict, root: str, path: str
    ) -> dict[str, Any] | None:
        if conflict.item_id:
            return _get_or_none(client, conflict.item_id)
        return _item_at(client, root, path)

    def _upload(
        self,
        track: LibraryTrack,
        root: str,
        relative: str,
        hashes: FileHashes,
        job: JobContext,
        *,
        base: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send the file as a new item, or as a replacement of ``base``; return the committed item.

        The bytes are read chunk by chunk under the read lease, and a change of the file in between
        stops the upload. The server checks the SHA-256 and the base revision itself.
        """
        client = self._client()
        with self._context.files.read_lease(track.track_id) as path:
            info = os.stat(path)
        size = info.st_size
        fingerprint = (info.st_size, info.st_mtime_ns)
        base_item = None if base is None else str(base["item_id"])
        base_revision = None if base is None else _count(base.get("revision"))
        opened = client.open_upload(
            root_id=root,
            relative_path=relative,
            size_bytes=size,
            sha256=hashes.sha256,
            base_item_id=base_item,
            base_revision=base_revision,
        )
        upload_id = str(opened["upload_id"])
        try:
            offset = 0
            stalls = 0
            while offset < size:
                job.raise_if_cancelled()
                with self._context.files.read_lease(track.track_id) as path:
                    now = os.stat(path)
                    if (now.st_size, now.st_mtime_ns) != fingerprint:
                        raise ConflictError(_CHANGED)
                    with open(path, "rb") as handle:
                        handle.seek(offset)
                        data = handle.read(min(DEFAULT_CHUNK_BYTES, size - offset))
                if not data:
                    raise ConflictError(_CHANGED)
                try:
                    offset = client.upload_chunk(upload_id, offset, data, size)
                    stalls = 0
                except UploadOffsetError as held:
                    stalls = stalls + 1 if held.offset == offset else 0
                    if stalls > _CHUNK_STALLS:
                        raise ConflictError(_STALLED) from None
                    offset = held.offset
            body = client.commit_upload(upload_id)
        except BaseException:
            with contextlib.suppress(ApiError, NetworkError):
                client.cancel_upload(upload_id)
            raise
        item = body.get("item")
        if not isinstance(item, dict):
            raise ConflictError("The server answered with something MTEE cannot read.")
        return dict(item)

    def _relink(
        self, track: LibraryTrack, item: Mapping[str, Any], hashes: FileHashes, local_path: str
    ) -> None:
        with self._store.transaction() as conn:
            _set_link(conn, track.track_id, item, hashes, local_path)
            upsert_server_item(conn, server_row(item))
            _drop_queue(conn, track.track_id)

    def _finish(self, conflict: Conflict, action: str, text: str) -> None:
        local = {key: value for key, value in conflict.local.items() if key != ERROR_KEY}
        local[ACTION_KEY] = action
        local[OUTCOME_KEY] = text
        with self._store.transaction() as conn:
            if action == OBSOLETE:
                # The queue waits for this conflict no longer: the next pass sends the track again.
                _drop_queue(conn, conflict.track_id)
            conn.execute(
                "UPDATE remote_conflicts SET state = ?, local_json = ? WHERE conflict_id = ?",
                (CONFLICT_RESOLVED, _dump(local), conflict.conflict_id),
            )
            write_log(conn, f"{_name_of(conflict)}: {text}")

    def _fail(self, conflict: Conflict, message: str) -> None:
        local = dict(conflict.local)
        local[ERROR_KEY] = message
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE remote_conflicts SET local_json = ? WHERE conflict_id = ?",
                (_dump(local), conflict.conflict_id),
            )
            write_log(conn, f"{_name_of(conflict)} is not resolved yet: {message}", "error")


# -- the feature: what the Tasks group, the tab and the status item read (graphical thread) --
class ConflictFeature(QObject):
    """The conflicts of the plugin on the graphical thread: the Tasks rows, the tab, the status."""

    # The conflict whose tab must read again.
    changed = Signal(str)

    def __init__(
        self,
        context: PluginContext,
        store: RemoteStore,
        link: Any,
        device_name: Callable[[], str],
        after_change: Callable[[], None],
    ) -> None:
        super().__init__()
        self._context = context
        self._store = store
        self._work = ConflictWork(context, store, link, device_name)
        self._after_change = after_change
        self._model = PluginRowsModel([])
        self._views: dict[str, dict[str, Any]] = {}
        self._building: set[str] = set()
        self._busy: set[str] = set()

    @property
    def model(self) -> PluginRowsModel:
        return self._model

    def open_count(self) -> int:
        return open_count(self._store.connection())

    def refresh(self) -> None:
        """Read the rows again, close what the disk settled, reopen what changed, refresh status."""
        self._sweep()
        rows = [self._row(conflict) for conflict in visible_conflicts(self._store.connection())]
        self._model.replace(rows)
        self._after_change()

    def run_waiting(self, row_id: str) -> TabRequest | None:
        conflict = self._work.conflict(row_id)
        if conflict is None or not conflict.visible:
            return None
        return TabRequest(TAB_KIND, row_id)

    def dismiss_waiting(self, row_id: str) -> None:
        conflict = self._work.conflict(row_id)
        if conflict is None or conflict.state == CONFLICT_RESOLVED:
            return
        self._work.dismiss(conflict)
        self.refresh()

    def tab_title(self, conflict_id: str) -> str:
        conflict = self._work.conflict(conflict_id)
        if conflict is None:
            return "Conflict"
        return f"Conflict · {self._title(conflict)}"

    def load(self, conflict_id: str) -> None:
        """Read both versions of a conflict in a job, unless they are read already."""
        if conflict_id in self._views or conflict_id in self._building:
            return
        self._building.add(conflict_id)
        submit(
            self._context,
            "Reading a remote conflict",
            lambda job: self._work.build_view(conflict_id, job),
            lambda view, error: self._built(conflict_id, view, error),
            visible=False,
        )

    def snapshot(self, conflict_id: str) -> dict[str, Any]:
        """What the tab shows now, as JSON-ready values."""
        conflict = self._work.conflict(conflict_id)
        if conflict is None:
            return {
                "finished": True,
                "resolved": True,
                "outcome": "This conflict no longer exists.",
            }
        view: dict[str, Any] = dict(self._views.get(conflict_id, {"loading": True}))
        resolved = conflict.state == CONFLICT_RESOLVED
        awaiting = bool(conflict.local.get(AWAITING_KEY)) and not resolved
        if resolved:
            outcome = _text(conflict.local.get(OUTCOME_KEY))
        else:
            outcome = _AWAITING if awaiting else ""
        view.update(
            title=view.get("title") or self._title(conflict),
            resolved=resolved,
            awaiting=awaiting,
            finished=resolved or awaiting,
            outcome=outcome,
            error=_text(conflict.local.get(ERROR_KEY)),
            busy=conflict_id in self._busy,
        )
        if resolved or awaiting:
            view["choices"] = []
        return view

    def choose(self, conflict_id: str, action: str) -> None:
        conflict = self._work.conflict(conflict_id)
        if conflict is None or conflict.state == CONFLICT_RESOLVED:
            return
        if conflict_id in self._busy:
            return
        if action == REMOVE_HERE:
            self._remove_here(conflict)
            self._after(conflict_id)
            return
        self._busy.add(conflict_id)
        self.changed.emit(conflict_id)
        submit(
            self._context,
            "Resolving a remote conflict",
            lambda job: self._work.resolve(conflict_id, action, job),
            lambda text, error: self._resolved(conflict_id, text, error),
        )

    # -- internals -------------------------------------------------------------------------
    def _built(
        self, conflict_id: str, view: dict[str, Any] | None, error: BaseException | None
    ) -> None:
        self._building.discard(conflict_id)
        if error is not None:
            self._views[conflict_id] = {"viewError": str(error) or type(error).__name__}
        else:
            self._views[conflict_id] = dict(view or {})
        self.changed.emit(conflict_id)

    def _resolved(self, conflict_id: str, text: str | None, error: BaseException | None) -> None:
        self._busy.discard(conflict_id)
        del text, error  # the sentence and the failure are kept in the conflict row
        self._after(conflict_id)

    def _after(self, conflict_id: str) -> None:
        self._views.pop(conflict_id, None)
        self.changed.emit(conflict_id)
        self.refresh()
        self._context.refresh_ui()

    def _remove_here(self, conflict: Conflict) -> None:
        """Ask the core to recycle the file; the core confirms. The conflict closes after that."""
        track = self._work.track(conflict.track_id)
        if track is None:
            self._work.forget_removed(conflict)
            return
        self._context.files.recycle([track.track_id])
        self._work.mark(conflict, {AWAITING_KEY: True})

    def _sweep(self) -> None:
        for conflict in read_conflicts(self._store.connection()):
            if conflict.state == CONFLICT_RESOLVED or conflict.track_id is None:
                continue
            if conflict.local.get(AWAITING_KEY) and self._work.track(conflict.track_id) is None:
                self._work.forget_removed(conflict)
                self.changed.emit(conflict.conflict_id)
            elif conflict.dismissed and self._work.has_newer_push(conflict):
                self._work.reopen(conflict)
                self.changed.emit(conflict.conflict_id)

    def _title(self, conflict: Conflict) -> str:
        if conflict.kind == KIND_PLAYLIST:
            return _text(conflict.local.get("name")) or "Playlist"
        track = self._work.track(conflict.track_id)
        if track is not None and track.title:
            return track.title
        return PurePosixPath(conflict.path_hint()).stem or "Track"

    def _row(self, conflict: Conflict) -> dict[str, str]:
        return {
            "id": conflict.conflict_id,
            "title": self._title(conflict),
            "subtitle": _SUBTITLES.get(conflict.kind, "Needs a decision"),
            "action": "Resolve",
        }


# -- helpers ---------------------------------------------------------------------------------
def _load(text: str | None) -> dict[str, Any]:
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _dump(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _dump_or_none(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _server_view(item: Mapping[str, Any]) -> dict[str, Any]:
    """The server side of a conflict row, as the other writers of the table keep it."""
    return {
        "item_id": str(item["item_id"]),
        "relative_path": str(item.get("relative_path", "")),
        "sha256": item.get("sha256"),
        "revision": _count(item.get("revision")),
        "size_bytes": _count(item.get("size_bytes")),
    }


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _key(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _join(folder: str, name: str) -> str:
    return "/".join(part for part in (folder, name) if part)


def _split(path: str) -> tuple[str, str, str]:
    """The folder (POSIX, empty at the root), the stem and the extension of a server path."""
    posix = PurePosixPath(path)
    parent = posix.parent.as_posix()
    folder = "" if parent in ("", ".") else parent
    return folder, posix.stem, posix.suffix


def _free_path(taken: set[str], folder: str, stem: str, ext: str, *, first_plain: bool) -> str:
    """The first ``stem.ext`` (or ``stem (n).ext``, n from 2) of the folder that no item holds."""
    plain = [f"{stem}{ext}"] if first_plain else []
    numbered = (f"{stem} ({number}){ext}" for number in itertools.count(2))
    for name in itertools.chain(plain, numbered):
        candidate = _join(folder, name)
        if candidate not in taken:
            return candidate
    raise ConflictError("No free name was found in that folder.")  # pragma: no cover


def _taken_in(client: RemoteClient, root: str, folder: str) -> set[str]:
    prefix = f"{folder}/" if folder else None
    return {
        str(item.get("relative_path", "")) for item in client.all_items(root_id=root, prefix=prefix)
    }


def _get_or_none(client: RemoteClient, item_id: str) -> dict[str, Any] | None:
    """The present item, or None when the server does not hold it (404, or trashed)."""
    try:
        return client.get_item(item_id)
    except ApiError as error:
        if error.status == 404:
            return None
        raise


def _item_at(client: RemoteClient, root: str, path: str) -> dict[str, Any] | None:
    folder, _, _ = _split(path)
    for item in client.all_items(root_id=root, prefix=f"{folder}/" if folder else None):
        if item.get("relative_path") == path:
            return dict(item)
    return None


def _relative_in(root: str, path: Path) -> str | None:
    base = os.path.abspath(root).rstrip("\\/")
    full = os.path.abspath(path)
    if not os.path.normcase(full).startswith(os.path.normcase(base) + os.sep):
        return None
    return full[len(base) + 1 :].replace("\\", "/")


def _mapped_optional(
    mappings: Sequence[FolderMapping], track: LibraryTrack | None
) -> tuple[str, str] | None:
    """The server root and the server path of a track under a mapped folder (the deepest wins)."""
    if track is None:
        return None
    best: tuple[int, str, str] | None = None
    for mapping in mappings:
        relative = _relative_in(mapping.local_root_path, Path(track.path))
        if relative is None:
            continue
        depth = len(mapping.local_root_path)
        if best is None or depth > best[0]:
            subpath = mapping.server_subpath
            server = _join(subpath, relative)
            best = (depth, mapping.server_root_id, server)
    return None if best is None else (best[1], best[2])


def _set_link(
    conn: sqlite3.Connection,
    track_id: str,
    item: Mapping[str, Any],
    hashes: FileHashes,
    server_path: str,
) -> None:
    """Link a track to an item: one link per track, and one track per item."""
    item_id = str(item["item_id"])
    owner = conn.execute(
        "SELECT track_id FROM remote_links WHERE item_id = ?", (item_id,)
    ).fetchone()
    if owner is not None and str(owner["track_id"]) != track_id:
        raise ConflictError(
            "That file on the server is already linked to another track. Nothing was changed."
        )
    conn.execute(
        "INSERT INTO remote_links (track_id, item_id, item_revision, local_sha256, audio_hash,"
        " linked_at_utc, server_path) VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (track_id) DO UPDATE SET item_id = excluded.item_id,"
        " item_revision = excluded.item_revision, local_sha256 = excluded.local_sha256,"
        " audio_hash = excluded.audio_hash, server_path = excluded.server_path,"
        " linked_at_utc = excluded.linked_at_utc",
        (
            track_id,
            item_id,
            _count(item.get("revision")),
            hashes.sha256,
            hashes.audio_hash,
            utc_now(),
            server_path,
        ),
    )


def _drop_queue(conn: sqlite3.Connection, track_id: str | None) -> None:
    """Drop the push rows of a track that waited for a conflict or would now be stale."""
    if track_id is None:
        return
    placeholders = ", ".join("?" for _ in _PUSH_KINDS)
    conn.execute(
        "DELETE FROM remote_queue WHERE track_id = ? AND state IN ('pending', 'blocked', 'failed')"
        f" AND kind IN ({placeholders})",
        (track_id, *_PUSH_KINDS),
    )


def _readable(error: BaseException) -> str:
    if isinstance(error, ApiError):
        return error.message
    if isinstance(error, NetworkError):
        return _NETWORK_TEXT
    if getattr(error, "readable", False):
        return str(error)
    if isinstance(error, FileNotFoundError):
        return "A file is missing. Nothing was changed."
    return f"{type(error).__name__}: {error}"


def _easy_tags(path: Path) -> dict[str, list[str]]:
    """The easy tags of a file (title, artist, album, genre, date), read only."""
    try:
        audio = mutagen.File(path, easy=True)
    except (OSError, mutagen.MutagenError, ValueError):
        return {}
    if audio is None or not audio.tags:
        return {}
    return {str(key): [str(value) for value in values] for key, values in audio.tags.items()}


def _tag(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value if str(part).strip()]
        return "; ".join(parts)
    return ""


def _server_facts(
    item: Mapping[str, Any] | None, cached: Mapping[str, Any] | None
) -> dict[str, Any]:
    """The server's values: the item as the server has it now, else the last values seen."""
    source: Mapping[str, Any] = item if item is not None else (cached or {})
    metadata = source.get("metadata")
    return {
        "present": item is not None,
        "known": item is not None or cached is not None,
        "relative_path": _text(source.get("relative_path")),
        "size": _count(source.get("size_bytes")),
        "revision": _count(source.get("revision")),
        "updated": _text(source.get("updated_at_utc")),
        "sha256": _text_or_none(source.get("sha256")),
        "audio_hash": _text_or_none(source.get("audio_hash")),
        "meta": metadata if isinstance(metadata, dict) else {},
    }


def _file_name(conflict: Conflict, track: LibraryTrack | None, server: Mapping[str, Any]) -> str:
    if track is not None:
        return Path(track.path).name
    return (
        PurePosixPath(conflict.path_hint() or str(server.get("relative_path", ""))).name or "Track"
    )


def _title_of(track: LibraryTrack | None, file_name: str) -> str:
    if track is not None and track.title:
        return track.title
    return PurePosixPath(file_name).stem or "Track"


def _can_link(conflict: Conflict, local: _Local, item: Mapping[str, Any] | None) -> bool:
    if conflict.kind != KIND_PATH or item is None or local.hashes is None:
        return False
    audio = local.hashes.audio_hash
    return audio is not None and audio == item.get("audio_hash")


def _identical_or_reason(conflict: Conflict, local: _Local, server: Mapping[str, Any]) -> str:
    if (
        conflict.kind == KIND_TAGS
        and local.hashes is not None
        and server.get("audio_hash")
        and local.hashes.audio_hash == server.get("audio_hash")
    ):
        return _IDENTICAL_AUDIO
    return _REASONS.get(conflict.kind, "Nothing changes until you choose.")


def _when(epoch: float | None) -> str:
    if epoch is None:
        return "unknown"
    return datetime.fromtimestamp(epoch).strftime("%b %d, %H:%M")


def _when_text(value: str) -> str:
    if not value:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.strftime("%b %d, %H:%M")


def _server_sub(server: Mapping[str, Any], item: Mapping[str, Any] | None, offline: bool) -> str:
    if offline and item is None:
        return "The server cannot be reached; the last values seen are shown"
    if not server["known"]:
        return "Not on the server"
    if item is None:
        return f"No longer on the server; last seen as revision {server['revision']}"
    return f"Revision {server['revision']} · changed {_when_text(str(server['updated']))}"


def _rows(local: _Local, server: Mapping[str, Any]) -> list[dict[str, Any]]:
    meta: Mapping[str, Any] = server["meta"]
    local_title = _tag(local.tags.get("title"))
    server_title = _tag(meta.get("title"))
    local_year = _tag(local.tags.get("date"))[:4]
    server_year = _tag(meta.get("date"))[:4]
    specs: list[tuple[str, str, str, bool]] = [
        ("Title", local_title, server_title, True),
        ("Artist", _tag(local.tags.get("artist")), _tag(meta.get("artist")), True),
        ("Album", _tag(local.tags.get("album")), _tag(meta.get("album")), True),
        ("Genre", _tag(local.tags.get("genre")), _tag(meta.get("genre")), True),
        ("Year", local_year, server_year, True),
        (
            "Size",
            format_size(local.size) if local.size is not None else "",
            format_size(int(server["size"])) if server["known"] else "",
            True,
        ),
        (
            "Modified",
            _when(local.mtime) if local.mtime is not None else "",
            _when_text(str(server["updated"])) if server["known"] else "",
            True,
        ),
        ("Revision", "", str(server["revision"]) if server["known"] else "", False),
    ]
    rows: list[dict[str, Any]] = []
    for label, a, b, compare in specs:
        differs = compare and a != b
        rows.append({"label": label, "a": a or "—", "b": b or "—", "differs": differs})
    return rows


def _choices(kind: str, new_name: str, can_link: bool) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    texts = _PLAYLIST_TEXTS if kind == KIND_PLAYLIST else _TEXTS
    for action in _KIND_ACTIONS.get(kind, ()):
        if action == LINK_EXISTING and not can_link:
            continue
        choices.append(
            {
                "action": action,
                "label": _LABELS[action],
                "text": texts[action].format(name=new_name),
                "danger": action in _DANGER,
            }
        )
    return choices


def _playlist_view(conflict: Conflict) -> dict[str, Any]:
    """Both track lists of a playlist changed on both sides, and its choices (plan 126.7)."""
    name = _text(conflict.local.get("name")) or "Playlist"
    server_name = _text(conflict.server.get("name")) or name
    here = _titles(conflict.local.get("entries"))
    there = _titles(conflict.server.get("entries"))
    revision = _count(conflict.server.get("revision"))
    return {
        "kind": conflict.kind,
        "title": name,
        "summary": f"{len(here)} tracks here, {len(there)} on the server",
        "reason": _REASONS[KIND_PLAYLIST],
        "thisSide": {"caption": "This computer", "sub": f"{len(here)} tracks"},
        "serverSide": {"caption": "Server", "sub": f"{len(there)} tracks · revision {revision}"},
        "rows": [
            {"label": "Name", "a": name, "b": server_name, "differs": name != server_name},
            {
                "label": "Tracks",
                "a": str(len(here)),
                "b": str(len(there)),
                "differs": here != there,
            },
        ],
        "lists": {"thisSide": _capped(here), "serverSide": _capped(there)},
        "choices": _choices(conflict.kind, f"{name} (server)", False),
        "canLink": False,
    }


def _titles(entries: Any) -> list[str]:
    """The titles of a playlist's entries, in order (an entry without a title shows its item)."""
    if not isinstance(entries, list):
        return []
    titles: list[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            title = _text(entry.get("title")) or _text(entry.get("item_id")) or "Track"
            artist = _text(entry.get("artist"))
            titles.append(f"{artist} - {title}" if artist else title)
    return titles


def _capped(titles: list[str]) -> list[str]:
    if len(titles) <= _LIST_LIMIT:
        return titles
    return [*titles[:_LIST_LIMIT], f"and {len(titles) - _LIST_LIMIT} more"]


def _name_of(conflict: Conflict) -> str:
    if conflict.kind == KIND_PLAYLIST:
        return _text(conflict.local.get("name")) or "a playlist"
    path = conflict.path_hint()
    return PurePosixPath(path).name if path else (conflict.track_id or "a track")
