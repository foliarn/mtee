"""Resumable uploads and the safe file operations behind them (milestone 124.5).

This is the code that writes into users' music folders, so the rules are strict:

- **Never overwrite a file.** Every placement goes through `place_file`, which links the
  source to the target (the link fails when the target exists) and then removes the source.
- **Everything stays on one disk.** Part files live inside the user's library folder, in
  `<library>/.mtee-tmp/uploads/<upload_id>.part`, and item trash in
  `<library>/.mtee-trash/<trash_id>/<original file name>`. In Docker each library folder is
  its own bind mount, so a rename between `/data` and `/music/<user>` would fail. Scans skip
  names that start with a dot, so neither folder is ever seen as library content (and
  `check_item_path` refuses client paths with such a segment).
- **`trash.stored_path` is relative to the user's library folder** (for rows of kind `item`),
  for example `.mtee-trash/<trash_id>/song.flac`. Backup entries (milestone 124.7) are
  relative to `<data>/trash/` instead.
- **File first, database second.** A file operation happens under `store.root_lock(root_id)`
  before the database transaction. If the transaction then fails, the operation is undone
  (replacement, move, trash, restore). The one exception is a *new* file: it is left in place
  and the failure is logged, because the next scan finds the file and adopts it.
- The in-memory locks (`exclusive`) only work inside one server process; the server runs as
  one process.
- Backup uploads (purpose `backup`, milestone 124.7) keep their part file in `<data>/uploads/`
  (`part_file` is the one place that chooses it). Their commit lives in `backups.py`, which
  reuses `verify_received`. The uploads table has no column for the kind of a backup, so
  `uploads.label` holds the JSON object `{"label": ..., "kind": ...}` (`encode_backup_meta`).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

from mtee_remote import clock
from mtee_remote.config import Settings
from mtee_remote.db import Database, Transaction
from mtee_remote.errors import ApiError
from mtee_remote.ids import new_id
from mtee_remote.library import hashing, store
from mtee_remote.paths import disk_path, normalize_relative_path, resolve_under

log = logging.getLogger(__name__)

TMP_DIRNAME = ".mtee-tmp"
UPLOADS_DIRNAME = "uploads"
TRASH_DIRNAME = ".mtee-trash"

# Upload purposes this server can commit: `item` (124.5) and `backup` (124.7). `check_purpose`
# is the one place that checks them.
PURPOSES = frozenset({"item", "backup"})
BACKUP_KINDS = frozenset({"manual", "automatic"})
BACKUP_LABEL_MAX = 200

SHA256_RE = re.compile(r"[0-9a-f]{64}")
_MAX_SQLITE_INT = 2**63 - 1


def check_purpose(purpose: str) -> None:
    """Refuse an upload purpose this server cannot commit yet (400 `bad_request`)."""
    if purpose not in PURPOSES:
        raise ApiError("bad_request", f"Unsupported upload purpose: {purpose!r}.")


# -- small helpers -------------------------------------------------------------------

_busy: set[str] = set()


@contextmanager
def exclusive(key: str) -> Iterator[None]:
    """Hold an in-memory lock on `key`; a second holder gets `409 conflict` at once.

    Call it only from the event loop thread (the check and the add are not interrupted by
    another coroutine because there is no `await` between them).
    """
    if key in _busy:
        raise ApiError("conflict", "Another request is already working on this.")
    _busy.add(key)
    try:
        yield
    finally:
        _busy.discard(key)


def now_iso() -> str:
    return clock.to_iso(clock.utc_now())


def check_item_path(raw: str) -> str:
    """Normalise a client path for a library file, or raise `bad_request`.

    On top of `normalize_relative_path`: no segment may start with a dot (scans skip such
    names, and `.mtee-tmp` / `.mtee-trash` must stay out of reach) and the extension must be
    one of MTEE's audio extensions (a scan would drop any other file from the library).
    """
    path = normalize_relative_path(raw)
    if any(segment.startswith(".") for segment in path.split("/")):
        raise ApiError("bad_request", "Invalid path: a name must not start with a dot.")
    if PurePosixPath(path).suffix.lower() not in store.AUDIO_EXTENSIONS:
        raise ApiError("bad_request", "Invalid path: the file is not a supported audio file.")
    return path


def file_facts(path: Path) -> tuple[int, int, int | None]:
    """Return `(size_bytes, mtime_ns, inode)` of a file, as the items table stores them."""
    info = os.stat(path)
    inode = info.st_ino if 0 < info.st_ino <= _MAX_SQLITE_INT else None
    return info.st_size, info.st_mtime_ns, inode


def make_parents(target: Path) -> None:
    """Create the folders above `target`; a file in the way means the path is taken."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError):
        raise ApiError("path_taken", "A file is in the way of that folder path.") from None


def path_in_use(conn: sqlite3.Connection, root_id: str, relative_path: str, target: Path) -> bool:
    """True when a present item or any file/folder on disk already has this path."""
    return store.present_path_taken(conn, root_id, relative_path) or os.path.lexists(target)


def place_file(src: Path, dst: Path) -> None:
    """Move `src` to `dst` without ever overwriting: the one way every module places a file.

    The caller holds `store.root_lock` of the root it writes into. `os.link(src, dst)` fails
    when `dst` exists (`409 path_taken`), which is the no-overwrite guarantee; `src` is then
    removed. If the file system has no hard links (any other `OSError`), `os.rename` is used
    after checking that `dst` does not exist. That check is not atomic against another
    process writing the same path at the same instant (for example a hand copy); the root
    lock only protects against this server's own writers and the scanner.
    If removing `src` fails, the new link is removed again and the error is raised, so the
    file never exists twice because of a failed move.
    """
    try:
        os.link(src, dst)
    except FileExistsError:
        raise ApiError("path_taken", "A file already exists at that path.") from None
    except FileNotFoundError:
        raise
    except OSError:
        if os.path.lexists(dst):
            raise ApiError("path_taken", "A file already exists at that path.") from None
        try:
            os.rename(src, dst)
        except FileExistsError:
            raise ApiError("path_taken", "A file already exists at that path.") from None
        return
    try:
        os.unlink(src)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(dst)
        raise


def library_folder(conn: sqlite3.Connection, settings: Settings, user_id: str) -> Path:
    row = conn.execute("SELECT library_dir FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise ApiError("not_found", "Unknown user.")
    return store.user_library_dir(settings, row["library_dir"])


def part_path(library: Path, upload_id: str) -> Path:
    return library / TMP_DIRNAME / UPLOADS_DIRNAME / f"{upload_id}.part"


def part_file(
    settings: Settings, conn: sqlite3.Connection, user_id: str, purpose: str, upload_id: str
) -> Path:
    """Where the part file of an upload lives: the one place that chooses the location.

    An item's part file is in its user's library folder (the disk of the item). A backup's is
    in `<data>/uploads/`, on the same volume as the stored backups.
    """
    if purpose == "backup":
        return settings.data_dir / UPLOADS_DIRNAME / f"{upload_id}.part"
    return part_path(library_folder(conn, settings, user_id), upload_id)


def part_size(part: Path) -> int:
    """The real size of the part file (0 when it does not exist)."""
    try:
        return part.stat().st_size
    except FileNotFoundError:
        return 0


# -- server trash entries (shared with trash.py) -------------------------------------


def trash_stored_path(trash_id: str, file_name: str) -> str:
    """The `trash.stored_path` of an item entry: relative to the user's library folder."""
    return f"{TRASH_DIRNAME}/{trash_id}/{file_name}"


def insert_trash_row(
    tx: Transaction,
    *,
    trash_id: str,
    user_id: str,
    item_id: str,
    stored_path: str,
    root_id: str,
    relative_path: str,
    size_bytes: int,
    device_id: str | None,
) -> None:
    tx.conn.execute(
        "INSERT INTO trash(trash_id, user_id, kind, item_id, stored_path, original_root_id,"
        " original_relative_path, size_bytes, trashed_at_utc, trashed_by_device_id)"
        " VALUES (?,?,'item',?,?,?,?,?,?,?)",
        (
            trash_id,
            user_id,
            item_id,
            stored_path,
            root_id,
            relative_path,
            size_bytes,
            now_iso(),
            device_id,
        ),
    )


def remove_empty_dir(path: Path) -> None:
    """Remove a folder if it is empty; anything else is left alone."""
    with contextlib.suppress(OSError):
        path.rmdir()


# -- quota -----------------------------------------------------------------------------


def used_bytes(conn: sqlite3.Connection, user_id: str) -> int:
    """Bytes the user occupies: present items and backups, trash entries (items and backups)
    and unfinished uploads.

    Unfinished means state `open` or `conflict` (a conflicting upload keeps its part file).
    """
    total = 0
    for sql in (
        "SELECT COALESCE(SUM(size_bytes), 0) FROM items WHERE user_id = ? AND state = 'present'",
        "SELECT COALESCE(SUM(size_bytes), 0) FROM trash WHERE user_id = ?",
        "SELECT COALESCE(SUM(size_bytes), 0) FROM backups WHERE user_id = ? AND state = 'present'",
        "SELECT COALESCE(SUM(size_bytes), 0) FROM uploads"
        " WHERE user_id = ? AND state IN ('open', 'conflict')",
    ):
        total += int(conn.execute(sql, (user_id,)).fetchone()[0])
    return total


# -- uploads ---------------------------------------------------------------------------


def load_upload(conn: sqlite3.Connection, user_id: str, upload_id: str) -> sqlite3.Row:
    """Return the user's upload row, or raise `not_found` (also for another user's upload)."""
    row = conn.execute(
        "SELECT * FROM uploads WHERE upload_id = ? AND user_id = ?", (upload_id, user_id)
    ).fetchone()
    if row is None or row["purpose"] not in PURPOSES:
        raise ApiError("not_found", "Unknown upload.")
    return row


def create_upload(
    db: Database,
    settings: Settings,
    *,
    user_id: str,
    device_id: str,
    purpose: str,
    root_id: str,
    relative_path: str,
    size_bytes: int,
    sha256: str,
    base_item_id: str | None,
    base_revision: int | None,
) -> dict[str, Any]:
    """Check an item upload request, create its empty part file and row; return the response.

    Backups have their own entry point, `create_backup_upload`.
    """
    check_purpose(purpose)
    if purpose != "item":
        raise ApiError("bad_request", "This upload purpose takes no root or path.")
    check_sha256(sha256)
    if (base_item_id is None) != (base_revision is None):
        raise ApiError(
            "bad_request", "base_item_id and base_revision must be given together or not at all."
        )
    conn = db.conn()
    root = conn.execute(
        "SELECT 1 FROM roots WHERE root_id = ? AND user_id = ?", (root_id, user_id)
    ).fetchone()
    if root is None:
        raise ApiError("not_found", "Unknown root.")
    clean = check_item_path(relative_path)
    replaced_size = 0
    if base_item_id is not None:
        item = conn.execute(
            "SELECT root_id, relative_path, size_bytes FROM items"
            " WHERE item_id = ? AND user_id = ? AND state = 'present'",
            (base_item_id, user_id),
        ).fetchone()
        if item is None:
            raise ApiError("not_found", "Unknown item.")
        if item["root_id"] != root_id:
            raise ApiError("bad_request", "The item is not in that root.")
        # A replacement is placed at the item's own path, wherever the client thinks it is.
        clean = item["relative_path"]
        replaced_size = int(item["size_bytes"])
    else:
        target = resolve_under(store.root_path(settings, conn, root_id), clean)
        if path_in_use(conn, root_id, clean, target):
            raise ApiError("path_taken", "A file already exists at that path.")
    return _open_upload(
        db,
        settings,
        user_id=user_id,
        device_id=device_id,
        purpose="item",
        root_id=root_id,
        relative_path=clean,
        size_bytes=size_bytes,
        sha256=sha256,
        base_item_id=base_item_id,
        base_revision=base_revision,
        label=None,
        replaced_size=replaced_size,
    )


def create_backup_upload(
    db: Database,
    settings: Settings,
    *,
    user_id: str,
    device_id: str,
    size_bytes: int,
    sha256: str,
    label: str | None,
    kind: str,
) -> dict[str, Any]:
    """Check a backup upload request (purpose `backup`), open it; return the response.

    `kind` is `manual` or `automatic`; `label` is at most `BACKUP_LABEL_MAX` characters.
    """
    check_sha256(sha256)
    if kind not in BACKUP_KINDS:
        raise ApiError("bad_request", "The kind must be 'manual' or 'automatic'.")
    if label is not None and len(label) > BACKUP_LABEL_MAX:
        raise ApiError("bad_request", f"The label is longer than {BACKUP_LABEL_MAX} characters.")
    return _open_upload(
        db,
        settings,
        user_id=user_id,
        device_id=device_id,
        purpose="backup",
        root_id=None,
        relative_path=None,
        size_bytes=size_bytes,
        sha256=sha256,
        base_item_id=None,
        base_revision=None,
        label=encode_backup_meta(label, kind),
        replaced_size=0,
    )


def _open_upload(
    db: Database,
    settings: Settings,
    *,
    user_id: str,
    device_id: str,
    purpose: str,
    root_id: str | None,
    relative_path: str | None,
    size_bytes: int,
    sha256: str,
    base_item_id: str | None,
    base_revision: int | None,
    label: str | None,
    replaced_size: int,
) -> dict[str, Any]:
    """Check the quota, create the empty part file and the upload row; return the response."""
    conn = db.conn()
    quota = conn.execute("SELECT quota_bytes FROM users WHERE user_id = ?", (user_id,)).fetchone()[
        0
    ]
    if quota is not None and used_bytes(conn, user_id) + size_bytes - replaced_size > quota:
        raise ApiError("quota_exceeded", "This upload would exceed the storage quota.")
    upload_id = new_id()
    part = part_file(settings, conn, user_id, purpose, upload_id)
    part.parent.mkdir(parents=True, exist_ok=True)
    with open(part, "xb"):
        pass
    try:
        with db.transaction() as tx:
            stamp = now_iso()
            tx.conn.execute(
                "INSERT INTO uploads(upload_id, user_id, device_id, purpose, root_id,"
                " relative_path, base_item_id, base_revision, label, size_bytes, sha256,"
                " received_bytes, state, created_at_utc, updated_at_utc)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,0,'open',?,?)",
                (
                    upload_id,
                    user_id,
                    device_id,
                    purpose,
                    root_id,
                    relative_path,
                    base_item_id,
                    base_revision,
                    label,
                    size_bytes,
                    sha256,
                    stamp,
                    stamp,
                ),
            )
    except BaseException:
        with contextlib.suppress(OSError):
            part.unlink()
        raise
    return {"upload_id": upload_id, "received_bytes": 0, "size_bytes": size_bytes}


def check_sha256(sha256: str) -> None:
    if SHA256_RE.fullmatch(sha256) is None:
        raise ApiError("bad_request", "The sha256 must be 64 lowercase hexadecimal characters.")


def encode_backup_meta(label: str | None, kind: str) -> str:
    """The `uploads.label` of a backup upload: a JSON object `{"label": ..., "kind": ...}`."""
    return json.dumps({"label": label, "kind": kind}, ensure_ascii=False, separators=(",", ":"))


def decode_backup_meta(raw: str | None) -> tuple[str | None, str]:
    """Return `(label, kind)` read back from the `uploads.label` of a backup upload."""
    data: dict[str, Any] = json.loads(raw or "{}")
    label = data.get("label")
    kind = data.get("kind")
    return (label if isinstance(label, str) else None), (
        "automatic" if kind == "automatic" else "manual"
    )


def upload_status(db: Database, settings: Settings, user_id: str, upload_id: str) -> dict[str, Any]:
    """The state of an upload; `received_bytes` is the real size of the part file.

    Once the upload is `done` the part file is gone and `received_bytes` is `size_bytes`;
    a `cancelled` upload reports 0.
    """
    conn = db.conn()
    row = load_upload(conn, user_id, upload_id)
    if row["state"] == "done":
        received = int(row["size_bytes"])
    elif row["state"] == "cancelled":
        received = 0
    else:
        received = part_size(part_file(settings, conn, user_id, row["purpose"], upload_id))
    return {
        "upload_id": upload_id,
        "state": row["state"],
        "received_bytes": received,
        "size_bytes": row["size_bytes"],
    }


def record_progress(db: Database, upload_id: str, received: int) -> None:
    with db.transaction() as tx:
        tx.conn.execute(
            "UPDATE uploads SET received_bytes = ?, updated_at_utc = ? WHERE upload_id = ?",
            (received, now_iso(), upload_id),
        )


def _set_state(db: Database, upload_id: str, state: str) -> None:
    with db.transaction() as tx:
        tx.conn.execute(
            "UPDATE uploads SET state = ?, updated_at_utc = ? WHERE upload_id = ?",
            (state, now_iso(), upload_id),
        )


def cancel_upload(db: Database, settings: Settings, user_id: str, upload_id: str) -> None:
    conn = db.conn()
    row = load_upload(conn, user_id, upload_id)
    if row["state"] == "done":
        raise ApiError("conflict", "This upload is already committed.")
    part = part_file(settings, conn, user_id, row["purpose"], upload_id)
    _set_state(db, upload_id, "cancelled")
    with contextlib.suppress(FileNotFoundError):
        part.unlink()


# -- commit ----------------------------------------------------------------------------


def verify_received(
    db: Database, settings: Settings, *, user_id: str, upload_id: str
) -> tuple[sqlite3.Row, Path]:
    """Check that the part file is complete and has the promised SHA-256; return `(row, part)`.

    Shared by the item commit and the backup commit (`backups.commit_backup`). A wrong hash
    empties the part file, so the client sends the bytes again, and gives `422 bad_hash`.
    """
    conn = db.conn()
    row = load_upload(conn, user_id, upload_id)
    if row["state"] not in ("open", "conflict"):
        raise ApiError("conflict", "This upload is already finished.")
    part = part_file(settings, conn, user_id, row["purpose"], upload_id)
    size = part_size(part)
    if size != row["size_bytes"]:
        raise ApiError(
            "bad_request", f"{size} of {row['size_bytes']} bytes were received; send the rest."
        )
    if hashing.file_sha256(part) != row["sha256"]:
        with open(part, "r+b") as handle:
            handle.truncate(0)
        record_progress(db, upload_id, 0)
        raise ApiError("bad_hash", "The received bytes do not match the SHA-256. Send them again.")
    return row, part


def commit_upload(
    db: Database,
    settings: Settings,
    *,
    user_id: str,
    device_id: str,
    upload_id: str,
    new_relative_path: str | None,
) -> dict[str, Any]:
    """Verify the received item and put it in the library; return `item_public` of the item.

    Checks the size and the SHA-256 (see `verify_received`), then holds `store.root_lock` while
    it places the file (see the module docstring for the order of file and database work).
    Backup uploads are committed by `backups.commit_backup`.
    """
    row, part = verify_received(db, settings, user_id=user_id, upload_id=upload_id)
    if row["purpose"] != "item":
        raise ApiError("bad_request", "This upload is not an item upload.")
    if row["base_item_id"] is not None:
        if new_relative_path is not None:
            raise ApiError("bad_request", "A replacement keeps the path of its item.")
        item_id = _commit_replacement(db, settings, row, part, user_id, device_id)
    else:
        item_id = _commit_new(db, settings, row, part, user_id, device_id, new_relative_path)
    return store.item_public_by_id(db.conn(), item_id)


def _find_duplicate(
    conn: sqlite3.Connection, settings: Settings, sha256: str, size: int
) -> Path | None:
    """Return a file on disk that a present item (any user) says has this SHA-256.

    The database value is only trusted while the file still has the size and mtime that were
    recorded with it.
    """
    rows = conn.execute(
        "SELECT root_id, relative_path, size_bytes, mtime_ns FROM items"
        " WHERE sha256 = ? AND state = 'present' AND size_bytes = ? LIMIT 20",
        (sha256, size),
    ).fetchall()
    for row in rows:
        try:
            path = disk_path(store.root_path(settings, conn, row["root_id"]), row["relative_path"])
            info = os.stat(path)
        except (ApiError, OSError):
            continue
        if info.st_size == row["size_bytes"] and info.st_mtime_ns == row["mtime_ns"]:
            return path
    return None


def _commit_new(
    db: Database,
    settings: Settings,
    upload: sqlite3.Row,
    part: Path,
    user_id: str,
    device_id: str,
    new_relative_path: str | None,
) -> str:
    conn = db.conn()
    root_id: str = upload["root_id"]
    relative = check_item_path(
        upload["relative_path"] if new_relative_path is None else new_relative_path
    )
    root_dir = store.root_path(settings, conn, root_id)
    target = resolve_under(root_dir, relative)
    with store.root_lock(root_id):
        if path_in_use(conn, root_id, relative, target):
            raise ApiError("path_taken", "A file already exists at that path.")
        make_parents(target)
        linked = False
        # Hard-link dedupe (decision 6). Another disk or mount makes os.link fail: then the
        # part file is simply placed. The source belongs to another root whose lock is not
        # held; the size and mtime check in _find_duplicate keeps a concurrent change out.
        source = _find_duplicate(conn, settings, upload["sha256"], upload["size_bytes"])
        if source is not None:
            try:
                os.link(source, target)
                linked = True
            except OSError:
                linked = False
        if linked:
            try:
                part.unlink()
            except OSError:
                log.warning("The part file of upload %s could not be removed.", upload["upload_id"])
        else:
            place_file(part, target)
        size, mtime_ns, inode = file_facts(target)
        try:
            with db.transaction() as tx:
                item_id = store.insert_item(
                    tx,
                    user_id=user_id,
                    root_id=root_id,
                    relative_path=relative,
                    size_bytes=size,
                    mtime_ns=mtime_ns,
                    inode=inode,
                    device_id=device_id,
                    sha256=upload["sha256"],
                )
                tx.conn.execute(
                    "UPDATE uploads SET state = 'done', received_bytes = ?, updated_at_utc = ?"
                    " WHERE upload_id = ?",
                    (size, now_iso(), upload["upload_id"]),
                )
        except BaseException:
            # The file is in place and cannot be taken back safely (it may be a link to
            # another item's file); the next scan finds it and adds the item.
            log.exception(
                "Upload %s: the file was placed at %s (root %s) but the database step failed;"
                " the next scan will adopt it.",
                upload["upload_id"],
                relative,
                root_id,
            )
            raise
    return item_id


def _commit_replacement(
    db: Database,
    settings: Settings,
    upload: sqlite3.Row,
    part: Path,
    user_id: str,
    device_id: str,
) -> str:
    conn = db.conn()
    item_id: str = upload["base_item_id"]
    upload_id: str = upload["upload_id"]
    item = conn.execute(
        "SELECT root_id FROM items WHERE item_id = ? AND user_id = ? AND state = 'present'",
        (item_id, user_id),
    ).fetchone()
    if item is None:
        _set_state(db, upload_id, "conflict")
        raise ApiError("conflict", "The item no longer exists or is in the trash.")
    root_id: str = item["root_id"]
    library = library_folder(conn, settings, user_id)
    root_dir = store.root_path(settings, conn, root_id)
    with store.root_lock(root_id):
        current = conn.execute(
            "SELECT relative_path, revision, size_bytes FROM items"
            " WHERE item_id = ? AND state = 'present'",
            (item_id,),
        ).fetchone()
        if current is None:
            _set_state(db, upload_id, "conflict")
            raise ApiError("conflict", "The item no longer exists or is in the trash.")
        if current["revision"] != upload["base_revision"]:
            _set_state(db, upload_id, "conflict")
            raise ApiError(
                "conflict",
                f"The item is at revision {current['revision']} but the upload started from"
                f" revision {upload['base_revision']}.",
            )
        relative: str = current["relative_path"]
        target = disk_path(root_dir, relative)
        if not target.is_file():
            raise ApiError(
                "conflict", "The current file is missing on the server; scan the root first."
            )
        trash_id = new_id()
        stored = trash_stored_path(trash_id, PurePosixPath(relative).name)
        trash_file = library / stored
        trash_file.parent.mkdir(parents=True, exist_ok=True)
        # The old file leaves its path (and any hard link it shared): the new content is a
        # new file, so another user's linked copy is never touched.
        place_file(target, trash_file)
        try:
            place_file(part, target)
        except BaseException:
            undo_place(trash_file, target)
            remove_empty_dir(trash_file.parent)
            raise
        try:
            size, mtime_ns, inode = file_facts(target)
            with db.transaction() as tx:
                insert_trash_row(
                    tx,
                    trash_id=trash_id,
                    user_id=user_id,
                    item_id=item_id,
                    stored_path=stored,
                    root_id=root_id,
                    relative_path=relative,
                    size_bytes=int(current["size_bytes"]),
                    device_id=device_id,
                )
                store.replace_item_file(
                    tx,
                    item_id,
                    size_bytes=size,
                    mtime_ns=mtime_ns,
                    inode=inode,
                    device_id=device_id,
                    sha256=upload["sha256"],
                )
                tx.conn.execute(
                    "UPDATE uploads SET state = 'done', received_bytes = ?, updated_at_utc = ?"
                    " WHERE upload_id = ?",
                    (size, now_iso(), upload_id),
                )
        except BaseException:
            log.exception("Upload %s: the database step failed; undoing the file moves.", upload_id)
            undo_place(target, part)
            undo_place(trash_file, target)
            remove_empty_dir(trash_file.parent)
            raise
    return item_id


def undo_place(src: Path, dst: Path) -> None:
    """Move a file back after a failed step; a failure here is logged, not raised."""
    try:
        place_file(src, dst)
    except Exception:
        log.exception("Undoing a file move failed; the file is still at %s.", src.name)
