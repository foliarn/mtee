"""The plugin's tables, through small typed helpers (plan 126.2).

Reads and writes go through the shared ``Database``: each thread gets its own connection, so the
helpers may be called from a job thread and from the graphical thread alike. A write that touches
several rows runs in one transaction, through ``RemoteStore.transaction``. The module functions
take the connection of that transaction; they never open one themselves.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from mtee.plugins.api import PluginContext

CONFLICT_OPEN = "open"
CONFLICT_DECIDE_LATER = "decide_later"
CONFLICT_RESOLVED = "resolved"
# A decide-later conflict that the person dismissed from Tasks carries this key in its local JSON
# (plan 126.6): it is hidden until the next change on either side reopens it.
DISMISSED_KEY = "dismissed_at_utc"
_OPEN_QUEUE_STATES = ("pending", "running", "failed", "blocked")


def utc_now() -> str:
    """The time of a row, as an ISO 8601 text in UTC."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class FolderMapping:
    """A watched folder of this computer and the server folder it syncs with."""

    local_root_path: str
    server_root_id: str
    server_subpath: str = ""


@dataclass(frozen=True)
class ServerRow:
    """One server item stored as a server-only row."""

    item_id: str
    root_id: str
    relative_path: str
    size_bytes: int
    sha256: str | None
    audio_hash: str | None
    revision: int
    metadata_json: str | None
    updated_at_utc: str


@dataclass(frozen=True)
class CachedHashes:
    sha256: str
    audio_hash: str | None


class RemoteStore:
    """Thread-aware access to the plugin's tables for one context."""

    def __init__(self, context: PluginContext) -> None:
        self._database = context.database

    def connection(self) -> sqlite3.Connection:
        """The connection of the calling thread."""
        return self._database.connection()

    def transaction(self) -> AbstractContextManager[sqlite3.Connection]:
        """A context manager that yields the connection inside one write transaction."""
        return self._database.transaction()

    # -- hash cache ----------------------------------------------------------------------
    def cached_hashes(self, path: str, size_bytes: int, mtime_ns: int) -> CachedHashes | None:
        row = (
            self.connection()
            .execute(
                "SELECT sha256, audio_hash FROM remote_hash_cache"
                " WHERE path = ? AND size_bytes = ? AND mtime_ns = ?",
                (path, size_bytes, mtime_ns),
            )
            .fetchone()
        )
        if row is None:
            return None
        return CachedHashes(str(row["sha256"]), row["audio_hash"])

    def remember_hashes(
        self, path: str, size_bytes: int, mtime_ns: int, hashes: CachedHashes
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO remote_hash_cache (path, size_bytes, mtime_ns, sha256, audio_hash)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (path) DO UPDATE SET size_bytes = excluded.size_bytes,"
                " mtime_ns = excluded.mtime_ns, sha256 = excluded.sha256,"
                " audio_hash = excluded.audio_hash",
                (path, size_bytes, mtime_ns, hashes.sha256, hashes.audio_hash),
            )

    # -- mappings ------------------------------------------------------------------------
    def mappings(self) -> list[FolderMapping]:
        rows = self.connection().execute(
            "SELECT local_root_path, server_root_id, server_subpath FROM remote_mappings"
            " ORDER BY local_root_path"
        )
        return [
            FolderMapping(
                str(row["local_root_path"]), str(row["server_root_id"]), str(row["server_subpath"])
            )
            for row in rows.fetchall()
        ]

    def save_mapping(self, mapping: FolderMapping) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO remote_mappings (local_root_path, server_root_id, server_subpath)"
                " VALUES (?, ?, ?) ON CONFLICT (local_root_path) DO UPDATE SET"
                " server_root_id = excluded.server_root_id,"
                " server_subpath = excluded.server_subpath",
                (mapping.local_root_path, mapping.server_root_id, mapping.server_subpath),
            )

    def remove_mapping(self, local_root_path: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "DELETE FROM remote_mappings WHERE local_root_path = ?", (local_root_path,)
            )


# -- module functions: each takes the connection of an open transaction ------------------
def write_log(conn: sqlite3.Connection, text: str, level: str = "info") -> None:
    conn.execute(
        "INSERT INTO remote_log (at_utc, level, text) VALUES (?, ?, ?)",
        (utc_now(), level, text),
    )


def insert_link(
    conn: sqlite3.Connection,
    *,
    track_id: str,
    item_id: str,
    item_revision: int,
    local_sha256: str,
    audio_hash: str | None,
    server_path: str | None = None,
) -> bool:
    """Link a local track to a server item; True when the row was added.

    A track already linked, or an item already linked to another track, is left alone: the first
    link stays, so a run that finds the same pair again adds nothing. ``server_path`` is the
    item's path on the server when the link was made (the move rule of plan 126.3 reads it).
    """
    cursor = conn.execute(
        "INSERT OR IGNORE INTO remote_links (track_id, item_id, item_revision, local_sha256,"
        " audio_hash, linked_at_utc, server_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (track_id, item_id, item_revision, local_sha256, audio_hash, utc_now(), server_path),
    )
    return cursor.rowcount == 1


def is_dismissed(local_json: str | None) -> bool:
    """True when a conflict's local JSON says the person dismissed it (see ``DISMISSED_KEY``)."""
    try:
        value = json.loads(local_json or "{}")
    except ValueError:
        return False
    return isinstance(value, dict) and bool(value.get(DISMISSED_KEY))


def has_open_conflict(conn: sqlite3.Connection, track_id: str, item_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM remote_conflicts WHERE track_id = ? AND item_id = ? AND state <> 'resolved'",
        (track_id, item_id),
    ).fetchone()
    return row is not None


def insert_conflict(
    conn: sqlite3.Connection,
    *,
    track_id: str | None,
    item_id: str | None,
    local: dict[str, Any],
    server: dict[str, Any],
    state: str = CONFLICT_DECIDE_LATER,
) -> None:
    conn.execute(
        "INSERT INTO remote_conflicts (conflict_id, track_id, item_id, local_json, server_json,"
        " created_at_utc, state) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            new_id(),
            track_id,
            item_id,
            json.dumps(local, ensure_ascii=False, sort_keys=True),
            json.dumps(server, ensure_ascii=False, sort_keys=True),
            utc_now(),
            state,
        ),
    )


def enqueue(
    conn: sqlite3.Connection, *, kind: str, track_id: str | None, item_id: str | None
) -> bool:
    """Add a pending queue entry; False when the same kind is already queued for the track."""
    if track_id is not None:
        placeholders = ", ".join("?" for _ in _OPEN_QUEUE_STATES)
        taken = conn.execute(
            "SELECT 1 FROM remote_queue WHERE kind = ? AND track_id = ?"
            f" AND state IN ({placeholders})",
            (kind, track_id, *_OPEN_QUEUE_STATES),
        ).fetchone()
        if taken is not None:
            return False
    now = utc_now()
    conn.execute(
        "INSERT INTO remote_queue (op_id, kind, track_id, item_id, state, attempts,"
        " created_at_utc, updated_at_utc) VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)",
        (new_id(), kind, track_id, item_id, now, now),
    )
    return True


def server_item_exists(conn: sqlite3.Connection, item_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM remote_server_items WHERE item_id = ?", (item_id,))
    return row.fetchone() is not None


def upsert_server_item(conn: sqlite3.Connection, row: ServerRow) -> None:
    conn.execute(
        "INSERT INTO remote_server_items (item_id, root_id, relative_path, size_bytes, sha256,"
        " audio_hash, revision, metadata_json, source_track_id, updated_at_utc)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)"
        " ON CONFLICT (item_id) DO UPDATE SET root_id = excluded.root_id,"
        " relative_path = excluded.relative_path, size_bytes = excluded.size_bytes,"
        " sha256 = excluded.sha256, audio_hash = excluded.audio_hash,"
        " revision = excluded.revision, metadata_json = excluded.metadata_json,"
        " updated_at_utc = excluded.updated_at_utc",
        (
            row.item_id,
            row.root_id,
            row.relative_path,
            row.size_bytes,
            row.sha256,
            row.audio_hash,
            row.revision,
            row.metadata_json,
            row.updated_at_utc,
        ),
    )
