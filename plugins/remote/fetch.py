"""The fetch: the changes of the other devices, read from the server and applied here (plan 126.4).

``fetch_once`` reads the change journal of the server from this device's cursor, page by page, and
applies each entry that concerns an item under a mapped server folder. Every handler is idempotent.
An entry caused by this device's own push changes nothing: a push links the item when it commits,
so the link already has the revision, the path or the SHA-256 that the entry reports.

The cursor is stored here and on the server after each page. A change that cannot be applied (a
file in use, an item that is gone) is logged and skipped. A network error stops the fetch; the page
that was cut is read again next time, which is safe because the handlers are idempotent.

Downloads go to ``<data-dir>/incoming`` first. A new file is put in its mapped folder by
``files.import_file`` (never over another file) and linked after the library scan has picked it
up (``link_pending_imports``). A changed file of a linked track is replaced by
``files.replace_content`` only when the local file is still the one the link was made with;
otherwise a conflict is recorded. Nothing is ever deleted here: a trashed item leaves a conflict,
and the local file stays.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from mtee.domain.jobs import JobCancelledError
from mtee.plugins.api import JobContext, LibraryTrack, PluginContext

from .client import ApiError, NetworkError, RemoteClient
from .hashing import FileHashes, hash_tracks
from .push import CONFLICT_OPEN
from .records import pull_records
from .sources import (
    hide_server_only,
    refresh_server_only,
    remember_item,
    server_item_row,
    server_row,
    show_as_server_only,
    unlink_server_only,
)
from .store import (
    CachedHashes,
    FolderMapping,
    RemoteStore,
    insert_conflict,
    insert_link,
    is_dismissed,
    upsert_server_item,
    utc_now,
    write_log,
)

FETCH_PAGE = 500
JOURNAL_CURSOR = "journal"
# The journal kinds of the records (plan 126.7): they carry no item of the folders, and are applied
# once, after the pages, by ``records.pull_records``.
RECORD_KINDS = frozenset({"play_events", "playlist", "track_data", "settings"})
DOWNLOAD_NEW_KEY = "download_new"
# One fetch at a time: the automatic pull and a press of Fetch never apply the same page twice.
_FETCH_LOCK = threading.Lock()


def download_new(context: PluginContext) -> bool:
    """Whether a new server track is downloaded into its mapped folder (off by default)."""
    return (context.settings.get(DOWNLOAD_NEW_KEY, "false") or "") == "true"


def set_download_new(context: PluginContext, value: bool) -> None:
    context.settings.set(DOWNLOAD_NEW_KEY, "true" if value else "false")


@dataclass
class FetchResult:
    """What one fetch did, for the summary the person sees."""

    pages: int = 0
    entries: int = 0
    linked: int = 0
    downloaded: int = 0
    server_only: int = 0
    replaced: int = 0
    moved: int = 0
    removed: int = 0
    conflicts: int = 0

    def summary(self) -> str:
        counts = (
            (self.downloaded, "downloaded"),
            (self.linked, "linked"),
            (self.server_only, "server only"),
            (self.replaced, "replaced"),
            (self.moved, "moved"),
            (self.removed, "removed on the server"),
            (self.conflicts, "conflicts"),
        )
        shown = [f"{count} {label}" for count, label in counts if count]
        if not shown:
            return "Nothing new on the server."
        return "Fetched: " + ", ".join(shown) + "."


@dataclass
class _Pass:
    """What the handlers of one fetch share: the context, the server, the mappings, the counts."""

    context: PluginContext
    store: RemoteStore
    client: RemoteClient
    job: JobContext
    mappings: list[FolderMapping]
    download: bool
    result: FetchResult
    by_path: dict[str, LibraryTrack] | None = None
    record_kinds: set[str] = field(default_factory=set)
    record_items: set[str] = field(default_factory=set)


def fetch_once(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    job: JobContext,
    *,
    wait: float = 0,
) -> FetchResult:
    """Read the server's changes from the cursor and apply them; return what was done.

    ``wait`` (seconds) makes the first request a long poll: it returns when a change comes, or when
    the wait ends with none. Runs on a job thread. Mappings are required; without one nothing is
    read, so that the changes are applied once a folder is mapped.
    """
    result = FetchResult()
    if wait > 0:
        client.changes(since=_cursor(store, client), limit=1, wait=wait)
    mappings = store.mappings()
    if not mappings:
        return result
    with _FETCH_LOCK:
        state = _Pass(context, store, client, job, mappings, download_new(context), result)
        cursor = _cursor(store, client)
        while True:
            page = client.changes(since=cursor, limit=FETCH_PAGE)
            for change in page.changes:
                job.raise_if_cancelled()
                _apply(state, change)
                result.entries += 1
            cursor = page.next
            _store_cursor(store, cursor)
            client.put_cursor(cursor)
            result.pages += 1
            context.run_on_gui(lambda: _refresh_views(context))
            if not page.more:
                break
        result.linked += link_pending_imports(context, store, job)
        refresh_server_only(context, store)
        if state.record_kinds or state.record_items:
            pull_records(
                context,
                store,
                client,
                kinds=state.record_kinds,
                items=state.record_items,
            )
    return result


def link_pending_imports(context: PluginContext, store: RemoteStore, job: JobContext) -> int:
    """Link the files downloaded for new items, once the library scan has picked them up.

    A file is linked only when its SHA-256 is still the one the server reported. A file that is
    gone is dropped from the pending list. Runs on a job thread; returns how many were linked.
    """
    rows = (
        store.connection()
        .execute("SELECT item_id, local_path, relative_path, sha256, revision FROM remote_imports")
        .fetchall()
    )
    if not rows:
        return 0
    by_path = {
        _key(track.path): track for track in context.library.tracks(context.library.track_ids())
    }
    linked = 0
    for row in rows:
        job.raise_if_cancelled()
        item_id = str(row["item_id"])
        local = Path(str(row["local_path"]))
        track = by_path.get(_key(local))
        if track is None:
            if not local.is_file():
                _drop_import(store, item_id, "The downloaded file is gone; it was not linked.")
            continue
        hashes = hash_tracks(context, [track.track_id], job).hashes.get(track.track_id)
        with store.transaction() as conn:
            conn.execute("DELETE FROM remote_imports WHERE item_id = ?", (item_id,))
            if hashes is None or hashes.sha256 != row["sha256"]:
                write_log(conn, "A downloaded file changed before it was linked.", "warning")
                continue
            if insert_link(
                conn,
                track_id=track.track_id,
                item_id=item_id,
                item_revision=int(row["revision"]),
                local_sha256=hashes.sha256,
                audio_hash=hashes.audio_hash,
                server_path=str(row["relative_path"]),
            ):
                write_log(conn, f"Linked the downloaded file {row['relative_path']}.")
                linked += 1
        if hashes is not None and hashes.sha256 == row["sha256"]:
            unlink_server_only(context, store, item_id)
    return linked


# -- the journal, page by page ---------------------------------------------------------------
def _cursor(store: RemoteStore, client: RemoteClient) -> int:
    """The stored cursor, or the one the server keeps for this device (0 for a new device)."""
    row = (
        store.connection()
        .execute("SELECT value FROM remote_cursors WHERE name = ?", (JOURNAL_CURSOR,))
        .fetchone()
    )
    if row is not None:
        try:
            return int(row["value"])
        except ValueError:
            pass
    return client.get_cursor()


def _store_cursor(store: RemoteStore, cursor: int) -> None:
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO remote_cursors (name, value) VALUES (?, ?)"
            " ON CONFLICT (name) DO UPDATE SET value = excluded.value",
            (JOURNAL_CURSOR, str(cursor)),
        )


def _refresh_views(context: PluginContext) -> None:
    """Show the changes: the availability of the tracks and the lists (graphical thread)."""
    context.availability_changed(None)
    context.refresh_ui()


def _apply(state: _Pass, change: dict[str, Any]) -> None:
    kind = change.get("kind")
    item_id = change.get("item_id")
    payload = change.get("payload")
    if not isinstance(kind, str) or not isinstance(payload, dict):
        return
    if kind in RECORD_KINDS:
        # A record changed on another device: it is pulled once the pages are read (see fetch_once).
        state.record_kinds.add(kind)
        if kind == "track_data" and isinstance(item_id, str):
            state.record_items.add(item_id)
        return
    if not isinstance(item_id, str):
        return
    handler = _HANDLERS.get(kind)
    if handler is None:
        return
    try:
        handler(state, item_id, payload)
    except (NetworkError, JobCancelledError):
        raise
    except Exception as error:  # one change that cannot be applied must not stop the others
        state.context.log.warning("A change of MTEE Remote was skipped (%s): %s", kind, error)
        _log(state, f"A change ({kind}) could not be applied: {error}", "warning")


def _arrived(state: _Pass, item_id: str, payload: dict[str, Any]) -> None:
    """``added`` and ``restored``: a new item under a mapped folder, or one that is back."""
    if _link(state, item_id) is not None:
        return
    row = server_item_row(state.store.connection(), item_id)
    if row is not None:
        show_as_server_only(
            state.context, state.store, item_id, str(row["relative_path"]), row["metadata_json"]
        )
        return
    root = payload.get("root_id")
    if isinstance(root, str) and not any(m.server_root_id == root for m in state.mappings):
        return
    item = _get(state, item_id)
    if item is not None:
        _arrive(state, item)


def _replaced(state: _Pass, item_id: str, payload: dict[str, Any]) -> None:
    link = _link(state, item_id)
    if link is not None:
        if _revision(payload) <= int(link["item_revision"]):
            return  # this device's own push, or an entry already applied
        item = _get(state, item_id)
        if item is not None and isinstance(item.get("sha256"), str):
            _apply_replacement(state, link, item)
        return
    if server_item_row(state.store.connection(), item_id) is not None:
        item = _get(state, item_id)
        if item is not None:
            _refresh_known(state, item)
        return
    _arrived(state, item_id, payload)


def _metadata(state: _Pass, item_id: str, payload: dict[str, Any]) -> None:
    link = _link(state, item_id)
    if link is not None:
        if _revision(payload) > int(link["item_revision"]):
            item = _get(state, item_id)
            if item is not None and isinstance(item.get("sha256"), str):
                _apply_replacement(state, link, item)
        return
    if server_item_row(state.store.connection(), item_id) is not None:
        item = _get(state, item_id)
        if item is not None:
            _refresh_known(state, item)
        return
    _arrived(state, item_id, payload)


def _moved(state: _Pass, item_id: str, payload: dict[str, Any]) -> None:
    item = _get(state, item_id)
    if item is None:
        return  # trashed since: the trashed entry that follows deals with it
    relative = str(item["relative_path"])
    location = _location(state.mappings, str(item["root_id"]), relative)
    link = _link(state, item_id)
    if link is not None:
        if link["server_path"] == relative:
            return  # this device's own move, or an entry already applied
        if location is None:
            _log(state, f"Moved on the server out of the mapped folder: {relative}.", "warning")
            return
        _move_linked(state, link, location, item)
        return
    if server_item_row(state.store.connection(), item_id) is not None:
        if location is None:
            _drop_known(state, item_id)
            return
        _refresh_known(state, item)
        return
    _arrive(state, item)


def _trashed(state: _Pass, item_id: str, payload: dict[str, Any]) -> None:
    del payload
    _gone(state, item_id, purged=False)


def _purged(state: _Pass, item_id: str, payload: dict[str, Any]) -> None:
    del payload
    _gone(state, item_id, purged=True)


_HANDLERS: dict[str, Callable[[_Pass, str, dict[str, Any]], None]] = {
    "added": _arrived,
    "restored": _arrived,
    "replaced": _replaced,
    "metadata": _metadata,
    "moved": _moved,
    "trashed": _trashed,
    "purged": _purged,
}


# -- the rules of one item -------------------------------------------------------------------
def _arrive(state: _Pass, item: dict[str, Any]) -> None:
    """A new item under a mapped folder: link the file already here, download it, or list it."""
    if not isinstance(item.get("sha256"), str):
        return  # the server is still hashing it: its metadata entry brings it back here
    location = _location(state.mappings, str(item["root_id"]), str(item["relative_path"]))
    if location is None:
        return
    mapping, inside = location
    local = _local_at(state, mapping, inside)
    if local is not None and local.readable:
        hashes = _hashes_of(state, local.track_id)
        if hashes is not None and hashes.sha256 == item["sha256"]:
            _link_here(state, local.track_id, item, hashes)
            return
    if not state.download:
        remember_item(state.store, item)
        show_as_server_only(
            state.context,
            state.store,
            str(item["item_id"]),
            str(item["relative_path"]),
            server_row(item).metadata_json,
        )
        state.result.server_only += 1
        _log(state, f"New on the server: {item['relative_path']} (server only).")
        return
    _download_new(state, item, mapping, inside)


def _link_here(state: _Pass, track_id: str, item: dict[str, Any], hashes: FileHashes) -> None:
    """The file already here has the item's SHA-256: link them, with no transfer."""
    item_id = str(item["item_id"])
    with state.store.transaction() as conn:
        linked = insert_link(
            conn,
            track_id=track_id,
            item_id=item_id,
            item_revision=_count(item.get("revision")),
            local_sha256=hashes.sha256,
            audio_hash=hashes.audio_hash,
            server_path=str(item["relative_path"]),
        )
        upsert_server_item(conn, server_row(item))
        if linked:
            write_log(conn, f"Matched {item['relative_path']} with a file already here.")
    if linked:
        unlink_server_only(state.context, state.store, item_id)
        state.result.linked += 1


def _download_new(state: _Pass, item: dict[str, Any], mapping: FolderMapping, inside: str) -> None:
    """Download a new item into its mapped folder; the file is linked after the library scan."""
    item_id = str(item["item_id"])
    # One folder per item keeps the file name the server has: the import takes the name as it is.
    downloaded = state.client.download(
        item_id,
        _incoming_folder(state.context) / item_id / _name(inside),
        expected_sha256=str(item["sha256"]),
        job=state.job,
    )
    folder = _folder_of(mapping, inside)
    final = state.context.files.import_file(downloaded, folder)
    with contextlib.suppress(OSError):
        downloaded.parent.rmdir()  # the item's folder of the download, empty now
    with state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO remote_imports (item_id, local_path, relative_path, sha256, revision,"
            " audio_hash, created_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (item_id) DO UPDATE SET local_path = excluded.local_path,"
            " relative_path = excluded.relative_path, sha256 = excluded.sha256,"
            " revision = excluded.revision, audio_hash = excluded.audio_hash",
            (
                item_id,
                str(final),
                str(item["relative_path"]),
                str(item["sha256"]),
                _count(item.get("revision")),
                item.get("audio_hash") if isinstance(item.get("audio_hash"), str) else None,
                utc_now(),
            ),
        )
        upsert_server_item(conn, server_row(item))
        write_log(conn, f"Downloaded {item['relative_path']}; it is linked after the scan.")
    unlink_server_only(state.context, state.store, item_id)
    state.context.run_on_gui(lambda: _rescan(state.context, folder))
    state.result.downloaded += 1


def _apply_replacement(state: _Pass, link: sqlite3.Row, item: dict[str, Any]) -> None:
    """The item has a newer revision than the link: replace the local file, or record a conflict."""
    revision = _count(item.get("revision"))
    if revision <= int(link["item_revision"]):
        return
    item_id = str(item["item_id"])
    server_sha = str(item["sha256"])
    track = _track(state, str(link["track_id"]))
    if track is None:
        _log(state, f"The track of {item['relative_path']} is no longer in the library.", "warning")
        return
    hashes = _hashes_of(state, track.track_id) if track.readable else None
    if hashes is not None and hashes.sha256 == server_sha:
        _set_link_version(state, track.track_id, revision, server_sha, item)
        return
    if hashes is None or hashes.sha256 != link["local_sha256"]:
        _conflict(
            state,
            track_id=track.track_id,
            item_id=item_id,
            kind="both_changed",
            local={
                "relative_path": link["server_path"],
                "sha256": None if hashes is None else hashes.sha256,
            },
            server=_server_view(item),
            message=f"{item['relative_path']} changed here and on the server.",
        )
        return
    suffix = PurePosixPath(str(item["relative_path"])).suffix
    downloaded = state.client.download(
        item_id,
        _incoming_folder(state.context) / f"{item_id}-{revision}{suffix}",
        expected_sha256=server_sha,
        job=state.job,
    )
    new_path = state.context.files.replace_content(track.track_id, downloaded)
    stat = os.stat(new_path)
    state.store.remember_hashes(
        _key(new_path),
        stat.st_size,
        stat.st_mtime_ns,
        CachedHashes(server_sha, _text_or_none(item.get("audio_hash"))),
    )
    _set_link_version(state, track.track_id, revision, server_sha, item)
    state.result.replaced += 1
    _log(state, f"Replaced {item['relative_path']} with the server version (revision {revision}).")


def _move_linked(
    state: _Pass, link: sqlite3.Row, location: tuple[FolderMapping, str], item: dict[str, Any]
) -> None:
    """A linked item moved on the server: move the file here when its folder changed."""
    mapping, inside = location
    track = _track(state, str(link["track_id"]))
    if track is None:
        return
    local = _relative_in(str(mapping.local_folder), track.path)
    if local is None:
        _log(state, f"{item['relative_path']} is not inside its mapped folder here.", "warning")
        return
    new_folder = _parent(inside)
    if new_folder != _parent(local):
        root_id = _library_root_id(state, mapping)
        if root_id is None:
            _log(state, "The folder of this track is no longer a watched folder.", "warning")
            return
        state.context.files.move_track(track.track_id, root_id, new_folder)
        local = f"{new_folder}/{_name(local)}" if new_folder else _name(local)
        state.result.moved += 1
        _log(state, f"Moved here to follow the server: {item['relative_path']}.")
    if _name(inside) != _name(local):
        _log(
            state,
            f"Renamed on the server to {item['relative_path']}; the name here is kept.",
            "warning",
        )
    # The link keeps the path this device now has, so the push sends no move back.
    _set_server_path(state, track.track_id, _join(mapping.server_subpath, local))


def _gone(state: _Pass, item_id: str, *, purged: bool) -> None:
    """A trashed or purged item: a linked track gets a conflict; a server-only track leaves."""
    link = _link(state, item_id)
    state_text = "purged" if purged else "trashed"
    if link is not None:
        name = str(link["server_path"] or item_id)
        _conflict(
            state,
            track_id=str(link["track_id"]),
            item_id=item_id,
            kind="deleted_on_server",
            local={"relative_path": link["server_path"], "sha256": link["local_sha256"]},
            server={"item_id": item_id, "state": state_text},
            message=f"{name} was {state_text} on the server; the file here is kept.",
        )
        return
    row = server_item_row(state.store.connection(), item_id)
    if row is None:
        return
    hide_server_only(state.context, state.store, item_id)
    if purged:
        _drop_known(state, item_id)
    state.result.removed += 1
    _log(state, f"{row['relative_path']} was {state_text} on the server (server only, removed).")


def _refresh_known(state: _Pass, item: dict[str, Any]) -> None:
    """A server-only item changed: its row and its server-only track take the new values."""
    row = server_row(item)
    remember_item(state.store, item)
    show_as_server_only(
        state.context, state.store, row.item_id, row.relative_path, row.metadata_json
    )


def _drop_known(state: _Pass, item_id: str) -> None:
    """Forget a server item that is no longer under a mapped folder (or was purged)."""
    hide_server_only(state.context, state.store, item_id)
    with state.store.transaction() as conn:
        conn.execute("DELETE FROM remote_server_items WHERE item_id = ?", (item_id,))


# -- helpers ---------------------------------------------------------------------------------
def _get(state: _Pass, item_id: str) -> dict[str, Any] | None:
    """The present item, or None when the server no longer has it under that identifier."""
    try:
        return state.client.get_item(item_id)
    except ApiError as error:
        if error.status == 404:
            return None
        raise


def _link(state: _Pass, item_id: str) -> sqlite3.Row | None:
    return (
        state.store.connection()
        .execute(
            "SELECT track_id, item_id, item_revision, local_sha256, server_path"
            " FROM remote_links WHERE item_id = ?",
            (item_id,),
        )
        .fetchone()
    )


def _location(
    mappings: list[FolderMapping], root_id: str, relative: str
) -> tuple[FolderMapping, str] | None:
    """The mapping that holds an item, and its path inside that mapping (the deepest wins)."""
    best: tuple[FolderMapping, str] | None = None
    for mapping in mappings:
        if mapping.server_root_id != root_id:
            continue
        inside = _inside(mapping.server_subpath, relative)
        if inside is None:
            continue
        if best is None or len(mapping.server_subpath) > len(best[0].server_subpath):
            best = (mapping, inside)
    return best


def _inside(subpath: str, relative: str) -> str | None:
    if not subpath:
        return relative
    prefix = subpath + "/"
    return relative[len(prefix) :] if relative.startswith(prefix) else None


def _folder_of(mapping: FolderMapping, inside: str) -> Path:
    return mapping.local_folder.joinpath(*PurePosixPath(inside).parts[:-1])


def _local_at(state: _Pass, mapping: FolderMapping, inside: str) -> LibraryTrack | None:
    """The library track at the path that ``inside`` takes under the mapped folder, if any."""
    if state.by_path is None:
        state.by_path = {
            _key(track.path): track
            for track in state.context.library.tracks(state.context.library.track_ids())
        }
    expected = mapping.local_folder.joinpath(*PurePosixPath(inside).parts)
    return state.by_path.get(_key(expected))


def _track(state: _Pass, track_id: str) -> LibraryTrack | None:
    found = state.context.library.tracks([track_id])
    return found[0] if found else None


def _hashes_of(state: _Pass, track_id: str) -> FileHashes | None:
    """The SHA-256 and audio hash of a local track, from the cache when the file did not change."""
    return hash_tracks(state.context, [track_id], state.job).hashes.get(track_id)


def _library_root_id(state: _Pass, mapping: FolderMapping) -> str | None:
    wanted = _key(Path(mapping.local_root_path))
    for root in state.context.library.roots():
        if _key(root.path) == wanted:
            return root.root_id
    return None


def _set_link_version(
    state: _Pass, track_id: str, revision: int, sha256: str, item: dict[str, Any]
) -> None:
    """The link now has the revision and the SHA-256 the server has (the file matches them)."""
    with state.store.transaction() as conn:
        conn.execute(
            "UPDATE remote_links SET item_revision = ?, local_sha256 = ?, audio_hash = ?"
            " WHERE track_id = ?",
            (revision, sha256, _text_or_none(item.get("audio_hash")), track_id),
        )
        upsert_server_item(conn, server_row(item))


def _set_server_path(state: _Pass, track_id: str, server_path: str) -> None:
    with state.store.transaction() as conn:
        conn.execute(
            "UPDATE remote_links SET server_path = ? WHERE track_id = ?", (server_path, track_id)
        )


def _conflict(
    state: _Pass,
    *,
    track_id: str,
    item_id: str,
    kind: str,
    local: dict[str, Any],
    server: dict[str, Any],
    message: str,
) -> None:
    """Record a conflict for a track and an item, once while it is open (plan 126.6 resolves it).

    A conflict the person dismissed (kept for later, hidden from Tasks) is reopened by a new change
    on the server: the change is news, so the conflict shows again with the new versions.
    """
    with state.store.transaction() as conn:
        row = conn.execute(
            "SELECT conflict_id, local_json FROM remote_conflicts WHERE track_id = ?"
            " AND item_id = ? AND state <> 'resolved'",
            (track_id, item_id),
        ).fetchone()
        if row is not None and not is_dismissed(row["local_json"]):
            return
        if row is not None:
            conn.execute(
                "UPDATE remote_conflicts SET state = ?, local_json = ?, server_json = ?,"
                " created_at_utc = ? WHERE conflict_id = ?",
                (
                    CONFLICT_OPEN,
                    json.dumps({"kind": kind, **local}, ensure_ascii=False, sort_keys=True),
                    json.dumps({"kind": kind, **server}, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                    row["conflict_id"],
                ),
            )
        else:
            insert_conflict(
                conn,
                track_id=track_id,
                item_id=item_id,
                local={"kind": kind, **local},
                server={"kind": kind, **server},
                state=CONFLICT_OPEN,
            )
        write_log(conn, message, "warning")
    state.result.conflicts += 1


def _server_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": str(item["item_id"]),
        "relative_path": str(item["relative_path"]),
        "sha256": item.get("sha256"),
        "revision": _count(item.get("revision")),
        "size_bytes": _count(item.get("size_bytes")),
    }


def _log(state: _Pass, text: str, level: str = "info") -> None:
    with state.store.transaction() as conn:
        write_log(conn, text, level)


def _drop_import(store: RemoteStore, item_id: str, text: str) -> None:
    with store.transaction() as conn:
        conn.execute("DELETE FROM remote_imports WHERE item_id = ?", (item_id,))
        write_log(conn, text, "warning")


def _incoming_folder(context: PluginContext) -> Path:
    folder = context.data_dir / "incoming"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _rescan(context: PluginContext, folder: Path) -> None:
    context.library.rescan(folder)


def _revision(payload: dict[str, Any]) -> int:
    return _count(payload.get("revision"))


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _key(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _relative_in(root: str, path: Path) -> str | None:
    """The POSIX path of ``path`` inside the folder ``root``, or None when it is outside."""
    base = os.path.abspath(root).rstrip("\\/")
    full = os.path.abspath(path)
    if not os.path.normcase(full).startswith(os.path.normcase(base) + os.sep):
        return None
    return full[len(base) + 1 :].replace("\\", "/")


def _parent(posix: str) -> str:
    return "/".join(PurePosixPath(posix).parts[:-1])


def _name(posix: str) -> str:
    return PurePosixPath(posix).name


def _join(subpath: str, relative: str) -> str:
    return "/".join(part for part in (subpath, relative) if part)
