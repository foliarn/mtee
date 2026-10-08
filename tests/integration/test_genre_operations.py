import sqlite3

import pytest
from tests.integration.test_genre_seed import fixture_library, genre_id

from mtee.domain.genres import GenreError
from mtee.persistence.database import Database
from mtee.persistence.genre_manager_repository import GenreManagerRepository


def repository(tmp_path):
    path, _root, ids = fixture_library(tmp_path)
    return GenreManagerRepository(Database(path)), ids


def test_catalog_move_rename_alias_archive_and_targeted_undo(tmp_path):
    repo, ids = repository(tmp_path)
    deep = genre_id("House \u203a Deep")
    house = genre_id("House")
    dub = genre_id("Dubstep")
    repo.change_membership([ids[0]], [deep], enabled=True)
    op = repo.edit(
        "genre", "edit", deep, {"name": "Depth", "aliases": ["Deep house"], "parent_id": dub}, 0
    )
    assert repo.track_assignments(ids)[ids[0]]["mteeGenres"] == ["Dubstep \u203a Depth"]
    unrelated = repo.edit("genre", "create", "", {"name": "New root"})
    repo.undo_any(op["operation"])
    assert repo.track_assignments(ids)[ids[0]]["mteeGenres"] == ["House \u203a Deep"]
    assert unrelated["identity"] in repo.taxonomy_from(repo.database.connection()).nodes
    op = repo.edit("genre", "edit", house, {"archived": True}, 0)
    with pytest.raises(GenreError, match="Archived"):
        repo.change_membership([ids[1]], [deep], enabled=True)
    repo.undo_any(op["operation"])
    assert all(n["genre_id"] != deep or n["assignable"] for n in repo.catalog()["genres"])
    repo.database.close()


def test_cycles_duplicates_conflicts_and_delete_refusal(tmp_path):
    repo, _ids = repository(tmp_path)
    house = genre_id("House")
    deep = genre_id("House \u203a Deep")
    with pytest.raises(GenreError, match="cycle"):
        repo.edit("genre", "edit", house, {"parent_id": deep}, 0)
    with pytest.raises(GenreError, match="duplicate"):
        repo.edit("genre", "create", "", {"name": " DEEP ", "parent_id": house})
    with pytest.raises(GenreError, match="children"):
        repo.edit("genre", "delete", house, {}, 0)
    op = repo.edit("genre", "edit", deep, {"name": "Depth"}, 0)
    repo.edit("genre", "edit", deep, {"name": "Depths"}, 1)
    with pytest.raises(GenreError, match="conflict"):
        repo.undo_any(op["operation"])
    assert repo.taxonomy_from(repo.database.connection()).path(deep) == "House \u203a Depths"
    repo.database.close()


def test_force_delete_backup_and_complete_targeted_recovery(tmp_path):
    repo, ids = repository(tmp_path)
    house = genre_id("House")
    deep = genre_id("House \u203a Deep")
    bass = genre_id("House \u203a Bass")
    repo.change_membership(ids[:2], [deep, bass], enabled=True)
    repo.change_membership([ids[2]], [genre_id("Rap")], enabled=True)
    before = repo.track_assignments(ids)
    operation = repo.edit("genre", "force_delete", house, {"confirmation": house}, 0)
    with sqlite3.connect(operation["backup"]) as backup:
        assert backup.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert repo.track_assignments(ids)[ids[0]]["genreIds"] == []
    repo.undo_any(operation["operation"])
    after = repo.track_assignments(ids)
    assert after[ids[0]]["genreIds"] == before[ids[0]]["genreIds"]
    assert after[ids[2]] == before[ids[2]]
    assert len(repo.catalog()["genres"]) == 48
    repo.database.close()


def test_local_tags_and_meta_families_remain_distinct_and_reversible(tmp_path):
    repo, ids = repository(tmp_path)
    tag = repo.edit("tag", "create", "", {"name": "Warm", "color": "#abcd12"})
    meta = repo.edit("meta", "create", "", {"name": "Dance nights", "members": [genre_id("House")]})
    op = repo.change_tags(ids[:2], tag["identity"], True, {ids[0]: 0, ids[1]: 0})
    assert repo.track_assignments(ids)[ids[0]]["localTags"] == ["Warm"]
    assert repo.track_assignments(ids)[ids[0]]["genreIds"] == []
    with pytest.raises(GenreError, match="assignments"):
        repo.edit("tag", "delete", tag["identity"], {}, 0)
    repo.undo_any(op)
    assert repo.track_assignments(ids)[ids[0]]["localTags"] == []
    repo.undo_any(meta["operation"])
    assert meta["identity"] not in [m["meta_id"] for m in repo.catalog()["metas"]]
    repo.database.close()


def test_successive_overlapping_undos_follow_journal_revisions(tmp_path, monkeypatch):
    # Fast transactions may share a timestamp; insertion order must remain authoritative.
    monkeypatch.setattr(
        "mtee.persistence.genre_repository.utc_now", lambda: "2026-10-08T00:00:00+00:00"
    )
    repo, ids = repository(tmp_path)
    deep = genre_id("House \u203a Deep")
    minimal = genre_id("House \u203a Minimal")
    first = repo.change_membership([ids[0]], [deep], enabled=True)
    second = repo.change_membership([ids[0]], [minimal], enabled=True)
    repo.undo_any(second)
    assert repo.track_assignments(ids)[ids[0]]["genreIds"] == [deep]
    repo.undo_any(first)
    assert repo.track_assignments(ids)[ids[0]]["genreIds"] == []
    renamed = repo.edit("genre", "edit", deep, {"name": "Depth"}, 0)
    reordered = repo.edit("genre", "edit", deep, {"position": 10}, 1)
    repo.undo_any(reordered["operation"])
    repo.undo_any(renamed["operation"])
    assert repo.taxonomy_from(repo.database.connection()).path(deep) == "House \u203a Deep"
    repo.database.close()


def test_catalog_cancellation_and_stale_tag_revision_are_atomic(tmp_path):
    repo, ids = repository(tmp_path)
    house = genre_id("House")

    def cancel():
        raise RuntimeError("Cancelled")

    with pytest.raises(RuntimeError, match="Cancelled"):
        repo.edit("genre", "edit", house, {"name": "Changed"}, 0, cancel)
    assert repo.taxonomy_from(repo.database.connection()).path(house) == "House"
    tag = repo.edit("tag", "create", "", {"name": "Warm"})["identity"]
    repo.change_membership([ids[1]], [house], enabled=True)
    with pytest.raises(GenreError, match="Changed track"):
        repo.change_tags(ids[:2], tag, True, {ids[0]: 0, ids[1]: 0})
    assert all(not row["localTags"] for row in repo.track_assignments(ids).values())
    repo.database.close()
