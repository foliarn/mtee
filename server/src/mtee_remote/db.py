"""SQLite storage: one connection per thread, explicit transactions and migrations."""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from mtee_remote import clock

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_NAME = re.compile(r"^(\d{4})_([A-Za-z0-9_\-]+)\.sql$")


@dataclass
class Transaction:
    """An open write transaction.

    `notify_users` collects the users whose journal changed; the database tells the
    `on_commit` callback about them once the transaction is committed.
    """

    conn: sqlite3.Connection
    notify_users: set[str] = field(default_factory=lambda: set[str]())


class Database:
    """The server database. Use `conn()` to read and `transaction()` to write."""

    def __init__(self, path: Path, backup_dir: Path) -> None:
        self.path = path
        self.backup_dir = backup_dir
        self.migrations_dir = MIGRATIONS_DIR
        self.on_commit: Callable[[set[str]], None] | None = None
        self._local = threading.local()

    def connect(self) -> sqlite3.Connection:
        """Open a new connection. Each thread must use its own."""
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def conn(self) -> sqlite3.Connection:
        """Return this thread's connection, opening it on first use."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = self.connect()
            self._local.conn = conn
        return conn

    def close(self) -> None:
        """Close this thread's connection, if any."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        """Run a block in `BEGIN IMMEDIATE ... COMMIT`; roll back if the block raises."""
        conn = self.conn()
        conn.execute("BEGIN IMMEDIATE")
        tx = Transaction(conn)
        try:
            yield tx
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        try:
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        callback = self.on_commit
        if callback is not None and tx.notify_users:
            try:
                callback(set(tx.notify_users))
            except Exception:
                # The data is committed; a failed wake-up must not look like a failed write.
                log.exception("on_commit callback failed")

    # -- migrations -----------------------------------------------------------------

    def _migration_files(self) -> list[tuple[int, str, Path]]:
        found: list[tuple[int, str, Path]] = []
        for path in sorted(self.migrations_dir.glob("*.sql")):
            match = _MIGRATION_NAME.match(path.name)
            if match is None:
                raise ValueError(f"Migration file name not understood: {path.name}")
            found.append((int(match.group(1)), match.group(2), path))
        versions = [version for version, _, _ in found]
        if len(set(versions)) != len(versions):
            raise ValueError("Two migration files share the same version number.")
        found.sort()
        return found

    def migrate(self) -> list[int]:
        """Apply the pending migrations in order; return the versions applied.

        Before the first pending migration, an existing database (one that already has
        applied migrations) is copied to `backup_dir` with SQLite's online backup.
        """
        conn = self.conn()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, name TEXT, applied_at_utc TEXT)"
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        pending = [m for m in self._migration_files() if m[0] not in applied]
        if not pending:
            return []
        if applied:
            self._backup_before(pending[0][0])
        done: list[int] = []
        for version, name, path in pending:
            sql = path.read_text(encoding="utf-8")
            with self.transaction() as tx:
                for statement in _split_statements(sql):
                    tx.conn.execute(statement)
                tx.conn.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at_utc) VALUES (?,?,?)",
                    (version, name, clock.to_iso(clock.utc_now())),
                )
            done.append(version)
        return done

    def _backup_before(self, version: int) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = clock.utc_now().strftime("%Y%m%dT%H%M%SZ")
        target = self.backup_dir / f"mtee-remote-{stamp}-before-{version:04d}.db"
        if target.exists():
            raise FileExistsError(f"A database backup named {target.name} already exists.")
        dest = sqlite3.connect(target)
        try:
            self.conn().backup(dest)
        finally:
            dest.close()
        return target


def _split_statements(script: str) -> list[str]:
    """Split a SQL script into statements.

    `executescript` is avoided on purpose: it commits the open transaction first, which
    would defeat the all-or-nothing migration.
    """
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip() and not _only_comments(buffer):
        statements.append(buffer.strip())
    return statements


def _only_comments(text: str) -> bool:
    return all(not line.strip() or line.strip().startswith("--") for line in text.splitlines())
