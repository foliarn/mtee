"""Data and privacy actions: database backup, restore and statistics reset.

Restore is a two-step flow, because the running application holds the database open:

1. ``stage_restore`` validates a backup chosen by the user and copies it into
   ``<data>/restore/pending.sqlite3``. The copy is written before the marker file
   ``pending.json``; without the marker the copy is ignored and removed at the next start.
   The live database is not touched.
2. ``apply_pending_restore`` runs at the next start, before the database is opened. It
   validates the copy again, writes a consistent safety backup of the current database
   (``<data>/restore/before-restore-<stamp>.sqlite3``), removes the WAL and shared-memory
   sidecars of the old file and replaces the database with the copy in one rename.
   Any failure before the rename leaves the current database in place and cancels the
   scheduled restore, with the reason reported.

The source file chosen by the user is only read. Nothing here deletes a backup.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mtee.persistence.database import Database, Migration, foreign_migration_names
from mtee.persistence.play_log_repository import PlayLogRepository

__all__ = [
    "BACKUP_SUFFIX",
    "SQLITE_HEADER",
    "BackupInfo",
    "BackupValidationError",
    "PendingRestore",
    "RestoreLayout",
    "RestoreOutcome",
    "apply_pending_restore",
    "back_up_database",
    "cancel_pending_restore",
    "default_backup_name",
    "read_pending_restore",
    "reset_statistics",
    "stage_restore",
    "validate_backup",
]

BACKUP_SUFFIX = ".sqlite3"
SQLITE_HEADER = b"SQLite format 3\x00"
_RESTORE_DIR_NAME = "restore"
_PENDING_FILE_NAME = "pending.sqlite3"
_MARKER_FILE_NAME = "pending.json"
_RESULT_FILE_NAME = "last-restore.json"
_SIDECAR_SUFFIXES = ("-wal", "-shm")


class BackupValidationError(ValueError):
    """Raised with a readable reason when a file cannot be used as a database backup."""


@dataclass(frozen=True, slots=True)
class BackupInfo:
    """What a validated backup contains, shown to the user before the restore is scheduled."""

    schema_version: int
    track_count: int
    size_bytes: int


@dataclass(frozen=True, slots=True)
class PendingRestore:
    """A restore scheduled for the next start."""

    source_name: str
    staged_at_utc: str
    info: BackupInfo


@dataclass(frozen=True, slots=True)
class RestoreOutcome:
    """Result of the restore attempted at start-up, for the Data & privacy page."""

    applied: bool
    message: str
    source_name: str
    safety_backup: Path | None = None


@dataclass(frozen=True, slots=True)
class RestoreLayout:
    """Where the restore files of one data directory live."""

    data_dir: Path

    @property
    def directory(self) -> Path:
        return self.data_dir / _RESTORE_DIR_NAME

    @property
    def pending_file(self) -> Path:
        return self.directory / _PENDING_FILE_NAME

    @property
    def marker_file(self) -> Path:
        return self.directory / _MARKER_FILE_NAME

    @property
    def result_file(self) -> Path:
        return self.directory / _RESULT_FILE_NAME


def default_backup_name(now: datetime) -> str:
    """Return a backup file name carrying the UTC time, for the save dialog."""
    return f"mtee-backup-{now.astimezone(UTC).strftime('%Y%m%d-%H%M%S')}{BACKUP_SUFFIX}"


def back_up_database(database: Database, destination: Path) -> Path:
    """Write a consistent copy of ``database`` to ``destination`` and verify it.

    ``Database.backup_to`` refuses to replace an existing file, so a backup is never
    overwritten. The copy is read through the SQLite backup API, so it includes data
    still held in the write-ahead log.
    """
    return database.backup_to(destination)


def reset_statistics(play_log: PlayLogRepository) -> int:
    """Delete every listening event and return how many were removed.

    The installation identifier and the playback history are kept.
    """
    return play_log.reset()


def validate_backup(
    path: Path,
    *,
    supported_version: int,
    migrations: Sequence[Migration],
    database_path: Path | None = None,
) -> BackupInfo:
    """Check that ``path`` is an MTEE database this build can open, and describe it.

    The checks: a SQLite header, a full integrity check, a schema version that is not
    newer than this build, and a migration history that matches the scripts shipped
    with this build. The file is opened read-only. A file that is the live database
    itself is refused.
    """
    if not path.is_file():
        raise BackupValidationError("The chosen file does not exist.")
    size = path.stat().st_size
    if size < len(SQLITE_HEADER):
        raise BackupValidationError("The chosen file is not an MTEE database.")
    with path.open("rb") as handle:
        if handle.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
            raise BackupValidationError("The chosen file is not an SQLite database.")
    if database_path is not None and path.resolve() == database_path.resolve():
        raise BackupValidationError("The chosen file is the database currently in use.")
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise BackupValidationError(f"The database cannot be opened: {error}") from error
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise BackupValidationError("The database failed its integrity check.")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version < 1 or not _has_table(connection, "schema_migrations"):
            raise BackupValidationError("The file has no MTEE schema history.")
        if version > supported_version:
            raise BackupValidationError(
                f"This backup uses schema version {version}; this build of MTEE supports "
                f"version {supported_version}. Update MTEE to restore it."
            )
        _check_migration_history(connection, version, migrations)
        track_count = (
            int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
            if _has_table(connection, "tracks")
            else 0
        )
    except sqlite3.DatabaseError as error:
        raise BackupValidationError(f"The database is damaged or unreadable: {error}") from error
    finally:
        connection.close()
    return BackupInfo(schema_version=version, track_count=track_count, size_bytes=size)


def stage_restore(
    source: Path,
    layout: RestoreLayout,
    *,
    database_path: Path,
    supported_version: int,
    migrations: Sequence[Migration],
    now: datetime,
) -> PendingRestore:
    """Validate ``source`` and schedule it as the database of the next start."""
    info = validate_backup(
        source,
        supported_version=supported_version,
        migrations=migrations,
        database_path=database_path,
    )
    layout.directory.mkdir(parents=True, exist_ok=True)
    # The previous schedule is withdrawn first, so the marker never describes another copy.
    layout.marker_file.unlink(missing_ok=True)
    temporary = layout.directory / f"{_PENDING_FILE_NAME}.tmp"
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, layout.pending_file)
    finally:
        temporary.unlink(missing_ok=True)
    staged_at = now.astimezone(UTC).isoformat(timespec="seconds")
    record = {
        "source_name": source.name,
        "staged_at_utc": staged_at,
        "schema_version": info.schema_version,
        "track_count": info.track_count,
        "size_bytes": info.size_bytes,
    }
    _write_json_atomic(layout.marker_file, record)
    return PendingRestore(source.name, staged_at, info)


def read_pending_restore(layout: RestoreLayout) -> PendingRestore | None:
    """Return the scheduled restore, or ``None`` when none is scheduled."""
    if not layout.marker_file.is_file() or not layout.pending_file.is_file():
        return None
    try:
        record = json.loads(layout.marker_file.read_text(encoding="utf-8"))
        info = BackupInfo(
            schema_version=int(record["schema_version"]),
            track_count=int(record["track_count"]),
            size_bytes=int(record["size_bytes"]),
        )
        return PendingRestore(str(record["source_name"]), str(record["staged_at_utc"]), info)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def cancel_pending_restore(layout: RestoreLayout) -> None:
    """Remove the scheduled restore. The marker goes first, so a partial state is ignored."""
    layout.marker_file.unlink(missing_ok=True)
    layout.pending_file.unlink(missing_ok=True)


def apply_pending_restore(
    layout: RestoreLayout,
    *,
    database_path: Path,
    supported_version: int,
    migrations: Sequence[Migration],
    now: datetime,
) -> RestoreOutcome | None:
    """Apply a scheduled restore before the database is opened; ``None`` when there is none.

    Call it before any connection to ``database_path`` exists. A restore that cannot be
    applied is cancelled and reported; the current database is then left as it was.
    """
    if not layout.marker_file.exists():
        # A copy without its marker is an interrupted staging: it is never applied.
        layout.pending_file.unlink(missing_ok=True)
        return None
    pending = read_pending_restore(layout)
    if pending is None:
        cancel_pending_restore(layout)
        return _record_outcome(
            layout,
            RestoreOutcome(
                False, "The scheduled restore was cancelled: its record is unreadable.", ""
            ),
        )
    source_name = pending.source_name
    try:
        validate_backup(
            layout.pending_file,
            supported_version=supported_version,
            migrations=migrations,
        )
    except BackupValidationError as error:
        cancel_pending_restore(layout)
        return _record_outcome(
            layout,
            RestoreOutcome(False, f"The scheduled restore was cancelled: {error}", source_name),
        )
    safety_backup: Path | None = None
    if database_path.exists():
        stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        safety_backup = layout.directory / f"before-restore-{stamp}{BACKUP_SUFFIX}"
        database = Database(database_path)
        try:
            database.backup_to(safety_backup)
        except Exception as error:
            cancel_pending_restore(layout)
            return _record_outcome(
                layout,
                RestoreOutcome(
                    False,
                    f"The scheduled restore was cancelled: the current database could not be "
                    f"backed up first ({error}).",
                    source_name,
                ),
            )
        finally:
            database.close()
    for suffix in _SIDECAR_SUFFIXES:
        Path(f"{database_path}{suffix}").unlink(missing_ok=True)
    os.replace(layout.pending_file, database_path)
    layout.marker_file.unlink(missing_ok=True)
    message = f"Restored the database from {source_name}."
    if safety_backup is not None:
        message += f" The previous database was kept as {safety_backup.name}."
    return _record_outcome(layout, RestoreOutcome(True, message, source_name, safety_backup))


def _record_outcome(layout: RestoreLayout, outcome: RestoreOutcome) -> RestoreOutcome:
    """Keep the last outcome in a small file, so the page can show it after a restart."""
    record: dict[str, Any] = {
        "applied": outcome.applied,
        "message": outcome.message,
        "source_name": outcome.source_name,
        "safety_backup": outcome.safety_backup.name if outcome.safety_backup else "",
    }
    with suppress(OSError):
        _write_json_atomic(layout.result_file, record)
    return outcome


def _has_table(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _check_migration_history(
    connection: sqlite3.Connection, version: int, migrations: Sequence[Migration]
) -> None:
    """Accept only the histories this build would itself accept (see ``Database.migrate``)."""
    recorded = [
        (int(row[0]), str(row[1]))
        for row in connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        )
    ]
    known = {migration.version: migration.name for migration in migrations}
    foreign = foreign_migration_names()
    for recorded_version, recorded_name in recorded:
        if recorded_version in known:
            continue
        if foreign.get(recorded_version) != recorded_name:
            raise BackupValidationError(
                "The backup records a migration this build does not know. It was not restored."
            )
    expected = [
        (migration.version, migration.name)
        for migration in migrations
        if migration.version <= version
    ]
    active = [item for item in recorded if item[0] in known]
    if active != expected:
        raise BackupValidationError(
            "The backup migration history does not match this build of MTEE. It was not restored."
        )


def _write_json_atomic(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f"{path.name}.tmp"
    temporary.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)
