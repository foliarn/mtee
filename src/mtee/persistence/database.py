"""SQLite access, migrations and backups.

The database is opened with one connection per thread. Every migration runs
inside a transaction, after a consistent backup of the existing file, and a
schema newer than this build is refused instead of being silently recreated.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "MIGRATIONS_DIR",
    "Database",
    "DatabaseError",
    "Migration",
    "MigrationFailedError",
    "SchemaTooRecentError",
    "UnsupportedMigrationHistoryError",
]

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_MIGRATION_NAME = re.compile(r"^(\d{3})_([A-Za-z0-9_\-]+)\.sql$")
_RETIRED_MIGRATIONS = {10: "audio_analysis"}


class DatabaseError(RuntimeError):
    """Base error of the persistence layer."""


class SchemaTooRecentError(DatabaseError):
    """Raised when the file was written by a newer build of MTEE."""

    def __init__(self, found_version: int, supported_version: int) -> None:
        super().__init__(
            f"This database uses schema version {found_version}; this build of MTEE "
            f"supports version {supported_version}. Update MTEE to open it."
        )
        self.found_version = found_version
        self.supported_version = supported_version


class UnsupportedMigrationHistoryError(DatabaseError):
    """Raised when recorded migrations are missing or unknown to this build."""


class MigrationFailedError(DatabaseError):
    """Raised when a migration could not be applied; the file stays unchanged."""

    def __init__(self, migration: Migration, cause: Exception) -> None:
        super().__init__(f"Migration {migration.file_name} failed: {cause}")
        self.migration = migration
        self.cause = cause


@dataclass(frozen=True, slots=True, order=True)
class Migration:
    """One numbered migration script."""

    version: int
    name: str
    path: Path

    @property
    def file_name(self) -> str:
        return self.path.name

    def read_sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover_migrations(directory: Path) -> list[Migration]:
    """Return the migrations of ``directory``, ordered by version.

    A file whose name does not follow ``NNN_name.sql`` is rejected rather than
    ignored, so a mistyped migration never disappears silently.
    """
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        matched = _MIGRATION_NAME.match(path.name)
        if matched is None:
            raise DatabaseError(f"Migration file name not understood: {path.name}")
        migrations.append(Migration(int(matched.group(1)), matched.group(2), path))
    versions = [migration.version for migration in migrations]
    if len(set(versions)) != len(versions):
        raise DatabaseError(f"Duplicated migration version in {directory}")
    return migrations


class Database:
    """Owns the SQLite file of one MTEE installation."""

    def __init__(self, path: Path | str, *, migrations_dir: Path | None = None) -> None:
        self._path = Path(path)
        self._migrations_dir = migrations_dir or MIGRATIONS_DIR
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._connections_lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def migrations(self) -> list[Migration]:
        """Return the migrations shipped with this build."""
        return discover_migrations(self._migrations_dir)

    @property
    def supported_version(self) -> int:
        """Return the highest schema version this build knows."""
        migrations = self.migrations
        return migrations[-1].version if migrations else 0

    def connection(self) -> sqlite3.Connection:
        """Return the connection of the current thread, creating it if needed."""
        existing: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if existing is not None:
            return existing
        self._path.parent.mkdir(parents=True, exist_ok=True)
        created = sqlite3.connect(self._path, isolation_level=None, check_same_thread=False)
        created.row_factory = sqlite3.Row
        created.execute("PRAGMA journal_mode = WAL")
        created.execute("PRAGMA foreign_keys = ON")
        created.execute("PRAGMA busy_timeout = 5000")
        self._local.connection = created
        with self._connections_lock:
            self._connections.append(created)
        return created

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block inside one transaction, rolled back on any failure."""
        connection = self.connection()
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        else:
            connection.execute("COMMIT")

    def schema_version(self) -> int:
        """Return the schema version recorded in the file."""
        row = self.connection().execute("PRAGMA user_version").fetchone()
        return int(row[0]) if row is not None else 0

    def backup_to(self, destination: Path) -> Path:
        """Write and verify a consistent copy, refusing to replace an older backup."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb"):
            pass
        try:
            target = sqlite3.connect(destination)
            try:
                self.connection().backup(target)
            finally:
                target.close()
            saved = sqlite3.connect(f"{destination.resolve().as_uri()}?mode=ro", uri=True)
            try:
                integrity = saved.execute("PRAGMA integrity_check").fetchone()
                if integrity is None or integrity[0] != "ok":
                    raise DatabaseError(f"Backup failed integrity check: {destination}")
            finally:
                saved.close()
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return destination

    def migrate(self) -> list[Migration]:
        """Apply the pending migrations and return those actually applied.

        The file is backed up before the first migration of an existing
        database. A failing migration is rolled back and re-raised; the previous
        content stays intact.
        """
        migrations = self.migrations
        supported = migrations[-1].version if migrations else 0
        current = self.schema_version()
        if current > supported:
            raise SchemaTooRecentError(current, supported)
        if current > 0:
            self._validate_migration_history(current, migrations)
        pending = [migration for migration in migrations if migration.version > current]
        if not pending:
            return []
        if current > 0:
            self.backup_to(self.backup_path_for(current))
        applied: list[Migration] = []
        for migration in pending:
            self._apply(migration)
            applied.append(migration)
        return applied

    def _validate_migration_history(self, current: int, migrations: Sequence[Migration]) -> None:
        """Refuse a schema whose applied versions/names do not match this build."""
        connection = self.connection()
        tables = {
            str(row["name"])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "schema_migrations" not in tables:
            raise UnsupportedMigrationHistoryError(
                "The database has a schema version but no migration history. It was left unchanged."
            )
        recorded = [
            (int(row["version"]), str(row["name"]))
            for row in connection.execute(
                "SELECT version, name FROM schema_migrations ORDER BY version"
            )
        ]
        known = {migration.version: migration.name for migration in migrations}
        retired = [(version, name) for version, name in recorded if version not in known]
        if any(_RETIRED_MIGRATIONS.get(version) != name for version, name in retired):
            raise UnsupportedMigrationHistoryError(
                "The database records an unknown or unsupported migration. "
                "The database was left unchanged."
            )
        if current < 10 and retired:
            raise UnsupportedMigrationHistoryError(
                "The database migration history is ahead of its recorded schema version. "
                "The database was left unchanged."
            )
        if current == 10 and (10, _RETIRED_MIGRATIONS[10]) not in retired:
            raise UnsupportedMigrationHistoryError(
                "Schema version 10 is missing its audio_analysis migration record. "
                "The database was left unchanged."
            )
        # Migration 010 only added analysis tables. Keep its history and data in
        # place while later migrations advance the active application schema.
        # Filtering only this exact retired record keeps unknown histories strict.
        active_recorded = [item for item in recorded if item[0] in known]
        expected = [
            (migration.version, migration.name)
            for migration in migrations
            if migration.version <= current
        ]
        if active_recorded != expected:
            raise UnsupportedMigrationHistoryError(
                "The database migration history does not match the migrations shipped with "
                "this build. The database was left unchanged."
            )

    def backup_path_for(self, version: int) -> Path:
        """Return where the safety copy of schema ``version`` is written."""
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return self._path.with_name(f"{self._path.name}.v{version}.{stamp}.backup")

    def close(self) -> None:
        """Close every connection opened by this instance."""
        with self._connections_lock:
            connections = list(self._connections)
            self._connections.clear()
        for connection in connections:
            connection.close()
        self._local = threading.local()

    def _apply(self, migration: Migration) -> None:
        connection = self.connection()
        statements = list(split_statements(migration.read_sql()))
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version, name, applied_at_utc) VALUES (?, ?, ?)",
                (migration.version, migration.name, _utc_now()),
            )
            connection.execute(f"PRAGMA user_version = {migration.version:d}")
        except Exception as error:
            connection.execute("ROLLBACK")
            raise MigrationFailedError(migration, error) from error
        else:
            connection.execute("COMMIT")


def split_statements(sql: str) -> Iterator[str]:
    """Yield the complete statements of ``sql``.

    ``executescript`` would commit the surrounding transaction, so the script is
    split with ``sqlite3.complete_statement`` and replayed statement by
    statement inside the transaction of the migration.
    """
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement:
                yield statement
    if buffer.strip():
        raise DatabaseError("The migration ends with an incomplete statement.")


def _utc_now() -> str:
    """Return the current UTC instant in ISO 8601, used by the stored rows."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def open_database(path: Path | str, *, migrations_dir: Path | None = None) -> Database:
    """Open ``path``, apply the pending migrations and return the database."""
    database = Database(path, migrations_dir=migrations_dir)
    database.migrate()
    return database


def applied_versions(migrations: Sequence[Migration]) -> list[int]:
    """Return the versions of ``migrations``, for reports and tests."""
    return [migration.version for migration in migrations]
