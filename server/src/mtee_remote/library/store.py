"""Database helpers for roots and items.

Every function that takes a `Transaction` only touches the database, never a file. The caller
opens the transaction (`with db.transaction() as tx:`), so several helpers can share one
commit, and the journal entry of a change is committed together with the change itself.

Conventions used by all helpers:

- `relative_path` is POSIX and relative to the root's folder (never absolute). Files found
  by a scan keep their spelling on disk (NFD names stay NFD); paths sent by clients are NFC.
- An item is *present* (`state = 'present'`) or *trashed*. Only present items own their path:
  the unique index `items_present_path` is on `(root_id, relative_path)` for present rows.
  A violation surfaces as `sqlite3.IntegrityError` from `insert_item`; `replace_item_file`
  never changes the path; `move_item` and `mark_restored` check first and raise
  `ApiError("path_taken")`.
- A new item starts at revision 1 and the revision goes up by 1 each time the file content
  is replaced.
- `updated_at_utc` is refreshed by every helper that changes the row.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mtee.services.library_scanner import AUDIO_SUFFIXES

from mtee_remote import clock, journal
from mtee_remote.config import Settings
from mtee_remote.db import Transaction
from mtee_remote.errors import ApiError
from mtee_remote.ids import new_id

# MTEE's own list of supported audio extensions (the module is Qt-free).
AUDIO_EXTENSIONS: frozenset[str] = AUDIO_SUFFIXES

# Columns `item_public` needs; select these (in any order) from `items`.
ITEM_COLUMNS = (
    "item_id, root_id, relative_path, size_bytes, sha256, audio_hash, hash_state,"
    " revision, metadata_json, duration_us, updated_at_utc"
)

_locks_guard = threading.Lock()
_root_locks: dict[str, threading.Lock] = {}


def root_lock(root_id: str) -> threading.Lock:
    """Return the process-wide lock of one root (the same object for the same id).

    The scanner holds it while it compares the root with the disk. Code that changes files
    inside a root (upload commit, move, trash, restore) must hold it too, so a scan never
    sees a half-done change. It is not reentrant: take one root lock at a time and do not
    call `scan_root` for the same root while holding it.
    """
    with _locks_guard:
        lock = _root_locks.get(root_id)
        if lock is None:
            lock = threading.Lock()
            _root_locks[root_id] = lock
        return lock


def user_library_dir(settings: Settings, library_dir: str) -> Path:
    """Return the user's library folder: `<music volume>/<library_dir>`."""
    return settings.music_dir / library_dir


def root_path(settings: Settings, conn: sqlite3.Connection, root_id: str) -> Path:
    """Return the folder of a root: the user's library folder joined with its `relative_dir`.

    `relative_dir == ''` (library adopted whole) gives the library folder itself.
    Raises `ApiError("not_found")` when the root does not exist.
    """
    row = conn.execute(
        "SELECT r.relative_dir, u.library_dir FROM roots r JOIN users u ON u.user_id = r.user_id"
        " WHERE r.root_id = ?",
        (root_id,),
    ).fetchone()
    if row is None:
        raise ApiError("not_found", "Unknown root.")
    base = user_library_dir(settings, row["library_dir"])
    return base / row["relative_dir"] if row["relative_dir"] else base


def roots_overlap(a: str, b: str) -> bool:
    """True when two root folders (`relative_dir`, '' = the whole library) are equal or nested.

    Compared case-insensitively, so it is also safe on case-insensitive file systems.
    """
    a, b = a.casefold(), b.casefold()
    return not a or not b or a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _now() -> str:
    return clock.to_iso(clock.utc_now())


def _item_row(tx: Transaction, item_id: str) -> sqlite3.Row:
    row = tx.conn.execute(
        "SELECT user_id, root_id, relative_path, revision FROM items WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    if row is None:
        raise ApiError("not_found", "Unknown item.")
    return row


def insert_item(
    tx: Transaction,
    *,
    user_id: str,
    root_id: str,
    relative_path: str,
    size_bytes: int,
    mtime_ns: int,
    inode: int | None,
    device_id: str | None = None,
    sha256: str | None = None,
) -> str:
    """Create a present item at revision 1 and return its new id.

    `hash_state` starts as `pending` even when `sha256` is given: the audio hash and the
    metadata still have to be computed (`set_hashes`). Adds an `item_revisions` row and a
    journal entry `added` `{root_id, relative_path, size_bytes, revision}`. `device_id` is
    the device that uploaded the file (None for a file found by a scan). Raises
    `sqlite3.IntegrityError` when a present item already has that path in the root.
    """
    item_id = new_id()
    now = _now()
    tx.conn.execute(
        "INSERT INTO items(item_id, user_id, root_id, relative_path, size_bytes, mtime_ns, inode,"
        " sha256, hash_state, revision, state, created_at_utc, updated_at_utc)"
        " VALUES (?,?,?,?,?,?,?,?,'pending',1,'present',?,?)",
        (item_id, user_id, root_id, relative_path, size_bytes, mtime_ns, inode, sha256, now, now),
    )
    tx.conn.execute(
        "INSERT INTO item_revisions(item_id, revision, sha256, size_bytes, device_id, at_utc)"
        " VALUES (?,?,?,?,?,?)",
        (item_id, 1, sha256, size_bytes, device_id, now),
    )
    journal.append(
        tx,
        user_id,
        "added",
        item_id,
        {
            "root_id": root_id,
            "relative_path": relative_path,
            "size_bytes": size_bytes,
            "revision": 1,
        },
    )
    return item_id


def replace_item_file(
    tx: Transaction,
    item_id: str,
    *,
    size_bytes: int,
    mtime_ns: int,
    inode: int | None,
    device_id: str | None = None,
    sha256: str | None = None,
) -> int:
    """Record that the item's file content changed and return the new revision (old + 1).

    The path stays. The derived values (`audio_hash`, `metadata_json`, `duration_us`) are
    cleared, `sha256` becomes the given value or NULL, and `hash_state` goes back to
    `pending` so the hash worker recomputes everything. Adds an `item_revisions` row and a
    journal entry `replaced` `{root_id, relative_path, size_bytes, revision}`.
    """
    row = _item_row(tx, item_id)
    revision = int(row["revision"]) + 1
    now = _now()
    tx.conn.execute(
        "UPDATE items SET size_bytes = ?, mtime_ns = ?, inode = ?, sha256 = ?, audio_hash = NULL,"
        " metadata_json = NULL, duration_us = NULL, hash_state = 'pending', revision = ?,"
        " updated_at_utc = ? WHERE item_id = ?",
        (size_bytes, mtime_ns, inode, sha256, revision, now, item_id),
    )
    tx.conn.execute(
        "INSERT INTO item_revisions(item_id, revision, sha256, size_bytes, device_id, at_utc)"
        " VALUES (?,?,?,?,?,?)",
        (item_id, revision, sha256, size_bytes, device_id, now),
    )
    journal.append(
        tx,
        row["user_id"],
        "replaced",
        item_id,
        {
            "root_id": row["root_id"],
            "relative_path": row["relative_path"],
            "size_bytes": size_bytes,
            "revision": revision,
        },
    )
    return revision


def set_hashes(
    tx: Transaction,
    item_id: str,
    revision: int,
    *,
    sha256: str | None,
    audio_hash: str | None,
    metadata_json: str | None,
    duration_us: int | None,
    ok: bool,
) -> bool:
    """Store the computed hashes, only if the item is still at `revision`.

    Returns False (and changes nothing) when the item no longer exists or its revision moved
    on: the file changed while it was being hashed and the new revision is `pending` again.
    Otherwise sets `hash_state` to `done` (`ok`) or `error`, stores the values, copies
    `sha256` into the `item_revisions` row of that revision and adds a journal entry
    `metadata` `{revision, sha256, audio_hash}`.
    """
    row = tx.conn.execute(
        "SELECT user_id FROM items WHERE item_id = ? AND revision = ?", (item_id, revision)
    ).fetchone()
    if row is None:
        return False
    tx.conn.execute(
        "UPDATE items SET sha256 = ?, audio_hash = ?, metadata_json = ?, duration_us = ?,"
        " hash_state = ?, updated_at_utc = ? WHERE item_id = ?",
        (
            sha256,
            audio_hash,
            metadata_json,
            duration_us,
            "done" if ok else "error",
            _now(),
            item_id,
        ),
    )
    tx.conn.execute(
        "UPDATE item_revisions SET sha256 = ? WHERE item_id = ? AND revision = ?",
        (sha256, item_id, revision),
    )
    journal.append(
        tx,
        row["user_id"],
        "metadata",
        item_id,
        {"revision": revision, "sha256": sha256, "audio_hash": audio_hash},
    )
    return True


def _check_path_free(tx: Transaction, root_id: str, relative_path: str, item_id: str) -> None:
    taken = tx.conn.execute(
        "SELECT 1 FROM items WHERE root_id = ? AND relative_path = ? AND state = 'present'"
        " AND item_id != ?",
        (root_id, relative_path, item_id),
    ).fetchone()
    if taken is not None:
        raise ApiError("path_taken", "A file already exists at that path.")


def move_item(tx: Transaction, item_id: str, new_relative_path: str) -> None:
    """Change the item's path inside its root (database only: the caller moves the file).

    Raises `ApiError("path_taken")` (409) when another present item of the root already has
    that path. The revision does not change (same content). Journal entry `moved`
    `{from, to}`. The caller must hold `root_lock(root_id)` when it also renames the file.
    """
    row = _item_row(tx, item_id)
    old = row["relative_path"]
    _check_path_free(tx, row["root_id"], new_relative_path, item_id)
    tx.conn.execute(
        "UPDATE items SET relative_path = ?, updated_at_utc = ? WHERE item_id = ?",
        (new_relative_path, _now(), item_id),
    )
    journal.append(tx, row["user_id"], "moved", item_id, {"from": old, "to": new_relative_path})


def mark_trashed(tx: Transaction, item_id: str) -> None:
    """Set the item's state to `trashed`, which frees its path for another file.

    The row, its revisions and its hashes stay (a restore needs them). Journal entry
    `trashed` `{relative_path}` (the path it had).
    """
    row = _item_row(tx, item_id)
    tx.conn.execute(
        "UPDATE items SET state = 'trashed', updated_at_utc = ? WHERE item_id = ?",
        (_now(), item_id),
    )
    journal.append(tx, row["user_id"], "trashed", item_id, {"relative_path": row["relative_path"]})


def mark_restored(tx: Transaction, item_id: str, relative_path: str) -> None:
    """Set the item back to `present` at `relative_path` (which may differ from the old one).

    Raises `ApiError("path_taken")` (409) when a present item already has that path. Journal
    entry `restored` `{relative_path}`.
    """
    row = _item_row(tx, item_id)
    _check_path_free(tx, row["root_id"], relative_path, item_id)
    tx.conn.execute(
        "UPDATE items SET state = 'present', relative_path = ?, updated_at_utc = ?"
        " WHERE item_id = ?",
        (relative_path, _now(), item_id),
    )
    journal.append(tx, row["user_id"], "restored", item_id, {"relative_path": relative_path})


def remove_missing(tx: Transaction, item_id: str) -> None:
    """Delete the row of a file that vanished from disk outside the server.

    The `item_revisions` rows go with it (cascade). Journal entry `purged`
    `{relative_path, reason: "missing"}` keeps `item_id` so clients can drop their link.
    """
    row = _item_row(tx, item_id)
    tx.conn.execute("DELETE FROM items WHERE item_id = ?", (item_id,))
    journal.append(
        tx,
        row["user_id"],
        "purged",
        item_id,
        {"relative_path": row["relative_path"], "reason": "missing"},
    )


def item_public(row: Mapping[str, Any] | sqlite3.Row) -> dict[str, Any]:
    """Return the client view of an item row (select `ITEM_COLUMNS` to have every field).

    `metadata` is the parsed `metadata_json` (an object) or None. No absolute path appears.
    """
    metadata_json = row["metadata_json"]
    metadata: Any = None
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except ValueError:
            metadata = None
    return {
        "item_id": row["item_id"],
        "root_id": row["root_id"],
        "relative_path": row["relative_path"],
        "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
        "audio_hash": row["audio_hash"],
        "hash_state": row["hash_state"],
        "revision": row["revision"],
        "metadata": metadata,
        "duration_us": row["duration_us"],
        "updated_at_utc": row["updated_at_utc"],
    }


def get_present_item(conn: sqlite3.Connection, user_id: str, item_id: str) -> sqlite3.Row:
    """Return the row of the user's present item (`ITEM_COLUMNS` plus `user_id`, `mtime_ns`).

    Raises `ApiError("not_found")` when the item does not exist, belongs to another user or
    is trashed: the three cases look the same to a client.
    """
    row = conn.execute(
        f"SELECT {ITEM_COLUMNS}, user_id, mtime_ns FROM items"
        " WHERE item_id = ? AND user_id = ? AND state = 'present'",
        (item_id, user_id),
    ).fetchone()
    if row is None:
        raise ApiError("not_found", "Unknown item.")
    return row


def present_path_taken(conn: sqlite3.Connection, root_id: str, relative_path: str) -> bool:
    """True when a present item of the root already has exactly this path."""
    row = conn.execute(
        "SELECT 1 FROM items WHERE root_id = ? AND relative_path = ? AND state = 'present'",
        (root_id, relative_path),
    ).fetchone()
    return row is not None


def item_public_by_id(conn: sqlite3.Connection, item_id: str) -> dict[str, Any]:
    """Return `item_public` of the item with this id (any state); `not_found` if it is gone."""
    row = conn.execute(f"SELECT {ITEM_COLUMNS} FROM items WHERE item_id = ?", (item_id,)).fetchone()
    if row is None:
        raise ApiError("not_found", "Unknown item.")
    return item_public(row)


def purge_item(tx: Transaction, item_id: str) -> None:
    """Delete the row of a trashed item whose last file was permanently removed.

    The `item_revisions` rows go with it (cascade). Journal entry `purged`
    `{relative_path, reason: "purged"}` keeps `item_id` so clients can drop their link.
    """
    row = _item_row(tx, item_id)
    tx.conn.execute("DELETE FROM items WHERE item_id = ?", (item_id,))
    journal.append(
        tx,
        row["user_id"],
        "purged",
        item_id,
        {"relative_path": row["relative_path"], "reason": "purged"},
    )
