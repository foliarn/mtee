import sqlite3
from pathlib import Path

import pytest
from tests.integration.test_genre_seed import fixture_library, genre_id

from mtee.domain.genres import GenreError
from mtee.persistence.database import Database
from mtee.persistence.genre_repository import GenreRepository
from mtee.persistence.library_repository import LibraryRepository


def test_initializer_preserves_edited_names_positions_and_aliases(tmp_path: Path) -> None:
    path, _, _ = fixture_library(tmp_path)
    database = Database(path)
    repository = GenreRepository(database)
    identity = genre_id("House")
    database.connection().execute(
        "UPDATE genres SET name='My house',name_key='my house',position=99,revision=1 "
        "WHERE genre_id=?",
        (identity,),
    )
    repository.initialize()
    snapshot = next(item for item in repository.taxonomy_snapshot() if item["genre_id"] == identity)
    assert snapshot["name"] == "My house"
    assert snapshot["position"] == 99
    assert database.connection().execute("SELECT COUNT(*) FROM genre_aliases").fetchone()[0] == 7
    assert database.connection().execute("SELECT COUNT(*) FROM local_tags").fetchone()[0] == 0
    with pytest.raises(sqlite3.IntegrityError):
        database.connection().execute(
            "INSERT INTO genres(genre_id,parent_id,name,name_key) "
            "VALUES('duplicate',NULL,'My house','my house')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.connection().execute(
            "INSERT INTO genres(genre_id,parent_id,name,name_key) "
            "VALUES('duplicate',?,'Deep','deep')",
            (identity,),
        )
    database.close()


def test_batch_family_fallback_and_undo_preserve_unrelated_track(tmp_path: Path) -> None:
    path, _, ids = fixture_library(tmp_path)
    database = Database(path)
    repository = GenreRepository(database)
    house, deep, minimal = (
        genre_id(name) for name in ["House", "House \u203a Deep", "House \u203a Minimal"]
    )
    repository.change_membership(ids[:2], [house], enabled=True)
    operation = repository.change_membership(ids[:2], [deep, minimal], enabled=True)
    assert repository.track_assignments(ids[:1])[ids[0]]["genreIds"] == sorted([deep, minimal])
    repository.change_membership([ids[2]], [house], enabled=True)
    repository.undo(operation)
    data = repository.track_assignments(ids[:3])
    assert all(data[identity]["mteeGenres"] == ["House"] for identity in ids[:3])
    repository.change_membership([ids[0]], [deep], enabled=True)
    repository.change_membership([ids[0]], [deep], enabled=False)
    assert repository.track_assignments(ids[:1])[ids[0]]["mteeGenres"] == ["House"]
    database.close()


def test_revisions_cancellation_and_deleted_tracks_refuse_atomic_write(tmp_path: Path) -> None:
    path, _, ids = fixture_library(tmp_path)
    database = Database(path)
    repository = GenreRepository(database)
    with pytest.raises(GenreError, match="Changed"):
        repository.change_membership(
            ids[:2], [genre_id("House")], enabled=True, expected_revisions={ids[0]: 0, ids[1]: 2}
        )
    assert repository.track_assignments(ids[:1])[ids[0]]["genreIds"] == []
    operation = repository.change_membership(ids[:2], [genre_id("House")], enabled=True)
    database.connection().execute("DELETE FROM tracks WHERE track_id=?", (ids[0],))
    with pytest.raises(GenreError, match=r"Undo conflict|Missing track"):
        repository.undo(operation)
    # Journal and revision marker survive physical track removal.
    assert (
        database.connection()
        .execute("SELECT COUNT(*) FROM genre_operation_items WHERE operation_id=?", (operation,))
        .fetchone()[0]
        == 2
    )
    assert (
        database.connection()
        .execute("SELECT COUNT(*) FROM genre_track_state WHERE track_id=?", (ids[0],))
        .fetchone()[0]
        == 1
    )
    assert repository.track_assignments([ids[1]])[ids[1]]["mteeGenres"] == ["House"]
    database.close()


def test_library_rows_include_local_genres_without_touching_file_genre(tmp_path: Path) -> None:
    path, root, ids = fixture_library(tmp_path)
    database = Database(path)
    repository = GenreRepository(database)
    repository.change_membership([ids[1]], [genre_id("House")], enabled=True)
    library = LibraryRepository(database)
    row = library.tracks_in_folder(root, "house")[0]
    assert row["mteeGenres"] == ["House"]
    assert row["genreFamilies"] == ["House"]
    assert row["genre"] == "File genre"
    assert library.track(ids[1])["mteeGenres"] == ["House"]
    assert library.tracks_by_ids([ids[1]])[0]["mteeGenres"] == ["House"]
    database.close()
