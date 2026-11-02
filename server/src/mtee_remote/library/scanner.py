"""Scan a root folder against the database, and hash the files that are still pending.

The scan only reads the music folder (it lists it and calls `stat`); it never creates,
modifies or deletes anything there. Hashing is a separate step (`hash_pending`) so a first
scan of a large library is fast and the slow part is resumable.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import stat as stat_module
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Literal

from mtee_remote import paths
from mtee_remote.config import Settings
from mtee_remote.db import Database, Transaction
from mtee_remote.errors import ApiError
from mtee_remote.library import hashing, store

log = logging.getLogger(__name__)

BATCH_SIZE = 200
_HASH_BATCH = 50
_MAX_SQLITE_INT = 2**63 - 1


@dataclass
class ScanResult:
    """What one scan changed. `moved` counts hand renames; `unchanged` counts untouched files."""

    added: int = 0
    changed: int = 0
    moved: int = 0
    removed: int = 0
    unchanged: int = 0


@dataclass(frozen=True)
class _DiskFile:
    size: int
    mtime_ns: int
    inode: int | None


@dataclass(frozen=True)
class _DbItem:
    item_id: str
    size: int
    mtime_ns: int
    inode: int | None


@dataclass
class _Plan:
    removes: list[str] = field(default_factory=lambda: list[str]())
    # (item_id, new relative path, file, whether the content may have changed too)
    moves: list[tuple[str, str, _DiskFile, bool]] = field(
        default_factory=lambda: list[tuple[str, str, _DiskFile, bool]]()
    )
    replaces: list[tuple[str, _DiskFile]] = field(
        default_factory=lambda: list[tuple[str, _DiskFile]]()
    )
    inserts: list[tuple[str, _DiskFile]] = field(
        default_factory=lambda: list[tuple[str, _DiskFile]]()
    )
    unchanged: int = 0


def _inode(value: int) -> int | None:
    return value if 0 < value <= _MAX_SQLITE_INT else None


def _walk(base: str, stop: threading.Event | None) -> dict[str, _DiskFile]:
    """List the audio files under `base` as `{posix relative path: file facts}`.

    Paths keep the spelling found on disk. A name in NFD (common from macOS) stays NFD,
    because on Linux the NFC spelling would not find the file.

    Skips names that start with a dot, symlinked folders and files that are not regular, and
    names that are not safe relative paths (control characters, a backslash...).
    """
    found: dict[str, _DiskFile] = {}
    pending: list[tuple[str, str]] = [(base, "")]
    while pending:
        if stop is not None and stop.is_set():
            break
        directory, prefix = pending.pop()
        try:
            iterator = os.scandir(directory)
        except OSError:
            log.warning("A folder could not be listed; its files are skipped.", exc_info=True)
            continue
        with iterator:
            for entry in iterator:
                name = entry.name
                if name.startswith("."):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append((entry.path, f"{prefix}{name}/"))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    suffix = PurePosixPath(name).suffix.lower()
                    if suffix not in store.AUDIO_EXTENSIONS:
                        continue
                    # DirEntry.stat() has no inode on Windows, so ask the file system.
                    info = os.stat(entry.path)
                except OSError:
                    continue  # vanished while listing; the next scan sees the truth
                if not stat_module.S_ISREG(info.st_mode):
                    continue
                relative = f"{prefix}{name}"
                try:
                    paths.normalize_relative_path(relative)
                except ApiError:
                    log.warning("A file name is not a safe path; the file is skipped.")
                    continue
                found[relative] = _DiskFile(info.st_size, info.st_mtime_ns, _inode(info.st_ino))
    return found


def _db_items(conn: sqlite3.Connection, root_id: str) -> dict[str, _DbItem]:
    rows = conn.execute(
        "SELECT item_id, relative_path, size_bytes, mtime_ns, inode FROM items"
        " WHERE root_id = ? AND state = 'present'",
        (root_id,),
    )
    return {
        row["relative_path"]: _DbItem(
            row["item_id"], row["size_bytes"], row["mtime_ns"], row["inode"]
        )
        for row in rows
    }


def _plan(disk: dict[str, _DiskFile], known: dict[str, _DbItem]) -> _Plan:
    plan = _Plan()
    new_paths: list[str] = []
    for relative, file in disk.items():
        item = known.get(relative)
        if item is None:
            new_paths.append(relative)
        elif item.size == file.size and item.mtime_ns == file.mtime_ns:
            plan.unchanged += 1
        else:
            plan.replaces.append((item.item_id, file))
    # A missing item and a new file with the same non-zero inode and size are one file that
    # was renamed or moved by hand: keep the item id.
    missing = {rel: item for rel, item in known.items() if rel not in disk}
    by_identity: dict[tuple[int, int], list[str]] = {}
    for rel, item in missing.items():
        if item.inode:
            by_identity.setdefault((item.inode, item.size), []).append(rel)
    for relative in new_paths:
        file = disk[relative]
        candidates = by_identity.get((file.inode, file.size)) if file.inode else None
        if candidates:
            old = missing.pop(candidates.pop(0))
            plan.moves.append((old.item_id, relative, file, old.mtime_ns != file.mtime_ns))
        else:
            plan.inserts.append((relative, file))
    plan.removes = [item.item_id for item in missing.values()]
    return plan


def _move(item_id: str, relative: str, changed: _DiskFile | None, tx: Transaction) -> None:
    """Rename the item; if the content may differ too (other mtime), record a new revision."""
    store.move_item(tx, item_id, relative)
    if changed is not None:
        store.replace_item_file(
            tx,
            item_id,
            size_bytes=changed.size,
            mtime_ns=changed.mtime_ns,
            inode=changed.inode,
        )


def _apply(
    db: Database,
    plan: _Plan,
    user_id: str,
    root_id: str,
    result: ScanResult,
    stop: threading.Event | None,
) -> None:
    """Apply the plan in transactions of `BATCH_SIZE` operations.

    Each operation runs inside a savepoint: one that fails (a concurrent writer took the
    path, the item vanished) is logged and skipped without losing the rest of the batch.
    """
    operations: list[
        tuple[Literal["added", "changed", "moved", "removed"], Callable[[Transaction], object]]
    ] = []
    for item_id in plan.removes:
        operations.append(("removed", partial(store.remove_missing, item_id=item_id)))
    for item_id, relative, file, changed in plan.moves:
        operations.append(("moved", partial(_move, item_id, relative, file if changed else None)))
    for item_id, file in plan.replaces:
        operations.append(
            (
                "changed",
                partial(
                    store.replace_item_file,
                    item_id=item_id,
                    size_bytes=file.size,
                    mtime_ns=file.mtime_ns,
                    inode=file.inode,
                ),
            )
        )
    for relative, file in plan.inserts:
        operations.append(
            (
                "added",
                partial(
                    store.insert_item,
                    user_id=user_id,
                    root_id=root_id,
                    relative_path=relative,
                    size_bytes=file.size,
                    mtime_ns=file.mtime_ns,
                    inode=file.inode,
                ),
            )
        )

    for start in range(0, len(operations), BATCH_SIZE):
        if stop is not None and stop.is_set():
            return
        with db.transaction() as tx:
            for counter, operation in operations[start : start + BATCH_SIZE]:
                tx.conn.execute("SAVEPOINT scan_op")
                try:
                    operation(tx)
                except (sqlite3.IntegrityError, ApiError):
                    tx.conn.execute("ROLLBACK TO scan_op")
                    tx.conn.execute("RELEASE scan_op")
                    log.warning("A change was skipped because a concurrent writer got there first.")
                    continue
                tx.conn.execute("RELEASE scan_op")
                setattr(result, counter, getattr(result, counter) + 1)


def scan_root(
    db: Database, settings: Settings, root_id: str, *, stop: threading.Event | None = None
) -> ScanResult:
    """Compare the root's folder with its `present` items and record the differences.

    Holds `store.root_lock(root_id)` throughout. New files become `pending` items, files whose
    size or mtime changed get a new revision (`pending` again), files that vanished are
    removed, and a vanished file plus a new one with the same inode and size is a hand rename
    (`move_item`, same item id). Nothing is hashed here (see `hash_pending`).

    Raises `ApiError("not_found")` for an unknown root and `FileNotFoundError` when the
    root's folder is missing: an unmounted volume must not empty the library in the database.
    """
    with store.root_lock(root_id):
        conn = db.conn()
        row = conn.execute("SELECT user_id FROM roots WHERE root_id = ?", (root_id,)).fetchone()
        if row is None:
            raise ApiError("not_found", "Unknown root.")
        base = store.root_path(settings, conn, root_id)
        if not base.is_dir():
            raise FileNotFoundError("The root folder does not exist or is not a folder.")
        disk = _walk(str(base), stop)
        if stop is not None and stop.is_set():
            return ScanResult()
        plan = _plan(disk, _db_items(conn, root_id))
        result = ScanResult(unchanged=plan.unchanged)
        _apply(db, plan, row["user_id"], root_id, result, stop)
        return result


def hash_pending(
    db: Database,
    settings: Settings,
    *,
    limit: int | None = None,
    stop: threading.Event | None = None,
) -> int:
    """Hash present items whose `hash_state` is `pending`, oldest first; return how many.

    For each item the file SHA-256, the audio hash and the tags are computed outside any
    transaction, then stored with `set_hashes` (refused if the revision moved meanwhile, in
    which case the item is `pending` again and gets picked up later). A missing file or an
    unreadable one gives `hash_state = 'error'`; a failed audio hash alone does not (it stays
    NULL). Progress lives in the database, so it resumes after a restart.
    """
    processed = 0
    root_dirs: dict[str, Path] = {}
    while limit is None or processed < limit:
        if stop is not None and stop.is_set():
            break
        want = _HASH_BATCH if limit is None else min(_HASH_BATCH, limit - processed)
        ids = [
            row["item_id"]
            for row in db.conn().execute(
                "SELECT item_id FROM items WHERE state = 'present' AND hash_state = 'pending'"
                " ORDER BY updated_at_utc, rowid LIMIT ?",
                (want,),
            )
        ]
        if not ids:
            break
        progressed = False
        for item_id in ids:
            if stop is not None and stop.is_set():
                return processed
            if _hash_one(db, settings, item_id, root_dirs):
                processed += 1
                progressed = True
        if not progressed:
            break
    return processed


def _hash_one(db: Database, settings: Settings, item_id: str, root_dirs: dict[str, Path]) -> bool:
    """Hash one item; return False when it was skipped (changed state or moved meanwhile)."""
    conn = db.conn()
    row = conn.execute(
        "SELECT root_id, relative_path, revision FROM items"
        " WHERE item_id = ? AND state = 'present' AND hash_state = 'pending'",
        (item_id,),
    ).fetchone()
    if row is None:
        return False
    root_id, relative, revision = row["root_id"], row["relative_path"], row["revision"]
    base = root_dirs.get(root_id)
    if base is None:
        try:
            base = store.root_path(settings, conn, root_id)
        except ApiError:
            return False
        root_dirs[root_id] = base
    sha256: str | None = None
    audio: str | None = None
    metadata_json: str | None = None
    duration_us: int | None = None
    path: Path | None = None
    try:
        path = paths.disk_path(base, relative)
        sha256 = hashing.file_sha256(path)
    except (OSError, ApiError):
        sha256 = None
    if sha256 is not None and path is not None:
        audio = hashing.audio_hash(path)
        metadata_json, duration_us = hashing.read_metadata(path)
    else:
        current = conn.execute(
            "SELECT relative_path, revision FROM items WHERE item_id = ?", (item_id,)
        ).fetchone()
        if current is None or (current["relative_path"], current["revision"]) != (
            relative,
            revision,
        ):
            return False  # moved or replaced while we tried: leave it pending
    with db.transaction() as tx:
        store.set_hashes(
            tx,
            item_id,
            revision,
            sha256=sha256,
            audio_hash=audio,
            metadata_json=metadata_json,
            duration_us=duration_us,
            ok=sha256 is not None,
        )
    return True
