"""Removing a source keeps its tracks, analysis and playlist entries; adding it back finds them.

Plan 132.1 and U12. A temporary database and small WAV files under ``tmp_path``; nothing outside
it is written.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.services.playlist_service import PlaylistService


def _write_wav(path: Path, frames: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * frames)


def _scan(library: LibraryRepository, root_id: str, music: Path) -> list[str]:
    generation = library.begin_scan(root_id)
    entries = []
    for path in sorted(music.rglob("*.wav")):
        entries.append(
            (
                path.relative_to(music).as_posix(),
                path,
                SourceRevision.observe(path),
                MetadataSnapshot(
                    title=(path.stem,),
                    artist=("Test artist",),
                    technical=TechnicalInfo(duration_us=100_000),
                ),
            )
        )
    identities = library.upsert_locations(root_id, entries, generation)
    library.finish_scan(root_id, generation, complete=True)
    return identities


@pytest.fixture
def library(tmp_path: Path):
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    music = tmp_path / "music"
    _write_wav(music / "sub" / "a.wav", 800)
    _write_wav(music / "b.wav", 800)
    repository = LibraryRepository(database)
    root_id = str(repository.add_root(music)["id"])
    ids = _scan(repository, root_id, music)
    yield database, repository, music, root_id, ids
    database.close()


def _count(database: Database, sql: str, *parameters: object) -> int:
    return int(database.connection().execute(sql, parameters).fetchone()[0])


def test_removing_a_source_keeps_tracks_analysis_and_playlist_entries(library) -> None:
    database, repository, music, root_id, ids = library
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO track_analysis(track_id,bpm,key_tonic,key_minor,algorithm_version,"
            "analyzed_at_utc) VALUES(?,?,?,?,?,?)",
            (ids[0], 120.0, 0, 0, 1, "2026-11-04T00:00:00+00:00"),
        )
    playlists = PlaylistsRepository(database)
    service = PlaylistService(playlists, repository)
    playlist = playlists.create("Road")
    assert service.add(playlist, ids) == 2

    removed = repository.remove_root(root_id)

    assert removed == 2
    assert repository.roots() == []
    assert _count(database, "SELECT COUNT(*) FROM tracks") == 2
    assert _count(database, "SELECT COUNT(*) FROM track_locations") == 2
    assert _count(database, "SELECT COUNT(*) FROM track_analysis WHERE bpm=120.0") == 1
    assert _count(database, "SELECT COUNT(*) FROM root_tracks") == 0
    assert repository.track(ids[0])["rootId"] in ("", None)
    rows = service.rows(playlist)
    assert [row["trackId"] for row in rows] == ids
    assert not any(row["available"] for row in rows)
    assert (music / "sub" / "a.wav").is_file()
    assert (music / "b.wav").is_file()


def test_adding_the_source_again_finds_the_same_track_ids_and_analysis(library) -> None:
    database, repository, music, root_id, ids = library
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO track_analysis(track_id,bpm,key_tonic,key_minor,algorithm_version,"
            "analyzed_at_utc) VALUES(?,?,?,?,?,?)",
            (ids[0], 120.0, 0, 0, 1, "2026-11-04T00:00:00+00:00"),
        )
    playlists = PlaylistsRepository(database)
    service = PlaylistService(playlists, repository)
    playlist = playlists.create("Road")
    service.add(playlist, ids)
    repository.remove_root(root_id)

    again = str(repository.add_root(music)["id"])
    found = _scan(repository, again, music)

    assert sorted(found) == sorted(ids)
    assert found == ids
    assert _count(database, "SELECT COUNT(*) FROM tracks") == 2
    assert _count(database, "SELECT COUNT(*) FROM track_analysis WHERE bpm=120.0") == 1
    assert repository.track(ids[0])["rootId"] == again
    rows = service.rows(playlist)
    assert [row["trackId"] for row in rows] == ids
    assert all(row["available"] for row in rows)


def test_removing_an_unknown_source_is_refused(library) -> None:
    _database, repository, _music, _root_id, _ids = library
    with pytest.raises(KeyError):
        repository.remove_root("00000000-0000-0000-0000-000000000000")
