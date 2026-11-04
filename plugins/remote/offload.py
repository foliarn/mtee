"""Offload, download and the delete choices of the server tracks (plan 126.5).

What the person sees:

- **Remove from this computer** (the first choice of the Recycle Bin confirmation for synced
  tracks) and **Free up space** (the track menu, which opens that confirmation). A track is freed
  only when the server copy and the local file both still have the SHA-256 of the last sync. The
  local file goes to the Recycle Bin through ``request.recycle``, and the track becomes a
  server-only track under the same ``track_id`` (``track_sources.adopt``). A track that changed is
  skipped and nothing moves.
- **Delete everywhere**: the local file goes to the Recycle Bin and the server copy to the server
  trash. A track that exists only on the server goes to the server trash.
- **Download** turns a server-only track back into a file of this computer under the same
  ``track_id``, in the folder of its mapping. A copy the player kept in the cache is reused when its
  SHA-256 is the one the server reports.

Nothing here deletes a file permanently. A file of this computer leaves only through the core's
Recycle Bin path, and a server copy only into the server trash (the administrator empties it).
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from mtee.plugins.api import (
    DeleteChoice,
    DeleteChoices,
    DeleteRequest,
    JobContext,
    PluginContext,
    RecycleOutcome,
    TrackAction,
)

from .availability import REMOTE, SYNCED, availability_of
from .cache import ext_of, open_cache
from .client import ApiError, DownloadError, NetworkError, RemoteClient
from .fetch import _folder_of, _location
from .hashing import hash_tracks
from .sources import source_track_of
from .store import CachedHashes, FolderMapping, RemoteStore, insert_link, write_log
from .tasks import submit

LINKED = "linked"
SERVER_ONLY = "server_only"
LOCAL_ONLY = "local_only"

REMOVE_LOCAL = "remove_local"
DELETE_EVERYWHERE = "delete_everywhere"
FREE_UP_ACTION = "free_up_space"
DOWNLOAD_ACTION = "download"
GROUP = "Remote"
INCOMING_DIR = "incoming"

REASON_CHANGED = "changed since the last sync"
REASON_GONE = "no longer on the server"
REASON_UNREADABLE = "its file could not be read"
REASON_KEY_TAKEN = "its server copy is already known under another track"

_CHUNK = 400
_NOT_CONNECTED = "Connect to MTEE Remote first. Nothing was moved."
_PREPARING = "The server is still preparing this track; try again later."
_NO_FOLDER = (
    "No folder of this computer is linked with the server folder of this track. Link it in "
    "Settings > Remote."
)


class OffloadError(Exception):
    """A refusal before anything moved; the message is the sentence the person reads."""

    readable = True


class _Link(Protocol):
    """What the actions need of the connection: a client while the device is signed in."""

    def client(self) -> RemoteClient | None: ...


def format_size(count: int) -> str:
    """The size in bytes as a short text: ``512 B``, ``59 MB``, ``1.2 GB``."""
    size = float(max(count, 0))
    if size < 1024:
        return f"{int(size)} B"
    for unit in ("KB", "MB", "GB"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}" if size < 10 else f"{size:.0f} {unit}"
    return f"{size / 1024:.1f} TB"


def classify(
    context: PluginContext, store: RemoteStore, track_ids: Sequence[str]
) -> dict[str, str]:
    """Each track as ``linked`` (a link and a local file), ``server_only`` or ``local_only``."""
    ids = list(dict.fromkeys(track_ids))
    if not ids:
        return {}
    linked = _link_rows(store, ids)
    server = _items_of_sources(store, ids)
    with_file = {track.track_id for track in context.library.tracks(ids) if track.readable}
    kinds: dict[str, str] = {}
    for track_id in ids:
        if track_id in linked and track_id in with_file:
            kinds[track_id] = LINKED
        elif track_id in server and track_id not in linked:
            kinds[track_id] = SERVER_ONLY
        else:
            kinds[track_id] = LOCAL_ONLY
    return kinds


def offer_choices(
    context: PluginContext, store: RemoteStore, track_ids: Sequence[str]
) -> list[DeleteChoice]:
    """The choices of the Recycle Bin confirmation; none when a track is local only."""
    kinds = classify(context, store, track_ids)
    if not kinds or LOCAL_ONLY in kinds.values():
        return []
    linked = [track_id for track_id, kind in kinds.items() if kind == LINKED]
    choices: list[DeleteChoice] = []
    if linked:
        freed = format_size(_size_of(context, store, linked))
        choices.append(
            DeleteChoice(
                REMOVE_LOCAL,
                "Remove from this computer",
                description=f"Frees {freed}. The tracks stay on the server and play from there.",
                tone="normal",
                replaces_recycle=True,
            )
        )
    choices.append(
        DeleteChoice(
            DELETE_EVERYWHERE,
            "Delete everywhere",
            description="Moves the files to the Recycle Bin and the server trash.",
            tone="danger",
            replaces_recycle=True,
        )
    )
    return choices


def run_delete(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient | None,
    request: DeleteRequest,
) -> str:
    """Run one of the two delete choices on a job thread; return the sentence of the job."""
    if client is None:
        raise OffloadError(_NOT_CONNECTED)
    if request.choice_id == REMOVE_LOCAL:
        return _remove_local(context, store, client, request)
    if request.choice_id == DELETE_EVERYWHERE:
        return _delete_everywhere(context, store, client, request)
    raise OffloadError(f"MTEE Remote does not know the choice {request.choice_id}.")


def download_tracks(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    job: JobContext,
    track_ids: Sequence[str],
) -> str:
    """Download each server-only track of ``track_ids`` into its folder; return the sentence."""
    server = _items_of_sources(store, list(dict.fromkeys(track_ids)))
    if not server:
        return "Nothing to download: the selected tracks are not server only."
    mappings = store.mappings()
    done = 0
    failures: list[str] = []
    for track_id, item_id in server.items():
        job.raise_if_cancelled()
        try:
            _download_one(context, store, client, job, mappings, track_id, item_id)
        except NetworkError as error:
            failures.append(str(error))
            break
        except (ApiError, DownloadError, OffloadError, OSError, ValueError) as error:
            failures.append(str(error) or type(error).__name__)
            continue
        done += 1
    text = f"Downloaded {done} {_noun(done)}." if done else "Nothing was downloaded."
    if failures:
        text += " " + " ".join(failures)
    return text


class OffloadService:
    """The delete choices and the two track actions of the plugin, over one store and link."""

    def __init__(self, context: PluginContext, store: RemoteStore, link: _Link) -> None:
        self._context = context
        self._store = store
        self._link = link

    def delete_choices(self) -> DeleteChoices:
        return DeleteChoices(offer=self._offer, run=self._run)

    def track_actions(self) -> list[TrackAction]:
        return [
            TrackAction(
                FREE_UP_ACTION,
                "Free up space",
                GROUP,
                run=self._free_up,
                enabled_fn=self._free_up_enabled,
            ),
            TrackAction(
                DOWNLOAD_ACTION,
                "Download",
                GROUP,
                run=self._download,
                enabled_fn=self._download_enabled,
            ),
        ]

    def _offer(self, track_ids: Sequence[str]) -> list[DeleteChoice]:
        return offer_choices(self._context, self._store, track_ids)

    def _run(self, request: DeleteRequest) -> str:
        try:
            return run_delete(self._context, self._store, self._link.client(), request)
        finally:
            self._context.availability_changed(None)
            self._context.run_on_gui(lambda: self._context.refresh_ui())

    def _free_up_enabled(self, rows: Sequence[Mapping[str, Any]]) -> bool:
        ids = _ids_of(rows)
        if not ids:
            return False
        states = availability_of(self._context, self._store, ids)
        return all(states.get(track_id) == SYNCED for track_id in ids)

    def _free_up(self, rows: Sequence[Mapping[str, Any]]) -> None:
        ids = _ids_of(rows)
        if ids:
            # The core confirmation opens with the delete choices; "Remove from this computer" is
            # its default. Nothing moves before the person confirms.
            self._context.files.recycle(ids)

    def _download_enabled(self, rows: Sequence[Mapping[str, Any]]) -> bool:
        ids = _ids_of(rows)
        if not ids:
            return False
        states = availability_of(self._context, self._store, ids)
        return all(states.get(track_id) == REMOTE for track_id in ids)

    def _download(self, rows: Sequence[Mapping[str, Any]]) -> None:
        ids = _ids_of(rows)
        if not ids:
            return
        client = self._link.client()
        if client is None:
            self._context.notify("Connect to MTEE Remote first.")
            return
        submit(
            self._context,
            "Downloading from MTEE Remote",
            lambda job: download_tracks(self._context, self._store, client, job, ids),
            self._downloaded,
            summary=lambda text: text,
        )

    def _downloaded(self, result: str | None, error: BaseException | None) -> None:
        # The job ends with the sentence of ``download_tracks``, or the readable error.
        del result, error
        self._context.availability_changed(None)
        self._context.refresh_ui()


# -- the delete choices --------------------------------------------------------------------
def _remove_local(
    context: PluginContext, store: RemoteStore, client: RemoteClient, request: DeleteRequest
) -> str:
    """Free the local files of the synced tracks whose server copy and file still match the link."""
    job = request.job
    kinds = classify(context, store, request.track_ids)
    linked = _link_rows(store, [track_id for track_id, kind in kinds.items() if kind == LINKED])
    if not linked:
        return "Nothing was freed: none of the selected tracks is a synced copy."
    paths = {track.track_id: Path(track.path) for track in context.library.tracks(list(linked))}
    items: dict[str, dict[str, Any]] = {}
    skipped: dict[str, str] = {}
    candidates: list[str] = []
    for track_id, link in linked.items():
        job.raise_if_cancelled()
        try:
            item = client.get_item(str(link["item_id"]))
        except ApiError as error:
            if error.status != 404:
                raise
            skipped[track_id] = REASON_GONE
            continue
        items[track_id] = item
        if item.get("sha256") != link["local_sha256"]:
            skipped[track_id] = REASON_CHANGED
            continue
        candidates.append(track_id)
    hashed = hash_tracks(context, candidates, job) if candidates else None
    known = {entry.source_key: entry.track_id for entry in context.track_sources.list()}
    verified: list[str] = []
    sizes: dict[str, int] = {}
    for track_id in candidates:
        found = hashed.hashes.get(track_id) if hashed is not None else None
        if found is None:
            skipped[track_id] = REASON_UNREADABLE
            continue
        if found.sha256 != linked[track_id]["local_sha256"]:
            skipped[track_id] = REASON_CHANGED
            continue
        item_id = str(linked[track_id]["item_id"])
        # Checked before anything moves: the file is gone once it is recycled, and adopting the
        # track under a key that another track holds would then fail with the file in the bin.
        if known.get(item_id, track_id) != track_id:
            skipped[track_id] = REASON_KEY_TAKEN
            context.log.warning("Track %s: its server copy is known under another track.", track_id)
            continue
        sizes[track_id] = _file_size(paths[track_id])
        verified.append(track_id)

    recycled: list[str] = []
    if verified:
        outcome: RecycleOutcome = request.recycle(verified)
        recycled = list(outcome.recycled)
        for failure in outcome.failed:
            skipped[failure.track_id] = failure.reason
    freed = sum(sizes.get(track_id, 0) for track_id in recycled)
    problems = 0
    for track_id in recycled:
        item_id = str(linked[track_id]["item_id"])
        item = items[track_id]
        relative = str(item["relative_path"])
        entry = source_track_of(item_id, relative, item.get("metadata"))
        try:
            context.track_sources.adopt(track_id, entry)
        except ValueError as error:
            # The file is in the Recycle Bin already: the link stays, so the copy is not forgotten.
            problems += 1
            context.log.warning("Track %s could not be made a server track: %s", track_id, error)
            with store.transaction() as conn:
                write_log(conn, f"Freed {relative}, but it is not a server track: {error}", "error")
            continue
        with store.transaction() as conn:
            conn.execute("DELETE FROM remote_links WHERE track_id = ?", (track_id,))
            conn.execute(
                "UPDATE remote_server_items SET source_track_id = ? WHERE item_id = ?",
                (track_id, item_id),
            )
            write_log(conn, f"Removed {relative} from this computer; it plays from the server.")
    return _freed_sentence(freed, len(recycled), skipped, problems)


def _delete_everywhere(
    context: PluginContext, store: RemoteStore, client: RemoteClient, request: DeleteRequest
) -> str:
    """Send the local files of the linked tracks to the Recycle Bin, then their server copies."""
    job = request.job
    kinds = classify(context, store, request.track_ids)
    linked = _link_rows(store, [track_id for track_id, kind in kinds.items() if kind == LINKED])
    server_only = _items_of_sources(
        store, [track_id for track_id, kind in kinds.items() if kind == SERVER_ONLY]
    )
    if not linked and not server_only:
        return "Nothing was deleted: none of the selected tracks is on the server."
    recycled: list[str] = []
    kept: dict[str, str] = {}
    if linked:
        outcome: RecycleOutcome = request.recycle(list(linked))
        recycled = list(outcome.recycled)
        kept = {failure.track_id: failure.reason for failure in outcome.failed}
    targets = [(track_id, str(linked[track_id]["item_id"]), True) for track_id in recycled]
    targets += [(track_id, item_id, False) for track_id, item_id in server_only.items()]
    trashed = 0
    problem = ""
    for track_id, item_id, was_linked in targets:
        job.raise_if_cancelled()
        try:
            _trash(client, item_id)
        except NetworkError as error:
            problem = str(error)
            _log_error(context, store, f"Server copy {item_id} not deleted: {problem}")
            break  # the server cannot be reached: the rest waits, and stays as it is
        except ApiError as error:
            problem = error.message
            _log_error(context, store, f"Server copy {item_id} not deleted: {problem}")
            continue
        trashed += 1
        if not was_linked:
            context.track_sources.remove([item_id])
        with store.transaction() as conn:
            if was_linked:
                conn.execute("DELETE FROM remote_links WHERE track_id = ?", (track_id,))
            conn.execute("DELETE FROM remote_server_items WHERE item_id = ?", (item_id,))
            write_log(conn, f"Deleted {item_id} everywhere: the server copy went to the trash.")
    parts: list[str] = []
    if recycled:
        parts.append(f"{len(recycled)} {_noun(len(recycled), 'file')} went to the Recycle Bin")
    if trashed:
        parts.append(f"{trashed} server {_noun(trashed, 'copy')} went to the server trash")
    if kept:
        parts.append(f"{len(kept)} stayed on this computer ({_reasons(kept)})")
    not_trashed = len(targets) - trashed
    if not_trashed:
        parts.append(f"{not_trashed} server {_noun(not_trashed, 'copy')} not deleted: {problem}")
    return "; ".join(parts) + "." if parts else "Nothing was deleted."


# -- the download --------------------------------------------------------------------------
def _download_one(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    job: JobContext,
    mappings: Sequence[FolderMapping],
    track_id: str,
    item_id: str,
) -> None:
    """Put the original of one server-only track back in its mapped folder, under its track id."""
    row = (
        store.connection()
        .execute(
            "SELECT root_id, relative_path, sha256, audio_hash, revision FROM remote_server_items"
            " WHERE item_id = ?",
            (item_id,),
        )
        .fetchone()
    )
    if row is None or row["sha256"] is None:
        raise OffloadError(_PREPARING)
    sha256 = str(row["sha256"])
    relative = str(row["relative_path"])
    location = _location(list(mappings), str(row["root_id"]), relative)
    if location is None:
        raise OffloadError(_NO_FOLDER)
    mapping, inside = location
    folder = _folder_of(mapping, inside)
    audio = row["audio_hash"] if isinstance(row["audio_hash"], str) else None
    incoming_dir = context.data_dir / INCOMING_DIR / item_id
    incoming_dir.mkdir(parents=True, exist_ok=True)
    incoming = incoming_dir / PurePosixPath(relative).name
    if not _take_cached(context, item_id, relative, sha256, incoming):
        client.download(item_id, incoming, expected_sha256=sha256, job=job)
    final = context.files.attach_file(track_id, incoming, folder)
    with contextlib.suppress(OSError):
        incoming_dir.rmdir()
    info = os.stat(final)
    with store.transaction() as conn:
        insert_link(
            conn,
            track_id=track_id,
            item_id=item_id,
            item_revision=int(row["revision"]),
            local_sha256=sha256,
            audio_hash=audio,
            server_path=relative,
        )
        conn.execute(
            "UPDATE remote_server_items SET source_track_id = NULL WHERE item_id = ?", (item_id,)
        )
        write_log(conn, f"Downloaded {relative} to {folder}.")
    store.remember_hashes(_key(final), info.st_size, info.st_mtime_ns, CachedHashes(sha256, audio))


def _take_cached(
    context: PluginContext, item_id: str, relative: str, sha256: str, target: Path
) -> bool:
    """Move the copy the stream cache kept to ``target``, when its SHA-256 is the expected one."""
    cached = open_cache(context).lookup(item_id, sha256, ext_of(relative))
    if cached is None:
        return False
    try:
        os.replace(cached, target)
    except OSError:
        return False  # in use (a player holds it): download the original again
    return True


# -- helpers -------------------------------------------------------------------------------
def _link_rows(store: RemoteStore, track_ids: Sequence[str]) -> dict[str, sqlite3.Row]:
    rows: dict[str, sqlite3.Row] = {}
    for chunk in _chunks(track_ids):
        found = store.connection().execute(
            "SELECT track_id, item_id, item_revision, local_sha256, audio_hash, server_path"
            f" FROM remote_links WHERE track_id IN ({_marks(chunk)})",
            chunk,
        )
        for row in found.fetchall():
            rows[str(row["track_id"])] = row
    return rows


def _items_of_sources(store: RemoteStore, track_ids: Sequence[str]) -> dict[str, str]:
    """The server item of each server-only track among ``track_ids``: track id to item id."""
    items: dict[str, str] = {}
    for chunk in _chunks(track_ids):
        found = store.connection().execute(
            "SELECT source_track_id, item_id FROM remote_server_items"
            f" WHERE source_track_id IN ({_marks(chunk)})",
            chunk,
        )
        for row in found.fetchall():
            items[str(row["source_track_id"])] = str(row["item_id"])
    return items


def _size_of(context: PluginContext, store: RemoteStore, track_ids: Sequence[str]) -> int:
    """The bytes of the local files: from the hash cache, or the file when it is not cached."""
    total = 0
    for track in context.library.tracks(list(track_ids)):
        row = (
            store.connection()
            .execute("SELECT size_bytes FROM remote_hash_cache WHERE path = ?", (_key(track.path),))
            .fetchone()
        )
        if row is not None:
            total += int(row["size_bytes"])
        else:
            total += _file_size(Path(track.path))
    return total


def _file_size(path: Path) -> int:
    try:
        return os.stat(path).st_size
    except OSError:
        return 0


def _key(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _log_error(context: PluginContext, store: RemoteStore, text: str) -> None:
    """Write a failure to the activity log and to the plugin's log."""
    context.log.warning("%s", text)
    with store.transaction() as conn:
        write_log(conn, text, "error")


def _trash(client: RemoteClient, item_id: str) -> None:
    """Move the server copy to the server trash; an item that is gone already counts as done."""
    try:
        client.trash_item(item_id)
    except ApiError as error:
        if error.status != 404:
            raise


def _ids_of(rows: Sequence[Mapping[str, Any]]) -> list[str] | None:
    """The track identifiers of the rows, or None when a row has none (the action is off)."""
    ids: list[str] = []
    for row in rows:
        value = row.get("trackId")
        if not isinstance(value, str) or not value:
            return None
        ids.append(value)
    return ids or None


def _freed_sentence(freed: int, recycled: int, skipped: Mapping[str, str], problems: int) -> str:
    parts = [f"Freed {format_size(freed)}" if recycled else "Nothing was freed"]
    if skipped:
        parts.append(f"skipped {len(skipped)} {_noun(len(skipped))} ({_reasons(skipped)})")
    if problems:
        parts.append(
            f"{problems} {_noun(problems)} not marked as server only; see the activity log"
        )
    return "; ".join(parts) + "."


def _reasons(reasons: Mapping[str, str]) -> str:
    """The distinct reasons of a mapping, in order, joined for one sentence."""
    return ", ".join(dict.fromkeys(reasons.values()))


def _noun(count: int, word: str = "track") -> str:
    return word if count == 1 else f"{word}s"


def _chunks(values: Sequence[str]) -> list[list[str]]:
    return [list(values[start : start + _CHUNK]) for start in range(0, len(values), _CHUNK)]


def _marks(values: Sequence[str]) -> str:
    return ", ".join("?" for _ in values)
