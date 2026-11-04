"""Push: this computer's changes sent to the server (plan 126.3).

``detect_changes`` looks at the library tracks under the mapped folders and queues what the server
does not have yet: an upload (the track has no link), a replacement (the track is linked and its
SHA-256 is no longer the link's) or a move (linked, same SHA-256, another path on the server). It
reads and hashes files and sends nothing. ``run_queue`` sends the pending operations in order.

A held track is a track with a conflict row the person has still to decide (state ``open`` or
``decide_later``, plan 126.6). Nothing is queued for it and ``run_queue`` does not send its pending
rows: a track that waits for the person must never reach the server, because a track whose tags
differ from its server copy has no link yet and would otherwise be uploaded again as a new item.

Files are only read, each chunk under its own read lease; nothing here writes, moves or deletes a
file of this computer. An upload keeps the id the server gave it in its queue row (``upload_id``
in the payload) as soon as it is opened, so a cut upload resumes from the bytes the server holds.

Queue states: ``pending`` (to send), ``running``, ``done``, ``blocked`` (a path taken or a stale
revision: a conflict row waits for the person, plan 126.6), ``failed`` (a readable reason, not
retried by itself).
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from mtee.plugins.api import JobContext, PluginContext

from .client import ApiError, NetworkError, RemoteClient, UploadOffsetError
from .first_match import OwnedTrack, owned_tracks
from .hashing import hash_tracks, path_key, trusted_hashes
from .store import (
    CONFLICT_DECIDE_LATER,
    RemoteStore,
    ServerRow,
    insert_conflict,
    insert_link,
    new_id,
    upsert_server_item,
    utc_now,
    write_log,
)

UPLOAD = "upload"
REPLACE = "replace"
MOVE = "move"
PUSH_KINDS = (UPLOAD, REPLACE, MOVE)

PENDING = "pending"
RUNNING = "running"
DONE = "done"
BLOCKED = "blocked"
FAILED = "failed"

# The kinds of conflict rows this milestone writes; plan 126.6 shows them in the Conflicts section.
PATH_TAKEN = "path_taken"
STALE_REVISION = "stale_revision"
CONFLICT = "conflict"
CONFLICT_OPEN = "open"

DEFAULT_CHUNK_BYTES = 8 * 1024 * 1024
_NANOSECONDS = 1_000_000_000
_FILE_CHANGED = "The file changed after it was queued; it is sent once it has settled."
_BUSY = "The file is busy (a tag write is running); it is sent in a later pass."
_BAD_HASH = "The file changed while it was sent; it is hashed again and sent in a later pass."
_NO_LONGER_A_FILE = "This track is no longer a readable file of the library."
_FILE_MISSING = "The file is not on this computer at the moment; it is sent when it is back."
_UNREADABLE = "The server answered with something MTEE cannot read."
_STALL_LIMIT = 3

_SENT = "sent"
_BLOCKED_OUTCOME = "blocked"
_FAILED_OUTCOME = "failed"
_DEFERRED = "deferred"
_OFFLINE = "offline"

ProgressCallback = Callable[[int, int], None]


@dataclass
class DetectReport:
    """What one detection pass queued, refreshed or skipped."""

    uploads: int = 0
    replacements: int = 0
    moves: int = 0
    refreshed: int = 0
    dropped: int = 0
    waiting: int = 0  # changed less than the idle delay ago: skipped this pass
    missing: int = 0  # the file is not on this computer
    unhashed: int = 0  # the file could not be read or hashed
    held: int = 0  # a conflict waits for the person: nothing is queued for it (plan 126.6)


@dataclass
class QueueReport:
    """What one run sent: the counts per outcome, and how many operations still wait."""

    sent: int = 0
    blocked: int = 0
    failed: int = 0
    pending: int = 0
    stopped: bool = False  # the server could not be reached, so the run ended early


class _NoJob:
    """Stands in for a job when a pass runs without one: nothing to cancel or report."""

    def raise_if_cancelled(self) -> None:
        return None

    def report_progress(self, progress: float) -> None:
        return None


_NO_JOB = cast(JobContext, _NoJob())


class _FileChangedError(Exception):
    """The file is not the one the queue row was made for: the operation waits for a new pass."""


@dataclass(frozen=True)
class _Local:
    """A settled local track, hashed, with the server path it belongs to."""

    track_id: str
    root_id: str
    server_path: str
    fingerprint: dict[str, int]
    sha256: str
    audio_hash: str | None


@dataclass
class _Op:
    """A queue row, with its payload as the run last saw it."""

    op_id: str
    kind: str
    track_id: str | None
    item_id: str | None
    payload: dict[str, Any]


# -- detection -----------------------------------------------------------------------------
def detect_changes(
    context: PluginContext,
    store: RemoteStore,
    *,
    idle_delay_s: float,
    now: float,
    job: JobContext | None = None,
) -> DetectReport:
    """Queue what the server needs for the mapped folders, and refresh the rows already queued.

    Nothing is sent. A track whose file changed later than ``now - idle_delay_s`` (a time of
    ``time.time()``) is skipped: it may still be written, or downloaded. A track with an operation
    already pending is not queued again; its payload is refreshed when its file changed. A track
    the first match left out as a second copy (``remote_excluded``) is never queued.

    A held track (an open or decide-later conflict row, see ``_held_tracks``) is never queued and
    its pending rows are left as they are: it is counted in ``report.held``. The person decides
    which version wins first. A track with no link whose tags differ from its server copy is the
    case this guards: queued as an upload, it would arrive as a second item with the same audio.
    The held set is read once for the whole pass.
    """
    report = DetectReport()
    mappings = store.mappings()
    if not mappings:
        return report
    excluded = _excluded_tracks(store)
    held = _held_tracks(store)
    settled: dict[str, tuple[OwnedTrack, dict[str, int]]] = {}
    for owned in owned_tracks(context, mappings):
        if not owned.readable or owned.track.track_id in excluded:
            continue
        if owned.track.track_id in held:
            report.held += 1
            continue
        try:
            info = os.stat(owned.track.path)
        except OSError:
            report.missing += 1
            continue
        # With no idle delay nothing waits. A file saved in the same clock tick as ``now`` must
        # not wait either: float rounding made its mtime look later than ``now``.
        if idle_delay_s > 0 and info.st_mtime_ns / _NANOSECONDS > now - idle_delay_s:
            report.waiting += 1
            continue
        fingerprint = {"size": info.st_size, "mtime_ns": info.st_mtime_ns}
        settled[owned.track.track_id] = (owned, fingerprint)
    if not settled:
        return report

    # An unchanged file is answered by the cache in one batch, without a lease or a read; only
    # the files that changed (or were never hashed) are hashed under their read lease.
    keys = {track_id: path_key(owned.track.path) for track_id, (owned, _f) in settled.items()}
    trusted = trusted_hashes(
        store,
        {
            keys[track_id]: (fingerprint["size"], fingerprint["mtime_ns"])
            for track_id, (_owned, fingerprint) in settled.items()
        },
    )
    known = {track_id: trusted[key] for track_id, key in keys.items() if key in trusted}
    unknown = [track_id for track_id in settled if track_id not in known]
    hashed = hash_tracks(context, unknown, job or _NO_JOB)
    report.unhashed = len(hashed.skipped)
    all_hashes = {**known, **hashed.hashes}
    locals_: list[_Local] = []
    for track_id, (owned, fingerprint) in settled.items():
        hashes = all_hashes.get(track_id)
        if hashes is None:
            continue
        mapping = mappings[owned.mapping]
        locals_.append(
            _Local(
                track_id=track_id,
                root_id=mapping.server_root_id,
                server_path=_join(mapping.server_subpath, owned.relative),
                fingerprint=fingerprint,
                sha256=hashes.sha256,
                audio_hash=hashes.audio_hash,
            )
        )
    with store.transaction() as conn:
        ids = [local.track_id for local in locals_]
        links = _links_of(conn, ids)
        open_rows = _open_rows_of(conn, ids)
        for local in locals_:
            _reconcile(
                conn,
                local,
                report,
                link=links.get(local.track_id),
                rows=open_rows.get(local.track_id, []),
            )
        if report.uploads or report.replacements or report.moves:
            write_log(
                conn,
                f"Queued {report.uploads} uploads, {report.replacements} replacements and "
                f"{report.moves} moves.",
            )
    return report


def _excluded_tracks(store: RemoteStore) -> set[str]:
    """The tracks the first match left out as second copies: they are never sent (126.4)."""
    rows = store.connection().execute("SELECT track_id FROM remote_excluded").fetchall()
    return {str(row["track_id"]) for row in rows}


def _held_tracks(store: RemoteStore) -> set[str]:
    """The tracks a conflict waits for: their open or decide-later rows (one query).

    A conflict that is resolved releases its track: the next pass treats it as any other track.
    """
    rows = (
        store.connection()
        .execute(
            "SELECT DISTINCT track_id FROM remote_conflicts"
            " WHERE state IN (?, ?) AND track_id IS NOT NULL",
            (CONFLICT_OPEN, CONFLICT_DECIDE_LATER),
        )
        .fetchall()
    )
    return {str(row["track_id"]) for row in rows}


def _reconcile(
    conn: sqlite3.Connection,
    local: _Local,
    report: DetectReport,
    *,
    link: sqlite3.Row | None,
    rows: list[sqlite3.Row],
) -> None:
    """Make the open queue rows of one track agree with what the track needs now.

    ``link`` and ``rows`` are the track's link and open queue rows, read for the whole pass by
    ``_links_of`` and ``_open_rows_of`` in the same transaction: each call changes the rows of its
    own track only, so the rows read for the others stay right.
    """
    wanted: tuple[str, dict[str, Any], str | None] | None
    if link is None:
        wanted = (UPLOAD, _upload_payload(local), None)
    elif local.sha256 != link["local_sha256"]:
        wanted = (REPLACE, _replace_payload(local, link), str(link["item_id"]))
    elif link["server_path"] is not None and link["server_path"] != local.server_path:
        wanted = (MOVE, _move_payload(local, link), str(link["item_id"]))
    else:
        wanted = None

    wanted_kind = wanted[0] if wanted is not None else None
    for row in rows:
        if row["state"] == PENDING and row["kind"] != wanted_kind:
            conn.execute("DELETE FROM remote_queue WHERE op_id = ?", (row["op_id"],))
            report.dropped += 1
    if wanted is None:
        return
    kind, payload, item_id = wanted
    same = [row for row in rows if row["kind"] == kind]
    if not same:
        _enqueue(conn, kind, local.track_id, item_id, payload)
        if kind == UPLOAD:
            report.uploads += 1
        elif kind == REPLACE:
            report.replacements += 1
        else:
            report.moves += 1
        return
    pending = [row for row in same if row["state"] == PENDING]
    if pending:
        _refresh(conn, pending[0], payload, report)


def _links_of(conn: sqlite3.Connection, track_ids: list[str]) -> dict[str, sqlite3.Row]:
    """The link of each track that has one, read in batches."""
    found: dict[str, sqlite3.Row] = {}
    for chunk in _batches(track_ids):
        marks = ", ".join("?" for _ in chunk)
        for row in conn.execute(
            "SELECT track_id, item_id, item_revision, local_sha256, server_path FROM remote_links"
            f" WHERE track_id IN ({marks})",
            chunk,
        ):
            found[str(row["track_id"])] = row
    return found


def _open_rows_of(conn: sqlite3.Connection, track_ids: list[str]) -> dict[str, list[sqlite3.Row]]:
    """The open push operations of each track, oldest first, read in batches."""
    found: dict[str, list[sqlite3.Row]] = {}
    kinds = ", ".join("?" for _ in PUSH_KINDS)
    for chunk in _batches(track_ids):
        marks = ", ".join("?" for _ in chunk)
        for row in conn.execute(
            "SELECT track_id, op_id, kind, state, payload_json FROM remote_queue"
            f" WHERE track_id IN ({marks}) AND kind IN ({kinds}) AND state <> ? ORDER BY rowid",
            (*chunk, *PUSH_KINDS, DONE),
        ):
            found.setdefault(str(row["track_id"]), []).append(row)
    return found


def _batches(values: list[str], size: int = 400) -> list[list[str]]:
    return [values[start : start + size] for start in range(0, len(values), size)]


def _enqueue(
    conn: sqlite3.Connection, kind: str, track_id: str, item_id: str | None, payload: dict[str, Any]
) -> None:
    now = utc_now()
    conn.execute(
        "INSERT INTO remote_queue (op_id, kind, track_id, item_id, state, attempts, payload_json,"
        " created_at_utc, updated_at_utc) VALUES (?, ?, ?, ?, 'pending', 0, ?, ?, ?)",
        (new_id(), kind, track_id, item_id, _dump(payload), now, now),
    )


def _refresh(
    conn: sqlite3.Connection, row: sqlite3.Row, payload: dict[str, Any], report: DetectReport
) -> None:
    """Replace the payload of a pending row when the file (or the link) changed since.

    A replaced payload drops the upload the row was sending: the server keeps those bytes, so
    the run cancels that upload (``stale_upload_id``) before it opens the new one.
    """
    old = _load(row["payload_json"])
    if all(old.get(key) == value for key, value in payload.items()):
        return
    merged = dict(payload)
    old_upload = old.get("upload_id")
    if isinstance(old_upload, str):
        merged["stale_upload_id"] = old_upload
    elif isinstance(old.get("stale_upload_id"), str):
        merged["stale_upload_id"] = old["stale_upload_id"]
    conn.execute(
        "UPDATE remote_queue SET payload_json = ?, updated_at_utc = ? WHERE op_id = ?",
        (_dump(merged), utc_now(), row["op_id"]),
    )
    report.refreshed += 1


def _upload_payload(local: _Local) -> dict[str, Any]:
    return {
        "root_id": local.root_id,
        "relative_path": local.server_path,
        "size": local.fingerprint["size"],
        "sha256": local.sha256,
        "audio_hash": local.audio_hash,
        "fingerprint": local.fingerprint,
    }


def _replace_payload(local: _Local, link: sqlite3.Row) -> dict[str, Any]:
    payload = _upload_payload(local)
    payload["item_id"] = str(link["item_id"])
    payload["base_revision"] = int(link["item_revision"])
    return payload


def _move_payload(local: _Local, link: sqlite3.Row) -> dict[str, Any]:
    return {"item_id": str(link["item_id"]), "relative_path": local.server_path}


# -- the run -------------------------------------------------------------------------------
def run_queue(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    job: JobContext,
    *,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    on_progress: ProgressCallback | None = None,
) -> QueueReport:
    """Send the pending operations in order; return what happened to each.

    ``on_progress(index, total)`` runs before each operation. A cancelled job stops between two
    chunks and raises (``JobCancelledError``); the operation then waits again, with its upload id,
    so the next run resumes it. A server that cannot be reached ends the run; the operation stays
    pending and counts one more attempt.
    """
    report = QueueReport()
    with store.transaction() as conn:
        conn.execute(
            "UPDATE remote_queue SET state = ?, updated_at_utc = ? WHERE state = ?",
            (PENDING, utc_now(), RUNNING),
        )
    rows = (
        store.connection()
        .execute(
            "SELECT op_id FROM remote_queue WHERE state = ? ORDER BY rowid",
            (PENDING,),
        )
        .fetchall()
    )
    total = len(rows)
    held = _held_tracks(store)
    for index, row in enumerate(rows):
        job.raise_if_cancelled()
        if on_progress is not None:
            on_progress(index, total)
        op = _load_op(store, str(row["op_id"]))
        if op is None:
            continue
        if op.track_id is not None and op.track_id in held:
            # A track a conflict waits for keeps its pending row until the person decides.
            continue
        outcome = _send(context, store, client, op, job, chunk_bytes)
        if outcome == _SENT:
            report.sent += 1
        elif outcome == _BLOCKED_OUTCOME:
            report.blocked += 1
        elif outcome == _FAILED_OUTCOME:
            report.failed += 1
        elif outcome == _OFFLINE:
            report.stopped = True
            break
    report.pending = pending_count(store)
    return report


def pending_count(store: RemoteStore) -> int:
    """The operations waiting to be sent (the Apply button counts them)."""
    row = (
        store.connection()
        .execute("SELECT COUNT(*) AS n FROM remote_queue WHERE state = ?", (PENDING,))
        .fetchone()
    )
    return int(row["n"])


def _load_op(store: RemoteStore, op_id: str) -> _Op | None:
    row = (
        store.connection()
        .execute(
            "SELECT op_id, kind, track_id, item_id, payload_json, state FROM remote_queue"
            " WHERE op_id = ?",
            (op_id,),
        )
        .fetchone()
    )
    if row is None or row["state"] != PENDING:
        return None
    return _Op(
        op_id=str(row["op_id"]),
        kind=str(row["kind"]),
        track_id=row["track_id"],
        item_id=row["item_id"],
        payload=_load(row["payload_json"]),
    )


def _send(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    op: _Op,
    job: JobContext,
    chunk_bytes: int,
) -> str:
    if op.kind == MOVE:
        return _send_move(context, store, client, op)
    if op.kind in (UPLOAD, REPLACE):
        return _send_upload(context, store, client, op, job, chunk_bytes)
    _set_op(store, op, FAILED, error=f"Unknown operation {op.kind}.")
    return _FAILED_OUTCOME


def _send_move(context: PluginContext, store: RemoteStore, client: RemoteClient, op: _Op) -> str:
    item_id = op.payload.get("item_id", op.item_id)
    relative = op.payload.get("relative_path")
    if not isinstance(item_id, str) or not isinstance(relative, str) or op.track_id is None:
        _set_op(store, op, FAILED, error="The move has no item or no path.")
        return _FAILED_OUTCOME
    _set_op(store, op, RUNNING)
    try:
        item = client.move_item(item_id, relative)
    except NetworkError as error:
        return _offline(store, op, error)
    except ApiError as error:
        return _api_failure(context, store, client, op, error)
    except BaseException:
        _set_op(store, op, PENDING)
        raise
    _finish_move(store, op, item)
    return _SENT


def _finish_move(store: RemoteStore, op: _Op, item: dict[str, Any]) -> None:
    relative = _text(item, "relative_path")
    with store.transaction() as conn:
        conn.execute(
            "UPDATE remote_links SET server_path = ? WHERE track_id = ?",
            (relative, op.track_id),
        )
        upsert_server_item(conn, _server_row(item))
        _mark_done(conn, op)
        write_log(conn, f"Moved on the server to {relative}.")


def _send_upload(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    op: _Op,
    job: JobContext,
    chunk_bytes: int,
) -> str:
    if op.track_id is None or not _is_complete(op.payload):
        # Queued by the first match, not hashed yet: the next detection pass fills it in.
        return _DEFERRED
    _set_op(store, op, RUNNING)
    try:
        stale = op.payload.pop("stale_upload_id", None)
        if isinstance(stale, str):
            _cancel_quietly(client, stale)
            _save_payload(store, op)
        item = _transfer(context, store, client, op, job, chunk_bytes)
    except _FileChangedError:
        _set_op(store, op, PENDING, error=_FILE_CHANGED)
        return _DEFERRED
    except FileNotFoundError:
        # The file may come back (a drive plugged in again): it waits, and counts an attempt.
        _set_op(store, op, PENDING, error=_FILE_MISSING, attempts=True)
        return _DEFERRED
    except LookupError:
        _discard_upload(client, op)
        _set_op(store, op, FAILED, error=_NO_LONGER_A_FILE)
        return _FAILED_OUTCOME
    except ValueError:
        _discard_upload(client, op)
        _set_op(store, op, FAILED, error=_NO_LONGER_A_FILE)
        return _FAILED_OUTCOME
    except TimeoutError:
        _set_op(store, op, PENDING, error=_BUSY)
        return _DEFERRED
    except OSError as error:
        reason = f"The file cannot be read: {error.strerror or error}."
        _set_op(store, op, PENDING, error=reason, attempts=True)
        return _DEFERRED
    except NetworkError as error:
        return _offline(store, op, error)
    except ApiError as error:
        return _api_failure(context, store, client, op, error)
    except BaseException:
        _set_op(store, op, PENDING)
        raise
    _finish_upload(store, op, item)
    return _SENT


def _transfer(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    op: _Op,
    job: JobContext,
    chunk_bytes: int,
) -> dict[str, Any]:
    """Resume the upload the server holds, or open one; send the bytes, commit, return the item.

    The upload id is in the payload from the moment it is opened, so a run cut short resumes
    from the byte the server reports. An upload the server holds as ``done`` was committed
    before this run could record it: its item is the result, when it is the same file.
    """
    held = op.payload.get("upload_id")
    status = _status_of(client, held) if isinstance(held, str) else None
    state = None if status is None else status.get("state")
    if state == "done":
        found = _committed_item(client, op)
        if found is not None:
            return found
    if status is not None and state in ("open", "conflict") and isinstance(held, str):
        upload_id = held
        offset = _count(status.get("received_bytes"))
    else:
        upload_id = _open(store, client, op)
        offset = 0
    _send_chunks(context, client, op, upload_id, offset, job, chunk_bytes)
    return _item_of(client.commit_upload(upload_id))


def _open(store: RemoteStore, client: RemoteClient, op: _Op) -> str:
    """Open the upload of ``op`` on the server and keep its id in the payload at once."""
    payload = op.payload
    payload.pop("upload_id", None)
    replace = op.kind == REPLACE
    opened = client.open_upload(
        root_id=str(payload["root_id"]),
        relative_path=str(payload["relative_path"]),
        size_bytes=int(payload["size"]),
        sha256=str(payload["sha256"]),
        base_item_id=str(payload["item_id"]) if replace else None,
        base_revision=int(payload["base_revision"]) if replace else None,
    )
    upload_id = str(opened["upload_id"])
    payload["upload_id"] = upload_id
    _save_payload(store, op)
    return upload_id


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _send_chunks(
    context: PluginContext,
    client: RemoteClient,
    op: _Op,
    upload_id: str,
    offset: int,
    job: JobContext,
    chunk_bytes: int,
) -> None:
    """Send the bytes from ``offset`` on, one chunk per read lease, checking the file each time."""
    track_id = op.track_id
    payload = op.payload
    size = int(payload["size"])
    expected = payload["fingerprint"]
    stalls = 0
    while offset < size:
        job.raise_if_cancelled()
        with context.files.read_lease(str(track_id)) as path:
            if _fingerprint(path) != expected:
                raise _FileChangedError()
            with open(path, "rb") as handle:
                handle.seek(offset)
                data = handle.read(min(chunk_bytes, size - offset))
        if not data:
            raise _FileChangedError()
        try:
            offset = client.upload_chunk(upload_id, offset, data, size)
        except UploadOffsetError as error:
            # The server holds other bytes: continue where it stands, not where this run was.
            stalls = stalls + 1 if error.offset == offset else 0
            if stalls > _STALL_LIMIT:
                raise ApiError(
                    416,
                    "range_not_satisfiable",
                    "The server keeps refusing the bytes of this upload.",
                ) from None
            offset = error.offset


def _committed_item(client: RemoteClient, op: _Op) -> dict[str, Any] | None:
    """The item of an upload the server committed before this run could record it, if any."""
    payload = op.payload
    if op.kind == REPLACE:
        item = client.get_item(str(payload["item_id"]))
        return item if item.get("sha256") == payload["sha256"] else None
    relative = str(payload["relative_path"])
    for item in client.all_items(root_id=str(payload["root_id"]), prefix=relative):
        if item.get("relative_path") == relative and item.get("sha256") == payload["sha256"]:
            return item
    return None


def _status_of(client: RemoteClient, upload_id: str) -> dict[str, Any] | None:
    """The state of an upload; None when the server does not know it any more."""
    try:
        return client.upload_status(upload_id)
    except ApiError as error:
        if error.status == 404:
            return None
        raise


def _finish_upload(store: RemoteStore, op: _Op, item: dict[str, Any]) -> None:
    """Record a committed upload or replacement: its link, the server view and the queue row."""
    payload = op.payload
    item_id = _text(item, "item_id")
    revision = _integer(item, "revision")
    relative = _text(item, "relative_path")
    audio_hash = payload.get("audio_hash")
    with store.transaction() as conn:
        if op.kind == UPLOAD:
            assert op.track_id is not None
            linked = insert_link(
                conn,
                track_id=op.track_id,
                item_id=item_id,
                item_revision=revision,
                local_sha256=str(payload["sha256"]),
                audio_hash=audio_hash if isinstance(audio_hash, str) else None,
                server_path=relative,
            )
            if not linked:
                _update_link(conn, op, item_id, revision, relative)
            write_log(conn, f"Sent {relative} to the server.")
        else:
            _update_link(conn, op, item_id, revision, relative)
            write_log(conn, f"Replaced {relative} on the server (revision {revision}).")
        upsert_server_item(conn, _server_row(item))
        _mark_done(conn, op)


def _update_link(
    conn: sqlite3.Connection, op: _Op, item_id: str, revision: int, relative: str
) -> None:
    audio_hash = op.payload.get("audio_hash")
    conn.execute(
        "UPDATE remote_links SET item_id = ?, item_revision = ?, local_sha256 = ?, audio_hash = ?,"
        " server_path = ? WHERE track_id = ?",
        (
            item_id,
            revision,
            op.payload.get("sha256"),
            audio_hash if isinstance(audio_hash, str) else None,
            relative,
            op.track_id,
        ),
    )


def _api_failure(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    op: _Op,
    error: ApiError,
) -> str:
    """Turn a refusal of the server into the state the operation takes; return the outcome."""
    if error.code == "path_taken":
        _discard_upload(client, op)
        _block(store, op, PATH_TAKEN, error.message)
        return _BLOCKED_OUTCOME
    if error.code == "conflict":
        _discard_upload(client, op)
        _block(store, op, STALE_REVISION if op.kind == REPLACE else CONFLICT, error.message)
        return _BLOCKED_OUTCOME
    if error.code == "quota_exceeded":
        _discard_upload(client, op)
        _set_op(store, op, FAILED, error=error.message)
        context.notify(f"Not sent to the server: {error.message}")
        return _FAILED_OUTCOME
    if error.code == "bad_hash":
        # The bytes were not the ones hashed: the next pass hashes the file again, from scratch.
        _discard_upload(client, op)
        _forget_hashes(context, store, op.track_id)
        _set_op(store, op, PENDING, error=_BAD_HASH)
        return _DEFERRED
    if error.status >= 500:
        _set_op(store, op, PENDING, error=error.message, attempts=True)
        return _DEFERRED
    _discard_upload(client, op)
    _set_op(store, op, FAILED, error=error.message)
    return _FAILED_OUTCOME


def _block(store: RemoteStore, op: _Op, label: str, message: str) -> None:
    """Hold the operation for the person and write the conflict row that shows it (plan 126.6)."""
    item_id = op.item_id if op.item_id is not None else op.payload.get("item_id")
    local = {
        "kind": label,
        "message": message,
        "relative_path": op.payload.get("relative_path"),
        "size": op.payload.get("size"),
        "sha256": op.payload.get("sha256"),
        "base_revision": op.payload.get("base_revision"),
    }
    server = {"kind": label, "item_id": item_id, "message": message}
    with store.transaction() as conn:
        conn.execute(
            "UPDATE remote_queue SET state = ?, last_error = ?, payload_json = ?,"
            " updated_at_utc = ? WHERE op_id = ?",
            (BLOCKED, message, _dump(op.payload), utc_now(), op.op_id),
        )
        insert_conflict(
            conn,
            track_id=op.track_id,
            item_id=item_id if isinstance(item_id, str) else None,
            local=local,
            server=server,
            state=CONFLICT_OPEN,
        )
        write_log(conn, f"Not sent, waiting for you: {message}", "warning")


def _offline(store: RemoteStore, op: _Op, error: NetworkError) -> str:
    _set_op(store, op, PENDING, error=str(error), attempts=True)
    return _OFFLINE


def _discard_upload(client: RemoteClient, op: _Op) -> None:
    """Forget the upload of ``op`` and cancel it on the server, when it has one."""
    upload_id = op.payload.pop("upload_id", None)
    if isinstance(upload_id, str):
        _cancel_quietly(client, upload_id)


def _cancel_quietly(client: RemoteClient, upload_id: str) -> None:
    # An upload nobody commits keeps its bytes on the server; nothing else depends on them.
    with contextlib.suppress(ApiError, NetworkError):
        client.cancel_upload(upload_id)


def _forget_hashes(context: PluginContext, store: RemoteStore, track_id: str | None) -> None:
    """Drop the cached hashes of a track's file, so the next pass hashes it again."""
    if track_id is None:
        return
    try:
        with context.files.read_lease(track_id) as path:
            key = os.path.normcase(os.path.abspath(path))
    except (LookupError, OSError, ValueError):
        return
    with store.transaction() as conn:
        conn.execute("DELETE FROM remote_hash_cache WHERE path = ?", (key,))


def _set_op(
    store: RemoteStore,
    op: _Op,
    state: str,
    *,
    error: str | None = None,
    attempts: bool = False,
) -> None:
    """Write the state, the error and the payload of an operation in one transaction."""
    bump = ", attempts = attempts + 1" if attempts else ""
    with store.transaction() as conn:
        conn.execute(
            f"UPDATE remote_queue SET state = ?, last_error = ?, payload_json = ?,"
            f" updated_at_utc = ?{bump} WHERE op_id = ?",
            (state, error, _dump(op.payload), utc_now(), op.op_id),
        )


def _save_payload(store: RemoteStore, op: _Op) -> None:
    with store.transaction() as conn:
        conn.execute(
            "UPDATE remote_queue SET payload_json = ?, updated_at_utc = ? WHERE op_id = ?",
            (_dump(op.payload), utc_now(), op.op_id),
        )


def _mark_done(conn: sqlite3.Connection, op: _Op) -> None:
    payload = {key: value for key, value in op.payload.items() if key not in _ID_KEYS}
    conn.execute(
        "UPDATE remote_queue SET state = ?, last_error = NULL, payload_json = ?,"
        " updated_at_utc = ? WHERE op_id = ?",
        (DONE, _dump(payload), utc_now(), op.op_id),
    )


_ID_KEYS = ("upload_id", "stale_upload_id")


# -- helpers -------------------------------------------------------------------------------
def _is_complete(payload: dict[str, Any]) -> bool:
    return (
        isinstance(payload.get("root_id"), str)
        and isinstance(payload.get("relative_path"), str)
        and isinstance(payload.get("sha256"), str)
        and isinstance(payload.get("size"), int)
        and isinstance(payload.get("fingerprint"), dict)
    )


def _fingerprint(path: Path) -> dict[str, int]:
    info = os.stat(path)
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns}


def _join(subpath: str, relative: str) -> str:
    return "/".join(part for part in (subpath, relative) if part)


def _load(text: str | None) -> dict[str, Any]:
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _item_of(body: dict[str, Any]) -> dict[str, Any]:
    item = body.get("item")
    if not isinstance(item, dict):
        raise ApiError(200, "bad_response", _UNREADABLE)
    return item


def _text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise ApiError(200, "bad_response", _UNREADABLE)
    return value


def _integer(item: dict[str, Any], key: str) -> int:
    value = item.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ApiError(200, "bad_response", _UNREADABLE)
    return value


def _server_row(item: dict[str, Any]) -> ServerRow:
    sha256 = item.get("sha256")
    audio_hash = item.get("audio_hash")
    metadata = item.get("metadata")
    updated = item.get("updated_at_utc")
    return ServerRow(
        item_id=_text(item, "item_id"),
        root_id=_text(item, "root_id"),
        relative_path=_text(item, "relative_path"),
        size_bytes=_integer(item, "size_bytes"),
        sha256=sha256 if isinstance(sha256, str) else None,
        audio_hash=audio_hash if isinstance(audio_hash, str) else None,
        revision=_integer(item, "revision"),
        metadata_json=None
        if metadata is None
        else json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        updated_at_utc=updated if isinstance(updated, str) else utc_now(),
    )
