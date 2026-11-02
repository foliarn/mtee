"""Database backups: storage, retention and settings (milestone 124.7).

The server stores the bytes of a backup and its metadata. It never opens a backup.

- A backup is uploaded like an item: `POST /api/v1/uploads` with purpose `backup`
  (`uploads.create_backup_upload`). Its part file is in `<data>/uploads/`.
- A present backup lives at `backups.stored_path`, relative to `<data>/`:
  `backups/<user_id>/<backup_id>.db`. Every move is a rename on the same volume, and
  `uploads.place_file` never overwrites.
- A trashed backup moves to `<data>/trash/backups/<backup_id>.db` (trash row of kind `backup`,
  `trash.stored_path` relative to `<data>/trash/`). Restoring moves it back.
- Retention (`apply_retention`) keeps every manual backup. Among the automatic ones it keeps the
  newest backup of each of the `daily` most recent UTC dates that have one, and the newest of
  each of the `weekly` most recent ISO weeks that have one. The union is kept; every other
  automatic backup goes to the trash, exactly as `DELETE` does. It runs after each automatic
  commit and after a settings change.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from mtee_remote import journal, trash, uploads
from mtee_remote.config import Settings
from mtee_remote.db import Database
from mtee_remote.errors import ApiError
from mtee_remote.ids import new_id
from mtee_remote.paths import disk_path

log = logging.getLogger(__name__)

BACKUP_DIRNAME = "backups"
SETTINGS_KEY = "backups"
DEFAULT_DAILY = 30
DEFAULT_WEEKLY = 12
MAX_DAILY = 365
MAX_WEEKLY = 104

_COLUMNS = (
    "backup_id, user_id, device_id, label, kind, size_bytes, sha256, stored_path, state,"
    " created_at_utc"
)


def backup_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """The client view of a backup row: no storage path."""
    return {
        "backup_id": row["backup_id"],
        "label": row["label"],
        "kind": row["kind"],
        "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
        "device_id": row["device_id"],
        "created_at_utc": row["created_at_utc"],
    }


def _present_row(conn: sqlite3.Connection, user_id: str, backup_id: str) -> sqlite3.Row:
    """The user's present backup, or `not_found` (also for another user's backup)."""
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM backups WHERE backup_id = ? AND user_id = ? AND state = 'present'",
        (backup_id, user_id),
    ).fetchone()
    if row is None:
        raise ApiError("not_found", "Unknown backup.")
    return row


def public_by_id(conn: sqlite3.Connection, user_id: str, backup_id: str) -> dict[str, Any]:
    """`backup_public` of a present backup of the user."""
    return backup_public(_present_row(conn, user_id, backup_id))


def _public_any_state(conn: sqlite3.Connection, user_id: str, backup_id: str) -> dict[str, Any]:
    """`backup_public` of the user's backup in any state (for the commit response).

    Retention may already have moved a just-committed backup to the trash (settings of zero
    days and zero weeks), and the upload still succeeded.
    """
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM backups WHERE backup_id = ? AND user_id = ?",
        (backup_id, user_id),
    ).fetchone()
    if row is None:
        raise ApiError("not_found", "Unknown backup.")
    return backup_public(row)


def list_backups(conn: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    """The user's present backups, newest first."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM backups WHERE user_id = ? AND state = 'present'"
        " ORDER BY created_at_utc DESC, rowid DESC",
        (user_id,),
    ).fetchall()
    return [backup_public(row) for row in rows]


def backup_file(db: Database, settings: Settings, user_id: str, backup_id: str) -> tuple[str, str]:
    """Return `(file path, sha256)` of a present backup; `not_found` when it is not the user's."""
    row = _present_row(db.conn(), user_id, backup_id)
    path = disk_path(settings.data_dir, row["stored_path"])
    return str(path), str(row["sha256"])


def commit_backup(
    db: Database,
    settings: Settings,
    *,
    user_id: str,
    device_id: str,
    upload_id: str,
    new_relative_path: str | None,
) -> dict[str, Any]:
    """Store a received backup, record it, apply retention; return `backup_public`.

    The file moves first, then one transaction records the backup, finishes the upload and
    journals `backup_added`. A failed transaction moves the file back. Retention runs after
    the commit; its failure is logged, because the backup itself is stored.
    """
    if new_relative_path is not None:
        raise ApiError("bad_request", "A backup has no path.")
    row, part = uploads.verify_received(db, settings, user_id=user_id, upload_id=upload_id)
    label, kind = uploads.decode_backup_meta(row["label"])
    size_bytes = int(row["size_bytes"])
    backup_id = new_id()
    stored = f"{BACKUP_DIRNAME}/{user_id}/{backup_id}.db"
    target = disk_path(settings.data_dir, stored)
    target.parent.mkdir(parents=True, exist_ok=True)
    uploads.place_file(part, target)
    try:
        with db.transaction() as tx:
            tx.conn.execute(
                "INSERT INTO backups(backup_id, user_id, device_id, label, kind, size_bytes,"
                " sha256, stored_path, state, created_at_utc)"
                " VALUES (?,?,?,?,?,?,?,?,'present',?)",
                (
                    backup_id,
                    user_id,
                    device_id,
                    label,
                    kind,
                    size_bytes,
                    row["sha256"],
                    stored,
                    uploads.now_iso(),
                ),
            )
            tx.conn.execute(
                "UPDATE uploads SET state = 'done', received_bytes = ?, updated_at_utc = ?"
                " WHERE upload_id = ?",
                (size_bytes, uploads.now_iso(), upload_id),
            )
            journal.append(
                tx,
                user_id,
                "backup_added",
                None,
                {"backup_id": backup_id, "label": label, "kind": kind, "size_bytes": size_bytes},
            )
    except BaseException:
        log.exception("Backup %s: the database step failed; moving the file back.", backup_id)
        uploads.undo_place(target, part)
        raise
    try:
        apply_retention(db, settings, user_id=user_id, device_id=device_id)
    except Exception:
        log.exception("Retention for user %s failed; it runs again at the next backup.", user_id)
    return {"backup": _public_any_state(db.conn(), user_id, backup_id)}


def delete_backup(
    db: Database, settings: Settings, *, user_id: str, device_id: str, backup_id: str
) -> None:
    """`DELETE /api/v1/backups/{id}`: move the backup to the trash."""
    trash.trash_backup(db, settings, user_id=user_id, backup_id=backup_id, device_id=device_id)


# -- settings --------------------------------------------------------------------------


def read_settings(conn: sqlite3.Connection, user_id: str) -> tuple[int, int]:
    """Return `(daily, weekly)` of the user; the defaults when the user has no row."""
    row = conn.execute(
        "SELECT value_json FROM user_settings WHERE user_id = ? AND key = ?",
        (user_id, SETTINGS_KEY),
    ).fetchone()
    if row is None:
        return DEFAULT_DAILY, DEFAULT_WEEKLY
    data: dict[str, Any] = json.loads(row["value_json"])
    return int(data["daily"]), int(data["weekly"])


def get_settings(db: Database, user_id: str) -> dict[str, int]:
    daily, weekly = read_settings(db.conn(), user_id)
    return {"daily": daily, "weekly": weekly}


def put_settings(
    db: Database, settings: Settings, *, user_id: str, device_id: str, daily: int, weekly: int
) -> dict[str, int]:
    """Store `daily` (0..365) and `weekly` (0..104), then apply retention with them."""
    if not 0 <= daily <= MAX_DAILY:
        raise ApiError("bad_request", f"The field 'daily' must be from 0 to {MAX_DAILY}.")
    if not 0 <= weekly <= MAX_WEEKLY:
        raise ApiError("bad_request", f"The field 'weekly' must be from 0 to {MAX_WEEKLY}.")
    value = json.dumps({"daily": daily, "weekly": weekly}, separators=(",", ":"))
    with db.transaction() as tx:
        tx.conn.execute(
            "INSERT INTO user_settings(user_id, key, value_json) VALUES (?,?,?)"
            " ON CONFLICT(user_id, key) DO UPDATE SET value_json = excluded.value_json",
            (user_id, SETTINGS_KEY, value),
        )
    try:
        apply_retention(db, settings, user_id=user_id, device_id=device_id)
    except Exception:
        log.exception("Retention for user %s failed; it runs again at the next backup.", user_id)
    return {"daily": daily, "weekly": weekly}


# -- retention -------------------------------------------------------------------------


def _utc_day_and_week(created_at_utc: str) -> tuple[date, tuple[int, int]]:
    moment = datetime.fromisoformat(created_at_utc).astimezone(UTC)
    day = moment.date()
    iso = day.isocalendar()
    return day, (iso.year, iso.week)


def kept_backup_ids(backups: Sequence[tuple[str, str]], daily: int, weekly: int) -> set[str]:
    """Return the ids to keep among automatic backups, given as `(backup_id, created_at_utc)`.

    `backups` must be in ascending order of creation. The newest backup of each of the `daily`
    most recent UTC dates that have one is kept, and the newest of each of the `weekly` most
    recent ISO weeks that have one. The result is the union of the two.
    """
    newest_by_day: dict[date, str] = {}
    newest_by_week: dict[tuple[int, int], str] = {}
    for backup_id, created_at_utc in backups:
        day, week = _utc_day_and_week(created_at_utc)
        newest_by_day[day] = backup_id  # ascending order: the last one is the newest
        newest_by_week[week] = backup_id
    kept: set[str] = set()
    for day in sorted(newest_by_day, reverse=True)[:daily]:
        kept.add(newest_by_day[day])
    for week in sorted(newest_by_week, reverse=True)[:weekly]:
        kept.add(newest_by_week[week])
    return kept


def apply_retention(
    db: Database, settings: Settings, *, user_id: str, device_id: str | None
) -> list[str]:
    """Trash the automatic backups that the user's settings do not keep; return their ids.

    Works on the creation times of the backups only, so it needs no clock. Manual backups
    are never touched.
    """
    with trash.BACKUP_LOCK:
        conn = db.conn()
        daily, weekly = read_settings(conn, user_id)
        rows = conn.execute(
            "SELECT backup_id, created_at_utc FROM backups"
            " WHERE user_id = ? AND kind = 'automatic' AND state = 'present'"
            " ORDER BY created_at_utc, rowid",
            (user_id,),
        ).fetchall()
        pairs = [(row["backup_id"], row["created_at_utc"]) for row in rows]
        keep = kept_backup_ids(pairs, daily, weekly)
        trashed: list[str] = []
        for backup_id, _ in pairs:
            if backup_id not in keep:
                trash.trash_backup(
                    db, settings, user_id=user_id, backup_id=backup_id, device_id=device_id
                )
                trashed.append(backup_id)
        return trashed
