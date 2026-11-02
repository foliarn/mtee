"""Moving files inside a root, and the server trash (milestone 124.5).

Same rules as `uploads.py` (read its docstring): files are placed with `place_file`, under
`store.root_lock`, before the database step, and a failed database step is undone.

Item trash lives in `<library>/.mtee-trash/<trash_id>/<original file name>`;
`trash.stored_path` is that path relative to the user's library folder.

A trash entry is either the *current* file of a trashed item, or an *older version* that a
replacement kept. The current entry of a trashed item is the newest entry that names it (a
trashed item cannot be replaced, so every replacement entry is older). Restoring it brings
the item itself back; restoring any other entry creates a new item.

A backup (milestone 124.7) has entries of kind `backup`: the file moves to
`<data>/trash/backups/<backup_id>.db`, and `trash.stored_path` is `backups/<backup_id>.db`,
relative to `<data>/trash/`. Restoring it moves the file back to `backups.stored_path`.
Backup moves are serialised by `BACKUP_LOCK`.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path, PurePosixPath
from typing import Any

from mtee_remote import journal
from mtee_remote.config import Settings
from mtee_remote.db import Database
from mtee_remote.errors import ApiError
from mtee_remote.ids import new_id
from mtee_remote.library import store
from mtee_remote.paths import resolve_under
from mtee_remote.uploads import (
    check_item_path,
    disk_path,
    file_facts,
    insert_trash_row,
    library_folder,
    make_parents,
    now_iso,
    path_in_use,
    place_file,
    remove_empty_dir,
    trash_stored_path,
    undo_place,
)

log = logging.getLogger(__name__)

# Held by every operation that moves a backup file (trash, restore, purge) and by the
# retention pass in backups.py. Re-entrant, because retention trashes backups itself.
BACKUP_LOCK = threading.RLock()
BACKUP_TRASH_DIRNAME = "backups"

_TAKEN = "A file already exists at that path."


def move_item(
    db: Database, settings: Settings, *, user_id: str, item_id: str, new_relative_path: str
) -> dict[str, Any]:
    """Move an item's file to another path in the same root and return `item_public`."""
    conn = db.conn()
    item = store.get_present_item(conn, user_id, item_id)
    root_id: str = item["root_id"]
    old: str = item["relative_path"]
    new = check_item_path(new_relative_path)
    root_dir = store.root_path(settings, conn, root_id)
    target = resolve_under(root_dir, new)
    with store.root_lock(root_id):
        # Read again under the lock: a scan may have moved or replaced the item meanwhile.
        item = store.get_present_item(conn, user_id, item_id)
        old = item["relative_path"]
        if new == old:
            return store.item_public(item)
        source = disk_path(root_dir, old)
        if not source.is_file():
            raise ApiError("conflict", "The file is missing on the server; scan the root first.")
        if path_in_use(conn, root_id, new, target):
            raise ApiError("path_taken", _TAKEN)
        make_parents(target)
        place_file(source, target)
        try:
            with db.transaction() as tx:
                store.move_item(tx, item_id, new)
        except BaseException:
            log.exception(
                "Moving item %s: the database step failed; undoing the file move.", item_id
            )
            undo_place(target, source)
            raise
    return store.item_public_by_id(conn, item_id)


def trash_item(
    db: Database, settings: Settings, *, user_id: str, device_id: str, item_id: str
) -> str:
    """Move an item's file to the server trash and mark the item trashed; return the trash id."""
    conn = db.conn()
    item = store.get_present_item(conn, user_id, item_id)
    root_id: str = item["root_id"]
    root_dir = store.root_path(settings, conn, root_id)
    library = library_folder(conn, settings, user_id)
    with store.root_lock(root_id):
        item = store.get_present_item(conn, user_id, item_id)
        relative: str = item["relative_path"]
        source = disk_path(root_dir, relative)
        if not source.is_file():
            raise ApiError("conflict", "The file is missing on the server; scan the root first.")
        trash_id = new_id()
        stored = trash_stored_path(trash_id, PurePosixPath(relative).name)
        trash_file = library / stored
        trash_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            place_file(source, trash_file)
        except BaseException:
            remove_empty_dir(trash_file.parent)
            raise
        try:
            with db.transaction() as tx:
                insert_trash_row(
                    tx,
                    trash_id=trash_id,
                    user_id=user_id,
                    item_id=item_id,
                    stored_path=stored,
                    root_id=root_id,
                    relative_path=relative,
                    size_bytes=int(item["size_bytes"]),
                    device_id=device_id,
                )
                store.mark_trashed(tx, item_id)
        except BaseException:
            log.exception("Trashing item %s: the database step failed; undoing.", item_id)
            undo_place(trash_file, source)
            remove_empty_dir(trash_file.parent)
            raise
    return trash_id


def trash_root(settings: Settings) -> Path:
    """The folder that holds trashed backups: `<data>/trash`."""
    return settings.data_dir / "trash"


def list_entries(conn: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    """The user's trash entries, newest first.

    An item entry has the fields it always had. A backup entry (kind `backup`) has `backup_id`
    and null item fields.
    """
    rows = conn.execute(
        "SELECT trash_id, kind, item_id, backup_id, original_root_id, original_relative_path,"
        " size_bytes, trashed_at_utc FROM trash WHERE user_id = ?"
        " ORDER BY trashed_at_utc DESC, rowid DESC",
        (user_id,),
    )
    entries: list[dict[str, Any]] = []
    for row in rows:
        entry: dict[str, Any] = {
            "trash_id": row["trash_id"],
            "kind": row["kind"],
            "item_id": row["item_id"],
            "original_root_id": row["original_root_id"],
            "original_relative_path": row["original_relative_path"],
            "size_bytes": row["size_bytes"],
            "trashed_at_utc": row["trashed_at_utc"],
        }
        if row["kind"] == "backup":
            entry["backup_id"] = row["backup_id"]
        entries.append(entry)
    return entries


def _row(conn: sqlite3.Connection, user_id: str, trash_id: str) -> sqlite3.Row:
    """The user's trash entry of any kind, or `not_found`."""
    row = conn.execute(
        "SELECT * FROM trash WHERE trash_id = ? AND user_id = ?", (trash_id, user_id)
    ).fetchone()
    if row is None:
        raise ApiError("not_found", "Unknown trash entry.")
    return row


def entry_kind(conn: sqlite3.Connection, user_id: str, trash_id: str) -> str:
    """The kind (`item` or `backup`) of the user's trash entry, or `not_found`."""
    kind: str = _row(conn, user_id, trash_id)["kind"]
    return kind


def _entry(conn: sqlite3.Connection, user_id: str, trash_id: str) -> sqlite3.Row:
    row = _row(conn, user_id, trash_id)
    if row["kind"] != "item":
        raise ApiError("bad_request", "Only entries of kind 'item' are handled here.")
    return row


def _is_current_entry(conn: sqlite3.Connection, entry: sqlite3.Row) -> bool:
    """True when `entry` is the file of a *trashed* item (see the module docstring)."""
    item_id = entry["item_id"]
    if item_id is None:
        return False
    item = conn.execute("SELECT state FROM items WHERE item_id = ?", (item_id,)).fetchone()
    if item is None or item["state"] != "trashed":
        return False
    newest = conn.execute(
        "SELECT trash_id FROM trash WHERE item_id = ? AND kind = 'item'"
        " ORDER BY rowid DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    return newest is not None and newest["trash_id"] == entry["trash_id"]


def restore(
    db: Database,
    settings: Settings,
    *,
    user_id: str,
    device_id: str,
    trash_id: str,
    relative_path: str | None,
) -> dict[str, Any]:
    """Put a trashed file back (at its old path or at `relative_path`) and return the item.

    The root is always the original one. The current file of a trashed item brings the item
    back (`restored`); an older version kept by a replacement becomes a new item (`added`,
    hash pending). Never overwrites: `409 path_taken` when the path is in use.
    """
    conn = db.conn()
    entry = _entry(conn, user_id, trash_id)
    root_id = entry["original_root_id"]
    owned = conn.execute(
        "SELECT 1 FROM roots WHERE root_id = ? AND user_id = ?", (root_id, user_id)
    ).fetchone()
    if root_id is None or owned is None or entry["original_relative_path"] is None:
        raise ApiError("conflict", "The original root of this file no longer exists.")
    root_dir = store.root_path(settings, conn, root_id)
    library = library_folder(conn, settings, user_id)
    source = disk_path(library, entry["stored_path"])
    if relative_path is not None:
        relative = check_item_path(relative_path)
        target = resolve_under(root_dir, relative)
    else:
        relative = entry["original_relative_path"]
        target = disk_path(root_dir, relative)
    with store.root_lock(root_id):
        if path_in_use(conn, root_id, relative, target):
            raise ApiError("path_taken", _TAKEN)
        if not source.is_file():
            raise ApiError("not_found", "The trashed file is missing on the server.")
        make_parents(target)
        place_file(source, target)
        try:
            with db.transaction() as tx:
                if _is_current_entry(tx.conn, entry):
                    item_id = entry["item_id"]
                    store.mark_restored(tx, item_id, relative)
                else:
                    size, mtime_ns, inode = file_facts(target)
                    item_id = store.insert_item(
                        tx,
                        user_id=user_id,
                        root_id=root_id,
                        relative_path=relative,
                        size_bytes=size,
                        mtime_ns=mtime_ns,
                        inode=inode,
                        device_id=device_id,
                    )
                tx.conn.execute("DELETE FROM trash WHERE trash_id = ?", (trash_id,))
        except BaseException:
            log.exception("Restoring trash entry %s: the database step failed; undoing.", trash_id)
            undo_place(target, source)
            raise
    remove_empty_dir(source.parent)
    return store.item_public_by_id(conn, item_id)


def purge(db: Database, settings: Settings, *, user_id: str, trash_id: str) -> None:
    """Permanently delete one trash entry: the only permanent delete the server has.

    The database goes first (one transaction: the trash row, and for the current file of a
    trashed item also the item row with a `purged` journal entry), then the file. If the
    file cannot be removed it stays in the trash folder, harmless and logged.
    """
    conn = db.conn()
    row = _row(conn, user_id, trash_id)
    if row["kind"] == "backup":
        _purge_backup(db, settings, row)
        return
    entry = _entry(conn, user_id, trash_id)
    path: Path = disk_path(library_folder(conn, settings, user_id), entry["stored_path"])
    with db.transaction() as tx:
        if _is_current_entry(tx.conn, entry):
            store.purge_item(tx, entry["item_id"])
        tx.conn.execute("DELETE FROM trash WHERE trash_id = ?", (trash_id,))
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.exception("Purged trash entry %s: its file could not be removed.", trash_id)
        return
    remove_empty_dir(path.parent)


# -- backups (milestone 124.7) -------------------------------------------------------


def trash_backup(
    db: Database,
    settings: Settings,
    *,
    user_id: str,
    backup_id: str,
    device_id: str | None,
) -> None:
    """Move a present backup's file to the trash and mark it trashed (journal `backup_trashed`).

    The file moves first, then the database changes in one transaction; a failed database
    step moves the file back. `not_found` when the backup is not present.
    """
    with BACKUP_LOCK:
        conn = db.conn()
        row = conn.execute(
            "SELECT stored_path, size_bytes FROM backups"
            " WHERE backup_id = ? AND user_id = ? AND state = 'present'",
            (backup_id, user_id),
        ).fetchone()
        if row is None:
            raise ApiError("not_found", "Unknown backup.")
        source = disk_path(settings.data_dir, row["stored_path"])
        if not source.is_file():
            raise ApiError("conflict", "The backup file is missing on the server.")
        trash_id = new_id()
        stored = f"{BACKUP_TRASH_DIRNAME}/{backup_id}.db"
        target = disk_path(trash_root(settings), stored)
        target.parent.mkdir(parents=True, exist_ok=True)
        place_file(source, target)
        try:
            with db.transaction() as tx:
                tx.conn.execute(
                    "INSERT INTO trash(trash_id, user_id, kind, item_id, backup_id, stored_path,"
                    " size_bytes, trashed_at_utc, trashed_by_device_id)"
                    " VALUES (?,?,'backup',NULL,?,?,?,?,?)",
                    (
                        trash_id,
                        user_id,
                        backup_id,
                        stored,
                        int(row["size_bytes"]),
                        now_iso(),
                        device_id,
                    ),
                )
                tx.conn.execute(
                    "UPDATE backups SET state = 'trashed' WHERE backup_id = ?", (backup_id,)
                )
                journal.append(tx, user_id, "backup_trashed", None, {"backup_id": backup_id})
        except BaseException:
            log.exception("Trashing backup %s: the database step failed; undoing.", backup_id)
            undo_place(target, source)
            raise


def restore_backup(db: Database, settings: Settings, *, user_id: str, trash_id: str) -> str:
    """Move a trashed backup back to its own place and return its `backup_id`.

    Restoring a backup writes no journal entry: the journal has no kind for it.
    """
    with BACKUP_LOCK:
        conn = db.conn()
        entry = _row(conn, user_id, trash_id)
        if entry["kind"] != "backup":
            raise ApiError("bad_request", "Only entries of kind 'backup' are handled here.")
        backup_id: str = entry["backup_id"]
        row = conn.execute(
            "SELECT stored_path FROM backups"
            " WHERE backup_id = ? AND user_id = ? AND state = 'trashed'",
            (backup_id, user_id),
        ).fetchone()
        if row is None:
            raise ApiError("not_found", "Unknown backup.")
        source = disk_path(trash_root(settings), entry["stored_path"])
        target = disk_path(settings.data_dir, row["stored_path"])
        if not source.is_file():
            raise ApiError("not_found", "The trashed backup is missing on the server.")
        target.parent.mkdir(parents=True, exist_ok=True)
        place_file(source, target)
        try:
            with db.transaction() as tx:
                tx.conn.execute(
                    "UPDATE backups SET state = 'present' WHERE backup_id = ?", (backup_id,)
                )
                tx.conn.execute("DELETE FROM trash WHERE trash_id = ?", (trash_id,))
        except BaseException:
            log.exception("Restoring backup %s: the database step failed; undoing.", backup_id)
            undo_place(target, source)
            raise
    return backup_id


def _purge_backup(db: Database, settings: Settings, entry: sqlite3.Row) -> None:
    """Delete a trashed backup for good: its trash row, its backup row, then its file.

    The database goes first. A file that cannot be removed stays in the trash folder, logged.
    """
    with BACKUP_LOCK:
        path = disk_path(trash_root(settings), entry["stored_path"])
        with db.transaction() as tx:
            tx.conn.execute("DELETE FROM backups WHERE backup_id = ?", (entry["backup_id"],))
            tx.conn.execute("DELETE FROM trash WHERE trash_id = ?", (entry["trash_id"],))
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.exception("Purged backup %s: its file could not be removed.", entry["backup_id"])
