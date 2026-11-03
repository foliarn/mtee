from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from mtee_remote import clock
from mtee_remote.db import MIGRATIONS_DIR, Database

EXPECTED_TABLES = {
    "users",
    "devices",
    "roots",
    "items",
    "item_revisions",
    "journal",
    "device_cursors",
    "uploads",
    "trash",
    "backups",
    "server_settings",
    "user_settings",
    "schema_migrations",
}


def _tables(db: Database) -> set[str]:
    rows = db.conn().execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def _new_db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db", tmp_path / "backups")


def test_migrate_empty_database(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    assert db.migrate() == [1, 2]
    assert _tables(db) >= EXPECTED_TABLES
    assert "folders" not in _tables(db)
    row = (
        db.conn().execute("SELECT version, name, applied_at_utc FROM schema_migrations").fetchone()
    )
    assert (row["version"], row["name"]) == (1, "initial")
    assert row["applied_at_utc"].endswith("Z")
    db.close()


def test_connection_settings(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    db.migrate()
    conn = db.conn()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert conn.row_factory is sqlite3.Row
    assert conn.isolation_level is None
    assert db.conn() is conn
    db.close()


def test_reopen_and_second_migrate_do_nothing(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    db.migrate()
    db.close()
    again = _new_db(tmp_path)
    assert again.migrate() == []
    count = again.conn().execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert count == 2
    assert not (tmp_path / "backups").exists()
    again.close()


def test_new_migration_makes_a_backup_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _new_db(tmp_path)
    db.migrate()
    with db.transaction() as tx:
        tx.conn.execute("INSERT INTO server_settings(key, value_json) VALUES ('k', '1')")
    assert not list((tmp_path / "backups").glob("*.db"))

    extra = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, extra, ignore=shutil.ignore_patterns("__pycache__"))
    (extra / "0003_add_note.sql").write_text(
        "ALTER TABLE users ADD COLUMN note TEXT;\n", encoding="utf-8"
    )
    db.migrations_dir = extra
    monkeypatch.setattr(clock, "utc_now", clock.utc_now)  # keep the real clock explicit
    assert db.migrate() == [3]

    backups = list((tmp_path / "backups").glob("mtee-remote-*-before-0003.db"))
    assert len(backups) == 1
    copy = sqlite3.connect(backups[0])
    try:
        assert copy.execute("SELECT value_json FROM server_settings").fetchone()[0] == "1"
        columns = [row[1] for row in copy.execute("PRAGMA table_info(users)")]
        assert "note" not in columns  # the backup holds the state before the migration
    finally:
        copy.close()
    assert "note" in [row[1] for row in db.conn().execute("PRAGMA table_info(users)")]
    db.close()


def test_failed_migration_rolls_back(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    db.migrate()
    extra = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, extra, ignore=shutil.ignore_patterns("__pycache__"))
    (extra / "0003_broken.sql").write_text(
        "CREATE TABLE half_done (x INTEGER);\nINSERT INTO missing_table VALUES (1);\n",
        encoding="utf-8",
    )
    db.migrations_dir = extra
    with pytest.raises(sqlite3.OperationalError):
        db.migrate()
    assert "half_done" not in _tables(db)
    versions = [row[0] for row in db.conn().execute("SELECT version FROM schema_migrations")]
    assert versions == [1, 2]
    db.close()


def test_transaction_commits_and_rolls_back(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    db.migrate()
    with db.transaction() as tx:
        tx.conn.execute("INSERT INTO server_settings(key, value_json) VALUES ('a', '1')")
    with pytest.raises(RuntimeError), db.transaction() as tx:
        tx.conn.execute("INSERT INTO server_settings(key, value_json) VALUES ('b', '2')")
        raise RuntimeError("boom")
    keys = [row[0] for row in db.conn().execute("SELECT key FROM server_settings")]
    assert keys == ["a"]
    assert not db.conn().in_transaction
    db.close()


def test_on_commit_runs_after_commit_only(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    db.migrate()
    seen: list[tuple[set[str], int]] = []

    def on_commit(users: set[str]) -> None:
        # By now the write must be visible to a fresh connection.
        other = db.connect()
        try:
            count = other.execute("SELECT COUNT(*) FROM server_settings").fetchone()[0]
        finally:
            other.close()
        seen.append((users, count))

    db.on_commit = on_commit
    with db.transaction() as tx:  # nobody to notify: no call
        tx.conn.execute("INSERT INTO server_settings(key, value_json) VALUES ('a', '1')")
    assert seen == []
    with db.transaction() as tx:
        tx.conn.execute("INSERT INTO server_settings(key, value_json) VALUES ('b', '2')")
        tx.notify_users.add("u1")
    assert seen == [({"u1"}, 2)]
    with pytest.raises(RuntimeError), db.transaction() as tx:
        tx.notify_users.add("u2")
        raise RuntimeError("boom")
    assert len(seen) == 1
    db.close()


def test_connections_are_per_thread(tmp_path: Path) -> None:
    import threading

    db = _new_db(tmp_path)
    db.migrate()
    main_conn = db.conn()
    other: list[sqlite3.Connection] = []
    thread = threading.Thread(target=lambda: other.append(db.conn()))
    thread.start()
    thread.join()
    assert other[0] is not main_conn
    db.close()


def test_deleting_a_user_cascades(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    db.migrate()
    now = clock.to_iso(clock.utc_now())
    with db.transaction() as tx:
        tx.conn.execute("INSERT INTO users VALUES ('u','alice','!',0,0,NULL,'alice',?)", (now,))
        tx.conn.execute(
            "INSERT INTO devices(device_id,user_id,name,kind,token_hash,created_at_utc)"
            " VALUES ('d','u','n','desktop','h',?)",
            (now,),
        )
        tx.conn.execute("INSERT INTO device_cursors VALUES ('d', 3)")
        tx.conn.execute("INSERT INTO journal VALUES ('u',1,NULL,'added','{}',?)", (now,))
    with db.transaction() as tx:
        tx.conn.execute("DELETE FROM users WHERE user_id = 'u'")
    for table in ("devices", "device_cursors", "journal"):
        assert db.conn().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    db.close()


def test_usernames_are_unique_ignoring_case(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    db.migrate()
    now = clock.to_iso(clock.utc_now())
    with db.transaction() as tx:
        tx.conn.execute("INSERT INTO users VALUES ('u1','Alice','!',0,0,NULL,'a',?)", (now,))
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as tx:
        tx.conn.execute("INSERT INTO users VALUES ('u2','alice','!',0,0,NULL,'b',?)", (now,))
    db.close()
