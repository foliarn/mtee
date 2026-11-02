"""Plugin migrations: a history apart from the core, checked and applied per plugin."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from mtee.persistence.database import (
    Database,
    DatabaseError,
    MigrationFailedError,
    UnsupportedMigrationHistoryError,
    discover_migrations,
)

_FIRST = "CREATE TABLE sample_items (id INTEGER PRIMARY KEY, label TEXT NOT NULL);\n"
_SECOND = (
    "ALTER TABLE sample_items ADD COLUMN note TEXT NOT NULL DEFAULT '';\n"
    "INSERT INTO sample_items (id, label) VALUES (1, 'seed');\n"
)
_BROKEN = "CREATE TABLE sample_later (id INTEGER PRIMARY KEY);\nINSERT INTO nowhere VALUES (1);\n"


def _scripts(directory: Path, **scripts: str) -> list:
    """Write ``name=sql`` scripts as ``001_name.sql``... and return their migrations."""
    directory.mkdir(parents=True, exist_ok=True)
    for number, (name, sql) in enumerate(scripts.items(), start=1):
        (directory / f"{number:03d}_{name}.sql").write_text(sql, encoding="utf-8")
    return discover_migrations(directory)


def _tables(database: Database) -> set[str]:
    return {
        str(row["name"])
        for row in database.connection().execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _plugin_rows(database: Database) -> list[tuple[str, int, str]]:
    rows = database.connection().execute(
        "SELECT plugin_id, version, name FROM plugin_migrations ORDER BY plugin_id, version"
    )
    return [(str(row[0]), int(row[1]), str(row[2])) for row in rows]


def _core_history(database: Database) -> list[tuple[int, str]]:
    rows = database.connection().execute(
        "SELECT version, name FROM schema_migrations ORDER BY version"
    )
    return [(int(row[0]), str(row[1])) for row in rows]


@pytest.fixture
def database(tmp_path: Path) -> Database:
    created = Database(tmp_path / "mtee.sqlite3")
    created.migrate()
    return created


def test_the_core_migration_creates_the_plugin_history_table(database: Database) -> None:
    assert "plugin_migrations" in _tables(database)
    assert database.schema_version() == 30
    assert (28, "plugin_migrations") in _core_history(database)
    assert _plugin_rows(database) == []


def test_scripts_apply_on_an_empty_database_and_are_recorded_per_plugin(
    database: Database, tmp_path: Path
) -> None:
    migrations = _scripts(tmp_path / "sample", items=_FIRST, seed=_SECOND)
    core_before = _core_history(database)

    applied = database.migrate_plugin("sample", migrations)

    assert [(m.version, m.name) for m in applied] == [(1, "items"), (2, "seed")]
    assert "sample_items" in _tables(database)
    assert _plugin_rows(database) == [("sample", 1, "items"), ("sample", 2, "seed")]
    assert database.connection().execute("SELECT label FROM sample_items").fetchone()[0] == "seed"
    # The core history and the schema version are not touched by a plugin.
    assert _core_history(database) == core_before
    assert database.schema_version() == 30
    assert database.migrate() == []


def test_a_second_run_applies_nothing_and_writes_no_backup(
    database: Database, tmp_path: Path
) -> None:
    migrations = _scripts(tmp_path / "sample", items=_FIRST)
    database.migrate_plugin("sample", migrations)
    backups = list(tmp_path.glob("*.backup"))

    assert database.migrate_plugin("sample", migrations) == []
    assert list(tmp_path.glob("*.backup")) == backups


def test_a_safety_copy_is_written_before_the_first_pending_script(
    database: Database, tmp_path: Path
) -> None:
    migrations = _scripts(tmp_path / "sample", items=_FIRST)

    database.migrate_plugin("sample", migrations)

    (backup,) = tmp_path.glob("mtee.sqlite3.v30.*.backup")
    with sqlite3.connect(backup) as saved:
        tables = {row[0] for row in saved.execute("SELECT name FROM sqlite_master")}
    assert "plugin_migrations" in tables
    assert "sample_items" not in tables


def test_scripts_apply_on_a_copy_of_a_database_at_the_current_version(
    database: Database, tmp_path: Path
) -> None:
    database.connection().execute(
        "INSERT INTO settings (key, value, updated_at_utc) VALUES "
        "('kept', 'value', '2026-10-29T00:00:00+00:00')"
    )
    database.close()
    copy = tmp_path / "copy.sqlite3"
    shutil.copyfile(database.path, copy)

    reopened = Database(copy)
    assert reopened.migrate() == []
    applied = reopened.migrate_plugin("sample", _scripts(tmp_path / "sample", items=_FIRST))

    assert [m.version for m in applied] == [1]
    assert (
        reopened.connection().execute("SELECT value FROM settings WHERE key = 'kept'").fetchone()[0]
        == "value"
    )
    assert "sample_items" in _tables(reopened)
    reopened.close()


def test_plugins_number_their_scripts_independently(database: Database, tmp_path: Path) -> None:
    first = _scripts(tmp_path / "one", items=_FIRST)
    second = _scripts(tmp_path / "two", things="CREATE TABLE other_things (id INTEGER);\n")

    database.migrate_plugin("sample", first)
    database.migrate_plugin("other", second)

    assert _plugin_rows(database) == [("other", 1, "things"), ("sample", 1, "items")]


def test_a_failing_script_is_rolled_back_and_the_earlier_scripts_stay_recorded(
    database: Database, tmp_path: Path
) -> None:
    migrations = _scripts(tmp_path / "sample", items=_FIRST, broken=_BROKEN, never=_SECOND)

    with pytest.raises(MigrationFailedError, match=r"002_broken.sql"):
        database.migrate_plugin("sample", migrations)

    assert _plugin_rows(database) == [("sample", 1, "items")]
    tables = _tables(database)
    assert "sample_items" in tables
    assert "sample_later" not in tables
    assert database.connection().in_transaction is False
    assert database.schema_version() == 30


def test_a_renamed_script_refuses_the_history_and_changes_nothing(
    database: Database, tmp_path: Path
) -> None:
    database.migrate_plugin("sample", _scripts(tmp_path / "v1", items=_FIRST))
    backups = list(tmp_path.glob("*.backup"))
    renamed = _scripts(tmp_path / "v2", rows=_FIRST, seed=_SECOND)

    with pytest.raises(UnsupportedMigrationHistoryError, match="sample"):
        database.migrate_plugin("sample", renamed)

    assert _plugin_rows(database) == [("sample", 1, "items")]
    assert "sample_items" in _tables(database)
    assert list(tmp_path.glob("*.backup")) == backups


def test_a_database_ahead_of_the_plugin_is_refused(database: Database, tmp_path: Path) -> None:
    database.migrate_plugin("sample", _scripts(tmp_path / "v2", items=_FIRST, seed=_SECOND))
    older = _scripts(tmp_path / "v1", items=_FIRST)

    with pytest.raises(UnsupportedMigrationHistoryError, match="does not ship"):
        database.migrate_plugin("sample", older)

    assert len(_plugin_rows(database)) == 2


def test_a_script_added_before_the_recorded_history_is_refused(
    database: Database, tmp_path: Path
) -> None:
    only_second = tmp_path / "gap"
    only_second.mkdir()
    (only_second / "002_seed.sql").write_text(_FIRST, encoding="utf-8")
    database.migrate_plugin("sample", discover_migrations(only_second))
    (only_second / "001_items.sql").write_text("CREATE TABLE sample_old (id INTEGER);\n")

    with pytest.raises(UnsupportedMigrationHistoryError, match="do not continue"):
        database.migrate_plugin("sample", discover_migrations(only_second))

    assert "sample_old" not in _tables(database)


def test_the_core_ignores_the_rows_of_a_plugin_that_is_absent(
    database: Database, tmp_path: Path
) -> None:
    database.migrate_plugin("sample", _scripts(tmp_path / "sample", items=_FIRST))
    database.close()

    reopened = Database(database.path)

    assert reopened.migrate() == []
    assert _plugin_rows(reopened) == [("sample", 1, "items")]
    # Removing the plugin leaves its table in place.
    assert "sample_items" in _tables(reopened)
    reopened.close()


def test_plugin_scripts_need_the_core_history_table_first(tmp_path: Path) -> None:
    bare = Database(tmp_path / "bare.sqlite3")
    migrations = _scripts(tmp_path / "sample", items=_FIRST)

    with pytest.raises(DatabaseError, match="core migrations"):
        bare.migrate_plugin("sample", migrations)
    bare.close()


def test_scripts_that_are_not_numbered_from_one_are_refused(
    database: Database, tmp_path: Path
) -> None:
    folder = tmp_path / "zero"
    folder.mkdir()
    (folder / "000_items.sql").write_text(_FIRST, encoding="utf-8")

    with pytest.raises(DatabaseError, match="numbered"):
        database.migrate_plugin("sample", discover_migrations(folder))
    with pytest.raises(DatabaseError, match="identifier"):
        database.migrate_plugin("", [])
