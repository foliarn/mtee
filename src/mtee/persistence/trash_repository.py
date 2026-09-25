"""Durable audit for recycle-bin operations that may be interrupted."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database

__all__ = ["TrashRepository"]


class TrashRepository:
    """Record each requested recycle before calling the Windows shell."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def prepare(
        self, operation_id: str, track_id: str, path: str, revision: SourceRevision
    ) -> None:
        now = _now()
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO trash_operations(operation_id,track_id,source_path,"
                "expected_size_bytes,expected_mtime_ns,expected_file_id,expected_generation,"
                "status,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'prepared',?,?)",
                (
                    operation_id,
                    track_id,
                    path,
                    revision.size_bytes,
                    revision.mtime_ns,
                    revision.file_id,
                    revision.generation,
                    now,
                    now,
                ),
            )

    def finish(
        self,
        operation_id: str,
        status: str,
        message: str = "",
        recycle_item_identity: str = "",
    ) -> None:
        if status not in {"recycled", "failed", "conflict"}:
            raise ValueError(f"Unsupported trash operation status: {status}")
        if status != "recycled" and recycle_item_identity:
            raise ValueError("Only a recycled item can have a Recycle Bin identity.")
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE trash_operations SET status=?,result_message=?,recycle_item_identity=?,"
                "updated_at_utc=? "
                "WHERE operation_id=? AND status='prepared'",
                (status, message, recycle_item_identity, _now(), operation_id),
            )

    def interrupted(self) -> list[dict[str, Any]]:
        """Return prepared rows for inspection; missing paths are never treated as success."""
        with self._database.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM trash_operations WHERE status='prepared' "
                    "ORDER BY created_at_utc,operation_id"
                )
            ]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
