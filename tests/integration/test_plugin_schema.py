"""Plugin-owned schema: a new database has no plugin tables, old databases keep their data."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mtee.persistence.database import (
    Database,
    DatabaseError,
    UnsupportedMigrationHistoryError,
    discover_migrations,
)
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.artist_manager.repository import ArtistRepository
from mtee.plugins.genre_manager.repository import GenreManagerRepository
from mtee.plugins.registry import bundled_plugins, plugin_ui_enabled, prepare_plugin_schema

_PLUGIN_PREFIXES = ("artist", "track_artist", "gm_")
_CORE_VERSIONS = [*range(1, 10), *range(11, 19), 24, 25, 26]


def _plugin_dir(plugin_id: str) -> Path:
    return next(item.migrations_dir for item in bundled_plugins() if item.plugin_id == plugin_id)


def _tables(database: Database) -> set[str]:
    return {
        str(row["name"])
        for row in database.connection().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _recorded_versions(database: Database) -> list[int]:
    rows = database.connection().execute("SELECT version FROM schema_migrations ORDER BY version")
    return [int(row[0]) for row in rows]


def _build_legacy_schema(directory: Path) -> Path:
    """Copy every script of the build that still shipped migrations up to 023."""
    directory.mkdir()
    for migration in Database(directory / "unused.sqlite3").migrations:
        if migration.version > 23:
            continue
        shutil.copyfile(migration.path, directory / migration.file_name)
    for plugin_id in ("artist_manager", "genre_manager"):
        for migration in discover_migrations(_plugin_dir(plugin_id)):
            shutil.copyfile(migration.path, directory / migration.file_name)
    return directory


def test_a_new_database_has_no_plugin_tables(tmp_path: Path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()

    assert database.schema_version() == 26
    assert _recorded_versions(database) == _CORE_VERSIONS
    tables = _tables(database)
    assert not {name for name in tables if name.startswith(_PLUGIN_PREFIXES)}
    database.close()


def test_loading_the_plugins_creates_their_tables_once(tmp_path: Path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    database.connection().execute("INSERT INTO tracks(track_id) VALUES('track-a')")

    ArtistRepository(database)
    assert "artists" in _tables(database)
    assert database.schema_version() == 26
    GenreManagerRepository(database)
    assert "gm_genres" in _tables(database)
    assert database.schema_version() == 26
    assert _recorded_versions(database) == sorted([*_CORE_VERSIONS, 19, 20, 22, 23])

    # Nothing is applied twice: a second opening only checks the recorded history.
    prepare_plugin_schema(database, "genre_manager")
    assert database.migrate() == []
    assert _recorded_versions(database) == sorted([*_CORE_VERSIONS, 19, 20, 22, 23])
    # The plugin scripts backed up the file before they changed a non-empty database.
    assert len(list(tmp_path.glob("mtee.sqlite3.v26.*.backup"))) == 2
    database.close()


def test_a_database_built_with_the_plugins_up_to_023_keeps_its_data(tmp_path: Path) -> None:
    legacy = Database(
        tmp_path / "library.sqlite3", migrations_dir=_build_legacy_schema(tmp_path / "legacy")
    )
    assert legacy.migrate()[-1].version == 23
    legacy.connection().execute("INSERT INTO tracks(track_id) VALUES('track-a')")
    legacy.connection().execute(
        "INSERT INTO artists(artist_id,display_name,name_key,name_origin,state,"
        "created_at_utc,updated_at_utc) VALUES('artist-a','Manual artist','manual artist',"
        "'manual','established','2026-10-09','2026-10-09')"
    )
    legacy.connection().execute(
        "INSERT INTO gm_genres(genre_id,parent_id,name,name_key,sort_order,archived,"
        "created_at_utc,updated_at_utc) VALUES('genre-house',NULL,'House','house',0,0,"
        "'2026-10-09','2026-10-09')"
    )
    SettingsRepository(legacy).set("workspace/name", "kept")
    legacy.close()

    upgraded = Database(tmp_path / "library.sqlite3")
    assert upgraded.schema_version() == 23
    assert [migration.version for migration in upgraded.migrate()] == [24, 25, 26]
    assert SettingsRepository(upgraded).get("workspace/name") == "kept"
    assert upgraded.connection().execute("SELECT display_name FROM artists").fetchone()[0] == (
        "Manual artist"
    )
    assert [row["name"] for row in GenreManagerRepository(upgraded).genres()] == ["House"]
    assert upgraded.migrate() == []
    # Only the core upgrade to 24 and 25 backed the file up; the plugins applied nothing.
    assert len(list(tmp_path.glob("library.sqlite3.v23.*.backup"))) == 1
    upgraded.close()


def test_a_plugin_record_with_another_name_is_refused_without_change(tmp_path: Path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    database.connection().execute(
        "INSERT INTO schema_migrations(version,name,applied_at_utc) "
        "VALUES(19,'something_else','2026-10-09T00:00:00+00:00')"
    )
    database.connection().execute("PRAGMA user_version = 19")

    with pytest.raises(UnsupportedMigrationHistoryError):
        database.migrate()
    with pytest.raises(UnsupportedMigrationHistoryError):
        ArtistRepository(database)
    assert database.schema_version() == 19
    assert "artists" not in _tables(database)
    database.close()


def test_a_plugin_script_must_be_registered_before_it_runs(tmp_path: Path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "030_future_plugin.sql").write_text(
        "CREATE TABLE future_plugin (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )

    with pytest.raises(UnsupportedMigrationHistoryError, match="not registered"):
        database.migrate_plugin("artist_manager", discover_migrations(scripts))
    assert "future_plugin" not in _tables(database)
    database.close()


def test_a_plugin_waits_for_the_core_schema(tmp_path: Path) -> None:
    database = Database(tmp_path / "empty.sqlite3")

    with pytest.raises(DatabaseError, match="core schema"):
        ArtistRepository(database)
    assert database.schema_version() == 0
    database.close()


def test_v01_ships_with_the_plugin_switch_off() -> None:
    assert plugin_ui_enabled() is False
    assert [item.plugin_id for item in bundled_plugins()] == ["artist_manager", "genre_manager"]
