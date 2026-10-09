"""Schema 022 starts from 020 and refuses the retired 021 without data loss."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from mtee.persistence.database import Database, UnsupportedMigrationHistoryError
from mtee.plugins.genre_manager.repository import GenreManagerRepository


def _schema_020(directory: Path) -> Path:
    directory.mkdir()
    for migration in Database(directory / "unused.sqlite3").migrations:
        if migration.version <= 20:
            shutil.copyfile(migration.path, directory / migration.file_name)
    return directory


def test_020_to_022_preserves_library_and_artist_data_with_valid_backup(tmp_path: Path) -> None:
    path = tmp_path / "library.sqlite3"
    old = Database(path, migrations_dir=_schema_020(tmp_path / "old"))
    old.migrate()
    old.connection().execute("INSERT INTO tracks(track_id) VALUES('track-a')")
    old.connection().execute(
        "INSERT INTO artists(artist_id,display_name,name_key,name_origin,state,"
        "created_at_utc,updated_at_utc) VALUES('artist-a','Manual artist','manual artist',"
        "'manual','established','2026-10-09','2026-10-09')"
    )
    old.close()

    upgraded = Database(path)
    assert [migration.version for migration in upgraded.migrate()] == [22]
    assert upgraded.schema_version() == 22
    assert upgraded.connection().execute("SELECT display_name FROM artists").fetchone()[0] == (
        "Manual artist"
    )
    assert GenreManagerRepository(upgraded).tags() == []
    assert upgraded.migrate() == []
    backups = list(tmp_path.glob("library.sqlite3.v20.*.backup"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as saved:
        assert saved.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert saved.execute("PRAGMA user_version").fetchone() == (20,)
        assert saved.execute("SELECT track_id FROM tracks").fetchone() == ("track-a",)
    upgraded.close()


def test_an_old_021_record_is_refused_before_a_backup_or_write(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    legacy_schema = _schema_020(tmp_path / "old")
    (legacy_schema / "021_track_genres.sql").write_text(
        "CREATE TABLE historical_021_marker(value TEXT NOT NULL);", encoding="utf-8"
    )
    legacy = Database(path, migrations_dir=legacy_schema)
    legacy.migrate()
    legacy.connection().execute("INSERT INTO historical_021_marker(value) VALUES('keep this data')")
    legacy.close()
    current = Database(path)
    with pytest.raises(UnsupportedMigrationHistoryError):
        current.migrate()
    assert current.schema_version() == 21
    assert (
        current.connection().execute("SELECT value FROM historical_021_marker").fetchone()[0]
        == "keep this data"
    )
    assert not list(tmp_path.glob("legacy.sqlite3.v21.*.backup"))
    current.close()


def test_backup_refuses_to_replace_an_existing_file(tmp_path: Path) -> None:
    database = Database(tmp_path / "fresh.sqlite3")
    database.migrate()
    destination = tmp_path / "keep.backup"
    destination.write_bytes(b"untouched")
    with pytest.raises(FileExistsError):
        database.backup_to(destination)
    assert destination.read_bytes() == b"untouched"
    database.close()
