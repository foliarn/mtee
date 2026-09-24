"""Interrupted and superseded inventories must not discard known references."""

from __future__ import annotations

import wave
from pathlib import Path

from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 8)


def _record(library, root_id: str, generation: int, path: Path, relative: str) -> str:
    return library.upsert_location(
        root_id,
        relative,
        path,
        SourceRevision.observe(path),
        MetadataSnapshot(title=(path.stem,)),
        generation,
    )


def test_partial_and_cancelled_scans_keep_unseen_tracks(tmp_path: Path) -> None:
    root_path = tmp_path / "collection"
    first = root_path / "a.wav"
    second = root_path / "b.wav"
    _write_wav(first)
    _write_wav(second)
    database = Database(tmp_path / "library.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(root_path)
    first_generation = library.begin_scan(root["id"])
    first_id = _record(library, root["id"], first_generation, first, "a.wav")
    _record(library, root["id"], first_generation, second, "b.wav")
    library.finish_scan(root["id"], first_generation, complete=True)

    partial_generation = library.begin_scan(root["id"])
    _record(library, root["id"], partial_generation, first, "a.wav")
    library.finish_scan(root["id"], partial_generation, complete=False)

    assert {row["filename"] for row in library.tracks_in_folder(root["id"], "")} == {
        "a.wav",
        "b.wav",
    }
    assert library.roots()[0]["availability"] == "partial"
    assert library.tracks_in_folder(root["id"], "")[0]["id"] == first_id
    database.close()


def test_stale_scan_batches_are_ignored_and_do_not_finish_new_scan(tmp_path: Path) -> None:
    root_path = tmp_path / "collection"
    track = root_path / "late.wav"
    _write_wav(track)
    database = Database(tmp_path / "library.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(root_path)

    old_generation = library.begin_scan(root["id"])
    new_generation = library.begin_scan(root["id"])
    stale_ids = library.upsert_locations(
        root["id"],
        [("late.wav", track, SourceRevision.observe(track), MetadataSnapshot())],
        old_generation,
    )
    library.finish_scan(root["id"], old_generation, complete=True)

    assert stale_ids == [""]
    assert library.tracks_in_folder(root["id"], "") == []
    assert library.roots()[0]["availability"] == "scanning"
    library.finish_scan(root["id"], new_generation, complete=False)
    database.close()
