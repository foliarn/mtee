"""Persistent paths, revisions, roots and read-only metadata snapshots."""

from __future__ import annotations

import wave
from pathlib import Path

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
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


def test_roots_are_deduplicated_and_tracks_keep_ids_across_rescans(tmp_path: Path) -> None:
    root_path = tmp_path / "collection"
    track_path = root_path / "sub" / "track.wav"
    _write_wav(track_path)
    database = Database(tmp_path / "library.sqlite3")
    database.migrate()
    library = LibraryRepository(database)

    root = library.add_root(root_path)
    duplicate = library.add_root(root_path / ".")
    generation = library.begin_scan(root["id"])
    metadata = MetadataSnapshot(
        title=("Tagged title",), technical=TechnicalInfo(duration_us=1_000_000)
    )
    track_id = library.upsert_location(
        root["id"],
        "sub/track.wav",
        track_path,
        SourceRevision.observe(track_path),
        metadata,
        generation,
    )
    library.upsert_folders(root["id"], ["sub", "empty"], generation)
    library.finish_scan(root["id"], generation, complete=True)

    next_generation = library.begin_scan(root["id"])
    rescanned = library.upsert_location(
        root["id"],
        "sub/track.wav",
        track_path,
        SourceRevision.observe(track_path),
        metadata,
        next_generation,
    )
    library.upsert_folders(root["id"], ["sub", "empty"], next_generation)
    library.finish_scan(root["id"], next_generation, complete=True)

    assert duplicate["id"] == root["id"]
    assert rescanned == track_id
    assert library.tracks_in_folder(root["id"], "sub")[0]["id"] == track_id
    assert library.tracks_in_folder(root["id"], "sub")[0]["folder"] == f"folder:{root['id']}/sub"
    assert library.folders(root["id"]) == ["", "empty", "sub"]
    assert library.folder_stats(root["id"], "sub") == (1, track_path.stat().st_size, 1_000_000)
    database.close()


def test_overlapping_parent_and_child_roots_share_one_path_identity(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    track = parent / "child" / "one.wav"
    _write_wav(track)
    database = Database(tmp_path / "library.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    parent_root = library.add_root(parent)
    child_root = library.add_root(parent / "child")
    metadata = MetadataSnapshot(title=("Same source",))

    identities = []
    for root, relative in ((parent_root, "child/one.wav"), (child_root, "one.wav")):
        generation = library.begin_scan(root["id"])
        identities.extend(
            library.upsert_locations(
                root["id"],
                [(relative, track, SourceRevision.observe(track), metadata)],
                generation,
            )
        )
        library.finish_scan(root["id"], generation, complete=True)

    assert len(set(identities)) == 1
    assert library.tracks_in_folder(parent_root["id"], "child")[0]["id"] == identities[0]
    assert library.tracks_in_folder(child_root["id"], "")[0]["id"] == identities[0]
    database.close()


def test_unchanged_scan_reuses_the_snapshot_and_changed_revision_is_not_reused(
    tmp_path: Path,
) -> None:
    track = tmp_path / "collection" / "track.wav"
    _write_wav(track)
    database = Database(tmp_path / "library.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(track.parent)
    metadata = MetadataSnapshot(title=("Known title",))
    revision = SourceRevision.observe(track)

    first = library.begin_scan(root["id"])
    track_id = library.upsert_location(root["id"], "track.wav", track, revision, metadata, first)
    library.finish_scan(root["id"], first, complete=True)

    assert library.unchanged_paths(root["id"], [("track.wav", revision)]) == {"track.wav"}
    second = library.begin_scan(root["id"], show_scanning=False)
    assert library.roots()[0]["availability"] == "available"
    reused = library.upsert_locations(root["id"], [("track.wav", track, revision, None)], second)
    library.finish_scan(root["id"], second, complete=True)
    assert reused == [track_id]
    assert library.tracks_in_folder(root["id"], "")[0]["title"] == "Known title"

    with track.open("ab") as handle:
        handle.write(b"changed")
    changed_revision = SourceRevision.observe(track)
    assert library.unchanged_paths(root["id"], [("track.wav", changed_revision)]) == set()
    third = library.begin_scan(root["id"])
    assert library.upsert_locations(
        root["id"], [("track.wav", track, changed_revision, None)], third
    ) == [""]
    library.finish_scan(root["id"], third, complete=False)
    fourth = library.begin_scan(root["id"], show_scanning=False)
    assert library.roots()[0]["availability"] == "partial"
    library.finish_scan(root["id"], fourth, complete=False, available=False)
    assert library.roots()[0]["availability"] == "unavailable"
    assert library.tracks_in_folder(root["id"], "")[0]["id"] == track_id
    database.close()
