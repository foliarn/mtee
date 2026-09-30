"""Migrations: preserved data, transactional rollback and refused schema."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from mtee.persistence.database import (
    Database,
    DatabaseError,
    MigrationFailedError,
    SchemaTooRecentError,
    UnsupportedMigrationHistoryError,
)
from mtee.persistence.settings_repository import SettingsRepository

_SECOND_MIGRATION = """
CREATE TABLE listening_note (
    id    INTEGER PRIMARY KEY,
    note  TEXT NOT NULL
);
"""

_FAILING_MIGRATION = """
CREATE TABLE later_table (id INTEGER PRIMARY KEY);
INSERT INTO settings (key, value) VALUES ('broken', 'missing column');
"""


def _shipped_migrations(destination: Path) -> Path:
    """Copy the initial migration of MTEE into ``destination`` and return it."""
    destination.mkdir(parents=True, exist_ok=True)
    initial = Database(destination / "unused.sqlite3").migrations[0]
    (destination / initial.file_name).write_text(initial.read_sql(), encoding="utf-8")
    return destination


def test_a_new_database_receives_the_initial_schema(tmp_path: Path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")

    applied = database.migrate()

    assert [migration.version for migration in applied] == [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        11,
        12,
        13,
        14,
        15,
        16,
    ]
    assert database.schema_version() == 16
    tables = {
        str(row["name"])
        for row in database.connection().execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "settings",
        "schema_migrations",
        "file_copy_operations",
        "track_analysis",
        "track_waveforms",
    } <= tables
    operation_columns = {
        str(row[1]) for row in database.connection().execute("PRAGMA table_info(file_operations)")
    }
    assert "phase" in operation_columns
    database.close()


def test_metadata_migration_backs_up_an_existing_database(tmp_path: Path) -> None:
    older_migrations = tmp_path / "schema-v3"
    older_migrations.mkdir()
    for migration in Database(tmp_path / "unused.sqlite3").migrations[:4]:
        shutil.copyfile(migration.path, older_migrations / migration.file_name)
    path = tmp_path / "mtee.sqlite3"
    original = Database(path, migrations_dir=older_migrations)
    assert [item.version for item in original.migrate()] == [1, 2, 3, 4]
    SettingsRepository(original).set("workspace/name", "preserved")
    original.close()

    upgraded = Database(path)
    assert [item.version for item in upgraded.migrate()] == [5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16]
    assert SettingsRepository(upgraded).get("workspace/name") == "preserved"
    backups = list(tmp_path.glob("mtee.sqlite3.v4.*.backup"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("PRAGMA user_version").fetchone() == (4,)
        assert backup.execute(
            "SELECT value FROM settings WHERE key='workspace/name'"
        ).fetchone() == ("preserved",)
    upgraded.close()


def test_opening_an_up_to_date_database_applies_nothing(tmp_path: Path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()

    assert database.migrate() == []
    database.close()


def test_a_later_migration_preserves_the_stored_settings(tmp_path: Path) -> None:
    migrations = _shipped_migrations(tmp_path / "migrations")
    path = tmp_path / "mtee.sqlite3"
    first = Database(path, migrations_dir=migrations)
    first.migrate()
    SettingsRepository(first).set("shell/last_status", "Ready")
    first.close()

    (migrations / "002_listening_note.sql").write_text(_SECOND_MIGRATION, encoding="utf-8")
    second = Database(path, migrations_dir=migrations)
    applied = second.migrate()

    assert [migration.version for migration in applied] == [2]
    assert SettingsRepository(second).get("shell/last_status") == "Ready"
    assert second.schema_version() == 2
    second.close()


def test_a_migration_creates_a_backup_before_touching_an_existing_file(tmp_path: Path) -> None:
    migrations = _shipped_migrations(tmp_path / "migrations")
    path = tmp_path / "mtee.sqlite3"
    first = Database(path, migrations_dir=migrations)
    first.migrate()
    SettingsRepository(first).set("kept", "value")
    first.close()

    (migrations / "002_listening_note.sql").write_text(_SECOND_MIGRATION, encoding="utf-8")
    second = Database(path, migrations_dir=migrations)
    second.migrate()
    second.close()

    backups = sorted(tmp_path.glob("mtee.sqlite3.v1.*.backup"))
    assert len(backups) == 1
    saved = sqlite3.connect(backups[0])
    try:
        stored = saved.execute("SELECT value FROM settings WHERE key = 'kept'").fetchone()
    finally:
        saved.close()
    assert stored is not None and stored[0] == "value"


def test_a_failing_migration_leaves_the_previous_content_intact(tmp_path: Path) -> None:
    migrations = _shipped_migrations(tmp_path / "migrations")
    path = tmp_path / "mtee.sqlite3"
    first = Database(path, migrations_dir=migrations)
    first.migrate()
    SettingsRepository(first).set("kept", "value")
    first.close()

    (migrations / "002_broken.sql").write_text(_FAILING_MIGRATION, encoding="utf-8")
    second = Database(path, migrations_dir=migrations)

    with pytest.raises(MigrationFailedError):
        second.migrate()

    assert second.schema_version() == 1
    assert SettingsRepository(second).get("kept") == "value"
    tables = {
        str(row["name"])
        for row in second.connection().execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert "later_table" not in tables
    second.close()


def test_a_schema_written_by_a_newer_build_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "mtee.sqlite3"
    database = Database(path)
    database.migrate()
    database.connection().execute("PRAGMA user_version = 99")

    with pytest.raises(SchemaTooRecentError) as failure:
        database.migrate()

    assert failure.value.found_version == 99
    assert database.schema_version() == 99
    database.close()


def test_a_database_with_the_retired_analysis_migration_is_upgraded_and_preserved(
    tmp_path: Path,
) -> None:
    legacy_migrations = tmp_path / "schema-v10"
    legacy_migrations.mkdir()
    current_migrations = Database(tmp_path / "unused.sqlite3").migrations
    for migration in current_migrations:
        if migration.version <= 9:
            shutil.copyfile(migration.path, legacy_migrations / migration.file_name)
    (legacy_migrations / "010_audio_analysis.sql").write_text(
        "CREATE TABLE analysis_results (result_id TEXT PRIMARY KEY, payload TEXT NOT NULL);",
        encoding="utf-8",
    )
    path = tmp_path / "mtee.sqlite3"
    legacy = Database(path, migrations_dir=legacy_migrations)
    legacy.migrate()
    SettingsRepository(legacy).set("workspace/name", "preserved")
    legacy.connection().execute(
        "INSERT INTO analysis_results(result_id, payload) VALUES('result-1', 'kept')"
    )
    legacy.close()

    upgraded = Database(path)
    assert [migration.version for migration in upgraded.migrate()] == [11, 12, 13, 14, 15, 16]
    assert upgraded.schema_version() == 16
    assert SettingsRepository(upgraded).get("workspace/name") == "preserved"
    assert (
        upgraded.connection()
        .execute("SELECT payload FROM analysis_results WHERE result_id='result-1'")
        .fetchone()[0]
        == "kept"
    )
    assert (
        upgraded.connection()
        .execute("SELECT name FROM schema_migrations WHERE version=10")
        .fetchone()[0]
        == "audio_analysis"
    )
    backups = list(tmp_path.glob("mtee.sqlite3.v10.*.backup"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("PRAGMA user_version").fetchone() == (10,)
        assert backup.execute("SELECT payload FROM analysis_results").fetchone() == ("kept",)
    assert upgraded.migrate() == []
    upgraded.close()


def test_an_unknown_retired_migration_remains_refused(tmp_path: Path) -> None:
    path = tmp_path / "mtee.sqlite3"
    database = Database(path)
    database.migrate()
    database.connection().execute(
        "INSERT INTO schema_migrations(version,name,applied_at_utc) "
        "VALUES(10, ?, '2026-09-25T00:00:00Z')",
        ("unknown_feature",),
    )

    with pytest.raises(UnsupportedMigrationHistoryError, match="unknown or unsupported"):
        database.migrate()
    assert database.schema_version() == 16
    database.close()


def test_a_migration_file_with_an_unexpected_name_is_reported(tmp_path: Path) -> None:
    migrations = _shipped_migrations(tmp_path / "migrations")
    (migrations / "initial.sql").write_text("SELECT 1;", encoding="utf-8")
    database = Database(tmp_path / "mtee.sqlite3", migrations_dir=migrations)

    with pytest.raises(DatabaseError):
        database.migrate()


def test_playlist_upgrade_keeps_v15_data_and_an_exact_backup(tmp_path: Path) -> None:
    old_migrations = tmp_path / "v15"
    old_migrations.mkdir()
    for migration in Database(tmp_path / "unused.sqlite3").migrations:
        if migration.version <= 15:
            shutil.copyfile(migration.path, old_migrations / migration.file_name)
    path = tmp_path / "upgrade.sqlite3"
    original = Database(path, migrations_dir=old_migrations)
    original.migrate()
    original.connection().execute("INSERT INTO tracks VALUES('kept-track')")
    original.connection().execute(
        "INSERT INTO track_locations(path_key,track_id,path,size_bytes,mtime_ns,"
        "status,metadata_json) "
        "VALUES('key','kept-track','fixture.wav',1,1,'readable',?)",
        ('{"unknown-tag":"kept","title":["Song"]}',),
    )
    SettingsRepository(original).set("existing", "unchanged")
    original.close()
    upgraded = Database(path)
    try:
        assert [m.version for m in upgraded.migrate()] == [16]
        assert upgraded.migrate() == []
        assert SettingsRepository(upgraded).get("existing") == "unchanged"
        assert (
            upgraded.connection()
            .execute("SELECT metadata_json FROM track_locations WHERE track_id='kept-track'")
            .fetchone()[0]
            == '{"unknown-tag":"kept","title":["Song"]}'
        )
        with sqlite3.connect(next(tmp_path.glob("upgrade.sqlite3.v15.*.backup"))) as backup:
            assert backup.execute("PRAGMA user_version").fetchone()[0] == 15
            assert backup.execute("SELECT track_id FROM tracks").fetchone()[0] == "kept-track"
            assert not backup.execute(
                "SELECT 1 FROM sqlite_master WHERE name='playlists'"
            ).fetchone()
    finally:
        upgraded.close()
