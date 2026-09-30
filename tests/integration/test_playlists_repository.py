from pathlib import Path

import pytest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.services.playlist_service import AmbiguousPlaylistAddError, PlaylistService


@pytest.fixture
def collection(tmp_path: Path):
    database = Database(tmp_path / "test.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(tmp_path / "audio")
    generation = library.begin_scan(root["id"])
    ids = []
    for index, (title, artist) in enumerate(
        [
            ("Écho (Original Mix)", "Alice"),
            ("echo (original mix)", "ALICE"),
            ("Écho (Remix)", "Alice"),
            ("No credit", ""),
        ]
    ):
        path = tmp_path / "audio" / f"{index}.wav"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"source unchanged" + bytes([index]))
        ids.append(
            library.upsert_location(
                root["id"],
                path.name,
                path,
                SourceRevision.observe(path),
                MetadataSnapshot(
                    title=(title,),
                    artist=(artist,) if artist else (),
                    technical=TechnicalInfo(duration_us=4_000_000),
                ),
                generation,
            )
        )
    library.finish_scan(root["id"], generation, complete=True)
    repository = PlaylistsRepository(database)
    yield database, library, repository, PlaylistService(repository, library), ids
    database.close()


def test_music_duplicates_versions_likes_and_reopen(collection) -> None:
    database, _library, repository, service, ids = collection
    playlist = repository.create("Road")
    assert service.add(playlist, ids[:3]) == 2
    assert [r["trackId"] for r in service.rows(playlist)] == [ids[0], ids[2]]
    with pytest.raises(AmbiguousPlaylistAddError):
        service.add(playlist, [ids[3]])
    assert len(repository.entries(playlist)) == 2
    service.add(playlist, [ids[3]], confirm_unknown=True)
    repository.like(ids[0], True)
    repository.like(ids[0], True)
    assert repository.liked_ids() == [ids[0]]
    assert service.liked_aliases() == sorted(ids[:2])
    assert service.rows("liked")[0]["trackId"] == ids[0]
    reopened = Database(database.path)
    try:
        assert len(PlaylistsRepository(reopened).entries(playlist)) == 3
        assert PlaylistsRepository(reopened).liked_ids() == [ids[0]]
    finally:
        reopened.close()


def test_reorder_is_atomic_and_rejects_a_stale_version(collection) -> None:
    _database, _library, repository, service, ids = collection
    playlist = repository.create("Order")
    service.add(playlist, [ids[0], ids[2]])
    entries = [e["entry_id"] for e in repository.entries(playlist)]
    version = repository.playlist(playlist)["version"]
    repository.reorder(playlist, entries[::-1], version)
    assert [e["entry_id"] for e in repository.entries(playlist)] == entries[::-1]
    with pytest.raises(ValueError):
        repository.reorder(playlist, entries, version)
    with pytest.raises(ValueError):
        repository.reorder(playlist, [entries[0], entries[0]], version + 1)
    assert [e["entry_id"] for e in repository.entries(playlist)] == entries[::-1]


def test_folder_cycles_deletion_copy_and_source_preservation(collection) -> None:
    _database, library, repository, service, ids = collection
    parent = repository.create_folder("Parent")
    child = repository.create_folder("Child", parent)
    with pytest.raises(ValueError):
        repository.move(parent, child, is_folder=True)
    with pytest.raises(ValueError):
        repository.delete_folder(parent)
    playlist = repository.create("Original", child)
    service.add(playlist, [ids[0]])
    copy = repository.duplicate(playlist)
    assert repository.entries(copy)[0]["entry_id"] != repository.entries(playlist)[0]["entry_id"]
    assert repository.entries(copy)[0]["track_id"] == ids[0]
    with pytest.raises(ValueError):
        repository.delete_folder(child)
    source = Path(library.track(ids[0])["path"])
    before = source.read_bytes()
    repository.delete(playlist)
    repository.delete(copy)
    repository.delete_folder(child)
    repository.delete_folder(parent)
    assert source.read_bytes() == before


def test_missing_entries_keep_identity_and_snapshot_after_catalogue_deletion(collection) -> None:
    database, library, repository, service, ids = collection
    playlist = repository.create("Missing")
    service.add(playlist, [ids[0], ids[2]])
    Path(library.track(ids[0])["path"]).unlink()
    rows = service.rows(playlist)
    assert rows[0]["available"] is False
    assert rows[1]["available"] is True
    database.connection().execute("DELETE FROM tracks WHERE track_id IN (?,?)", (ids[0], ids[2]))
    rows_after = service.rows(playlist)
    assert [r["id"] for r in rows_after] == [r["id"] for r in rows]
    assert [r["title"] for r in rows_after] == [r["title"] for r in rows]
    assert all(not r["available"] for r in rows_after)
    assert len({r["id"] for r in rows_after}) == 2


def test_resolution_refuses_musical_duplicates(collection) -> None:
    _database, _library, repository, service, ids = collection
    playlist = repository.create(
        "Import",
        entries=[
            {"snapshot": {"title": "Missing", "artist": "Someone"}},
        ],
    )
    entry = repository.entries(playlist)[0]["entry_id"]
    service.add(playlist, [ids[0]])
    with pytest.raises(ValueError, match="already"):
        service.resolve(playlist, entry, ids[1])
    service.resolve(playlist, entry, ids[2])
    assert repository.entries(playlist)[0]["track_id"] == ids[2]
