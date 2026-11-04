"""Deleting a playlist folder, both ways (plan 132.4, U13), on a temporary database."""

from pathlib import Path

import pytest

from mtee.persistence.database import Database
from mtee.persistence.playlists_repository import PlaylistsRepository


@pytest.fixture
def repository(tmp_path: Path):
    database = Database(tmp_path / "playlists.sqlite3")
    database.migrate()
    yield PlaylistsRepository(database)
    database.close()


def _folder_names(repository: PlaylistsRepository, parent: str) -> list[str]:
    return [f["name"] for f in repository.folders() if (f["parent_id"] or "") == parent]


def _playlist_names(repository: PlaylistsRepository, folder: str) -> list[str]:
    return [p["name"] for p in repository.playlists() if (p["folder_id"] or "") == folder]


def test_keep_contents_moves_subfolders_and_playlists_up_in_order(repository) -> None:
    top = repository.create_folder("Top")
    before = repository.create_folder("Before")
    middle = repository.create_folder("Middle", top)
    first_child = repository.create_folder("First", middle)
    second_child = repository.create_folder("Second", middle)
    repository.create_folder("After")
    repository.create("Lonely", top)
    repository.create("Inside one", middle)
    repository.create("Inside two", middle)
    deleted = repository.delete_folder(middle, keep_contents=True)

    assert deleted == []
    assert middle not in {f["folder_id"] for f in repository.folders()}
    # The subfolders take the place of the folder among its siblings, in their order.
    assert _folder_names(repository, top) == ["First", "Second"]
    assert _folder_names(repository, "") == ["Top", "Before", "After"]
    assert {f["folder_id"] for f in repository.folders() if f["name"] == "First"} == {first_child}
    assert {f["folder_id"] for f in repository.folders() if f["name"] == "Second"} == {second_child}
    # The playlists of the folder move up one level, and keep their relative order.
    assert _playlist_names(repository, top) == ["Lonely", "Inside one", "Inside two"]
    assert _playlist_names(repository, middle) == []
    assert before in {f["folder_id"] for f in repository.folders()}


def test_keep_contents_at_the_root_keeps_playlists_at_the_root(repository) -> None:
    folder = repository.create_folder("Solo")
    repository.create("Kept", folder)
    repository.create_folder("Child", folder)
    assert repository.delete_folder(folder, keep_contents=True) == []
    assert _playlist_names(repository, "") == ["Kept"]
    assert _folder_names(repository, "") == ["Child"]


def test_delete_everything_removes_nested_folders_and_their_playlists(repository) -> None:
    top = repository.create_folder("Top")
    nested = repository.create_folder("Nested", top)
    deeper = repository.create_folder("Deeper", nested)
    keep = repository.create("Outside", "")
    inside_top = repository.create("Inside top", top)
    inside_nested = repository.create("Inside nested", nested)
    inside_deeper = repository.create("Inside deeper", deeper)

    deleted = repository.delete_folder(top, keep_contents=False)

    assert sorted(deleted) == sorted([inside_top, inside_nested, inside_deeper])
    assert repository.folders() == []
    assert [p["playlist_id"] for p in repository.playlists()] == [keep]


def test_delete_everything_of_an_empty_folder_deletes_nothing_else(repository) -> None:
    empty = repository.create_folder("Empty")
    keep = repository.create("Kept", "")
    assert repository.delete_folder(empty, keep_contents=False) == []
    assert [p["playlist_id"] for p in repository.playlists()] == [keep]


def test_a_missing_folder_is_refused(repository) -> None:
    with pytest.raises(LookupError):
        repository.delete_folder("no-such-folder", keep_contents=True)
