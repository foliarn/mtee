"""Durable per-field edit history and recovery phases."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import normalize_path

__all__ = ["MetadataHistoryRepository", "RepositoryRevisionConflictError"]


class RepositoryRevisionConflictError(RuntimeError):
    """The catalog changed before a verified file edit could be recorded."""


class MetadataHistoryRepository:
    """Store only changed tag values, revisions, and owned recovery paths."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self,
        *,
        operation_id: str,
        draft_id: str,
        track_id: str,
        source_path: Path,
        revision: SourceRevision,
        source_sha256: str,
        temporary_path: Path,
        backup_path: Path,
        before: dict[str, str | None],
        after: dict[str, str | None],
        undo_of: str = "",
    ) -> None:
        now = _now()
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO metadata_edit_operations("
                "operation_id,draft_id,track_id,source_path,expected_generation,"
                "expected_size_bytes,expected_mtime_ns,source_sha256,temporary_path,"
                "backup_path,before_json,after_json,status,undo_of,created_at_utc,updated_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    operation_id,
                    draft_id,
                    track_id,
                    str(source_path),
                    revision.generation,
                    revision.size_bytes,
                    revision.mtime_ns,
                    source_sha256,
                    str(temporary_path),
                    str(backup_path),
                    _json(before),
                    _json(after),
                    "prepared",
                    undo_of or None,
                    now,
                    now,
                ),
            )

    def set_status(
        self,
        operation_id: str,
        status: str,
        *,
        new_sha256: str = "",
        after: dict[str, str | None] | None = None,
        error: str = "",
    ) -> None:
        with self._database.transaction() as connection:
            changed = connection.execute(
                "UPDATE metadata_edit_operations SET status=?,"
                "new_sha256=COALESCE(NULLIF(?,''),new_sha256),"
                "after_json=COALESCE(?,after_json),error=?,updated_at_utc=? "
                "WHERE operation_id=?",
                (
                    status,
                    new_sha256,
                    _json(after) if after is not None else None,
                    error,
                    _now(),
                    operation_id,
                ),
            ).rowcount
            if changed != 1:
                raise KeyError(f"Unknown metadata operation: {operation_id}")

    def complete(
        self,
        *,
        operation_id: str,
        track_id: str,
        path: Path,
        expected_revision: SourceRevision,
        new_revision: SourceRevision,
        snapshot: MetadataSnapshot,
        new_sha256: str,
        undo_of: str = "",
    ) -> None:
        """Update the source cache and history in one SQLite transaction."""
        encoded = _json(snapshot.to_dict())
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE track_locations SET size_bytes=?,mtime_ns=?,file_id=?,generation=?,"
                "file_modified_at_ns=?,"
                "duration_us=?,status=?,metadata_json=? WHERE track_id=? AND path_key=? "
                "AND size_bytes=? AND mtime_ns=? AND file_id IS ? AND generation=?",
                (
                    new_revision.size_bytes,
                    new_revision.mtime_ns,
                    new_revision.file_id,
                    new_revision.generation,
                    new_revision.mtime_ns,
                    snapshot.technical.duration_us,
                    snapshot.status,
                    encoded,
                    track_id,
                    normalize_path(path),
                    expected_revision.size_bytes,
                    expected_revision.mtime_ns,
                    expected_revision.file_id,
                    expected_revision.generation,
                ),
            )
            if cursor.rowcount != 1:
                raise RepositoryRevisionConflictError(
                    "The library record changed while the metadata write was in progress."
                )
            changed = connection.execute(
                "UPDATE metadata_edit_operations SET status='completed',new_sha256=?,error='',"
                "updated_at_utc=? WHERE operation_id=? AND status IN ('publishing','published')",
                (new_sha256, _now(), operation_id),
            ).rowcount
            if changed != 1:
                raise RepositoryRevisionConflictError(
                    "The edit journal no longer matches this write."
                )
            if undo_of:
                undone = connection.execute(
                    "UPDATE metadata_edit_operations SET status='undone',"
                    "undone_by=?,updated_at_utc=? "
                    "WHERE operation_id=? AND status='completed' AND undone_by IS NULL",
                    (operation_id, _now(), undo_of),
                ).rowcount
                if undone != 1:
                    raise RepositoryRevisionConflictError(
                        "The save selected for Undo was already changed or undone."
                    )

    def get(self, operation_id: str) -> dict[str, Any] | None:
        row = (
            self._database.connection()
            .execute("SELECT * FROM metadata_edit_operations WHERE operation_id=?", (operation_id,))
            .fetchone()
        )
        return _row_dict(row) if row is not None else None

    def latest_undoable(self, track_id: str) -> dict[str, Any] | None:
        row = (
            self._database.connection()
            .execute(
                "SELECT * FROM metadata_edit_operations WHERE track_id=? AND status='completed' "
                "AND undo_of IS NULL AND undone_by IS NULL "
                "ORDER BY created_at_utc DESC, rowid DESC LIMIT 1",
                (track_id,),
            )
            .fetchone()
        )
        return _row_dict(row) if row is not None else None

    def incomplete(self) -> list[dict[str, Any]]:
        rows = (
            self._database.connection()
            .execute(
                "SELECT * FROM metadata_edit_operations WHERE status IN "
                "('prepared','publishing','published','needs_recovery') ORDER BY created_at_utc"
            )
            .fetchall()
        )
        return [_row_dict(row) for row in rows]

    def has_incomplete_for_track(self, track_id: str) -> bool:
        row = (
            self._database.connection()
            .execute(
                "SELECT 1 FROM metadata_edit_operations WHERE track_id=? AND status IN "
                "('prepared','publishing','published','needs_recovery') LIMIT 1",
                (track_id,),
            )
            .fetchone()
        )
        return row is not None


def _row_dict(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["before"] = json.loads(str(result.pop("before_json")))
    result["after"] = json.loads(str(result.pop("after_json")))
    return result


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")
