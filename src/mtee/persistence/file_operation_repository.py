"""Durable journal for renames, same-volume moves, recovery and Undo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mtee.domain.file_operations import FileOperationTarget, now_utc
from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository

__all__ = ["FileOperationJournalConflictError", "FileOperationRepository"]


class FileOperationJournalConflictError(RuntimeError):
    """The journal or library location changed before the move was recorded."""


class FileOperationRepository:
    """Persist per-track mutation phases without storing audio copies."""

    def __init__(self, database: Database, library: LibraryRepository) -> None:
        self._database = database
        self._library = library

    def create(
        self,
        *,
        operation_id: str,
        kind: str,
        target: FileOperationTarget,
        source_sha256: str,
        undo_of: str = "",
    ) -> None:
        now = now_utc()
        revision = target.revision
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO file_operations(operation_id,track_id,kind,source_path,"
                "destination_path,source_sha256,expected_size_bytes,expected_mtime_ns,"
                "expected_file_id,expected_generation,status,undo_of,created_at_utc,"
                "updated_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,'prepared',?,?,?)",
                (
                    operation_id,
                    target.track_id,
                    kind,
                    str(target.source),
                    str(target.destination),
                    source_sha256,
                    revision.size_bytes,
                    revision.mtime_ns,
                    revision.file_id,
                    revision.generation,
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
        error: str = "",
        recovery_path: Path | None = None,
        phase: str | None = None,
    ) -> None:
        with self._database.transaction() as connection:
            changed = connection.execute(
                "UPDATE file_operations SET status=?,error=?,recovery_path=?,"
                "phase=COALESCE(?,phase),updated_at_utc=? "
                "WHERE operation_id=?",
                (
                    status,
                    error,
                    str(recovery_path) if recovery_path else None,
                    phase,
                    now_utc(),
                    operation_id,
                ),
            ).rowcount
            if changed != 1:
                raise KeyError(f"Unknown file operation: {operation_id}")

    def update_phase(
        self, operation_id: str, phase: str, *, recovery_path: Path | None = None
    ) -> None:
        """Record a copy/move boundary before continuing its file-system work."""
        with self._database.transaction() as connection:
            changed = connection.execute(
                "UPDATE file_operations SET phase=?,recovery_path=?,updated_at_utc=? "
                "WHERE operation_id=? AND status='prepared'",
                (phase, str(recovery_path) if recovery_path else None, now_utc(), operation_id),
            ).rowcount
            if changed != 1:
                raise KeyError(f"File operation is no longer prepared: {operation_id}")

    def complete(
        self,
        *,
        operation_id: str,
        track_id: str,
        expected_revision: SourceRevision,
        destination: Path,
        result_revision: SourceRevision,
        metadata: MetadataSnapshot,
        undo_of: str = "",
    ) -> None:
        with self._database.transaction() as connection:
            self._library.move_location_in_transaction(
                connection,
                track_id=track_id,
                expected_revision=expected_revision,
                destination=destination,
                new_revision=result_revision,
                metadata=metadata,
            )
            completed = connection.execute(
                "UPDATE file_operations SET status='completed',result_size_bytes=?,"
                "result_mtime_ns=?,result_file_id=?,result_generation=?,error='',phase='completed',"
                "updated_at_utc=? "
                "WHERE operation_id=? AND status='prepared'",
                (
                    result_revision.size_bytes,
                    result_revision.mtime_ns,
                    result_revision.file_id,
                    result_revision.generation,
                    now_utc(),
                    operation_id,
                ),
            ).rowcount
            if completed != 1:
                raise FileOperationJournalConflictError("The move journal is no longer prepared.")
            if undo_of:
                undone = connection.execute(
                    "UPDATE file_operations SET status='undone',phase='undone',updated_at_utc=? "
                    "WHERE operation_id=? AND status='completed' AND undo_of IS NULL",
                    (now_utc(), undo_of),
                ).rowcount
                if undone != 1:
                    raise FileOperationJournalConflictError(
                        "The move selected for Undo was already changed or undone."
                    )

    def get(self, operation_id: str) -> dict[str, Any] | None:
        row = (
            self._database.connection()
            .execute("SELECT * FROM file_operations WHERE operation_id=?", (operation_id,))
            .fetchone()
        )
        return dict(row) if row is not None else None

    def incomplete(self) -> list[dict[str, Any]]:
        rows = self._database.connection().execute(
            "SELECT * FROM file_operations WHERE status IN ('prepared','needs_recovery') "
            "ORDER BY created_at_utc"
        )
        return [dict(row) for row in rows]

    def latest_undoable(self) -> dict[str, Any] | None:
        row = (
            self._database.connection()
            .execute(
                "SELECT * FROM file_operations WHERE status='completed' AND undo_of IS NULL "
                "ORDER BY created_at_utc DESC,rowid DESC LIMIT 1"
            )
            .fetchone()
        )
        return dict(row) if row is not None else None
