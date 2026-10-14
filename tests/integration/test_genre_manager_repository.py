"""Genre Manager decisions persist without touching track metadata."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from mtee.persistence.database import Database
from mtee.plugins.genre_manager.repository import GenreManagerRepository, StaleDecisionError
from mtee.plugins.genre_manager.service import GenreManagerService


@pytest.fixture
def module(
    tmp_path: Path,
) -> Iterator[tuple[Database, GenreManagerRepository, GenreManagerService]]:
    database = Database(tmp_path / "genre.sqlite3")
    database.migrate()
    database.connection().execute("INSERT INTO tracks(track_id) VALUES('track-a')")
    repository = GenreManagerRepository(database)
    service = GenreManagerService(repository)
    service.ensure_catalogue()
    yield database, repository, service
    database.close()


def _genre(repository: GenreManagerRepository, name: str) -> str:
    return next(row["genre_id"] for row in repository.genres() if row["name"] == name)


def test_catalogue_is_idempotent_and_tags_start_empty(
    module: tuple[Database, GenreManagerRepository, GenreManagerService],
) -> None:
    _database, repository, service = module
    assert len(repository.genres()) >= 29
    assert repository.tags() == []
    service.ensure_catalogue()
    assert len(repository.genres()) >= 29


def test_genre_revision_review_and_tag_revision_are_separate(
    module: tuple[Database, GenreManagerRepository, GenreManagerService],
) -> None:
    database, repository, service = module
    deep = _genre(repository, "Deep House")
    minimal = _genre(repository, "Minimal House")
    first = service.assign_genre("track-a", deep, expected_revision=0, operation_id="add-deep")
    assert first["genres"] == [deep]
    assert first["genre_revision"] == 1
    assert not first["reviewed"]
    reviewed = repository.mark_reviewed("track-a", expected_revision=1, operation_id="review")
    assert reviewed["reviewed"]
    tag = repository.create_tag("banger")
    tagged = repository.set_tag(
        "track-a", tag, present=True, expected_revision=0, operation_id="add-tag"
    )
    assert tagged["reviewed"] and tagged["tag_revision"] == 1
    changed = service.assign_genre(
        "track-a", minimal, expected_revision=1, operation_id="add-minimal"
    )
    assert changed["genres"] == [deep, minimal]
    assert not changed["reviewed"]
    assert (
        repository.set_tag(
            "track-a", tag, present=True, expected_revision=1, operation_id="retry-tag"
        )["tag_revision"]
        == 1
    )
    assert (
        database.connection()
        .execute("SELECT COUNT(*) FROM gm_track_tags WHERE track_id='track-a'")
        .fetchone()[0]
        == 1
    )


def test_retry_is_idempotent_and_stale_revision_is_refused(
    module: tuple[Database, GenreManagerRepository, GenreManagerService],
) -> None:
    _database, repository, service = module
    deep = _genre(repository, "Deep House")
    first = service.assign_genre("track-a", deep, expected_revision=0, operation_id="same")
    repeated = service.assign_genre("track-a", deep, expected_revision=0, operation_id="same")
    assert repeated == first
    with pytest.raises(StaleDecisionError):
        service.assign_genre("track-a", _genre(repository, "Techno"), expected_revision=0)
    assert repository.track("track-a") == first


def test_folder_name_has_no_automatic_effect(
    module: tuple[Database, GenreManagerRepository, GenreManagerService],
) -> None:
    _database, repository, service = module
    assert repository.track("track-a")["genres"] == []
    house = _genre(repository, "House")
    assert service.assign_folder_genre(["track-a"], house)[0]["genres"] == [house]
    assert not repository.track("track-a")["reviewed"]


def test_undo_restores_only_the_target_decision(
    module: tuple[Database, GenreManagerRepository, GenreManagerService],
) -> None:
    _database, repository, service = module
    deep = _genre(repository, "Deep House")
    tag = repository.create_tag("Night")
    service.assign_genre("track-a", deep, expected_revision=0, operation_id="genre-op")
    repository.set_tag("track-a", tag, present=True, expected_revision=0, operation_id="tag-op")
    undone = repository.undo("genre-op")
    assert undone["genres"] == []
    assert undone["tags"] == [tag]
    assert undone["genre_revision"] == 2
    assert repository.undo("genre-op") == undone
    assert repository.undo("tag-op")["tags"] == []


def test_undo_refuses_a_newer_genre_decision(
    module: tuple[Database, GenreManagerRepository, GenreManagerService],
) -> None:
    _database, repository, service = module
    deep = _genre(repository, "Deep House")
    minimal = _genre(repository, "Minimal House")
    service.assign_genre("track-a", deep, expected_revision=0, operation_id="first")
    service.assign_genre("track-a", minimal, expected_revision=1, operation_id="second")
    with pytest.raises(StaleDecisionError):
        repository.undo("first")
    assert repository.track("track-a")["genres"] == [deep, minimal]


def test_archiving_a_branch_keeps_existing_assignments_but_blocks_new_ones(
    module: tuple[Database, GenreManagerRepository, GenreManagerService],
) -> None:
    database, repository, service = module
    house = _genre(repository, "House")
    deep = _genre(repository, "Deep House")
    service.assign_genre("track-a", deep, expected_revision=0)
    repository.set_genre_archived(house, True)
    assert repository.track("track-a")["genres"] == [deep]
    assert next(item for item in repository.genres() if item["genre_id"] == deep)["archived"]
    database.connection().execute("INSERT INTO tracks(track_id) VALUES('track-b')")
    with pytest.raises(ValueError, match="Archived genres"):
        repository.set_genres(
            "track-b", [deep], expected_revision=0, operation_id="archive-refused"
        )
    repository.set_genre_archived(house, False)
    assert not next(item for item in repository.genres() if item["genre_id"] == deep)["archived"]
