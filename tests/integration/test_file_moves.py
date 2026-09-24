"""Same-volume file operations preserve identity and never overwrite peers."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.database import Database
from mtee.persistence.file_operation_repository import FileOperationRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_operation_service import FileOperationService
from mtee.services.metadata_reader import MetadataReader


@pytest.fixture
def library_case(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    source = root / "Track.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 80)
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root_record = library.add_root(root)
    generation = library.begin_scan(str(root_record["id"]))
    track_id = library.upsert_location(
        str(root_record["id"]),
        source.name,
        source,
        SourceRevision.observe(source),
        MetadataReader().read(source),
        generation,
    )
    library.finish_scan(str(root_record["id"]), generation, complete=True)
    access = FileAccessCoordinator()
    history = FileOperationRepository(database, library)
    service = FileOperationService(library, history, access)
    yield database, library, service, history, access, track_id, root, source


def test_move_and_undo_keep_the_same_track_uuid_and_refresh_its_location(
    library_case,
) -> None:
    database, library, service, history, _access, track_id, root, source = library_case
    folder = root / "sets"
    folder.mkdir()
    root_id = str(library.roots()[0]["id"])
    scan_generation = library.begin_scan(root_id)
    scanned_revision = SourceRevision.observe(source)
    scanned_metadata = MetadataReader().read(source)

    preview = service.preview("move", [track_id], str(folder))
    result = service.execute_target("move", preview.targets[0])

    destination = folder / source.name
    assert result.status == "completed"
    assert not source.exists() and destination.is_file()
    assert library.source_record(track_id).path == destination
    assert library.track(track_id)["id"] == track_id
    assert library.registered_roots_for(destination)
    assert history.get(result.operation_id)["status"] == "completed"
    assert service.latest_undoable_operation_id() == result.operation_id

    stale_scan_result = library.upsert_locations(
        root_id,
        [(source.name, source, scanned_revision, scanned_metadata)],
        scan_generation,
    )
    library.finish_scan(root_id, scan_generation, complete=True)
    assert stale_scan_result == [""]
    assert [row["id"] for row in library.tracks_in_folder(root_id, "sets")] == [track_id]

    undo = service.undo_move(result.operation_id)

    assert undo.status == "completed"
    assert source.is_file() and not destination.exists()
    assert library.source_record(track_id).path == source
    assert library.track(track_id)["id"] == track_id
    assert history.get(result.operation_id)["status"] == "undone"
    assert service.latest_undoable_operation_id() == ""
    database.close()


def test_destination_created_after_preview_is_not_replaced(library_case) -> None:
    _database, _library, service, _history, _access, track_id, root, source = library_case
    folder = root / "sets"
    folder.mkdir()
    preview = service.preview("move", [track_id], str(folder))
    destination = folder / source.name
    destination.write_bytes(b"created by another process")
    existing = destination.read_bytes()

    result = service.execute_target("move", preview.targets[0])

    assert result.status == "blocked"
    assert source.is_file()
    assert destination.read_bytes() == existing


def test_playback_or_another_reader_returns_a_busy_result(library_case) -> None:
    _database, _library, service, _history, access, track_id, root, source = library_case
    folder = root / "sets"
    folder.mkdir()
    preview = service.preview("move", [track_id], str(folder))

    with access.acquire(TrackId.parse(track_id), "test reader", timeout_seconds=0):
        result = service.execute_target("move", preview.targets[0])

    assert result.status == "busy"
    assert "Stop playback" in result.message
    assert source.is_file()
    assert not (folder / source.name).exists()


@pytest.mark.windows_file_ops
def test_windows_case_only_rename_uses_the_requested_spelling(library_case) -> None:
    _database, library, service, _history, _access, track_id, root, _source = library_case
    preview = service.preview("rename", [track_id], "track")

    result = service.execute_target("rename", preview.targets[0])

    assert result.status == "completed"
    names = {path.name for path in root.iterdir()}
    assert "track.wav" in names
    assert "Track.wav" not in names
    assert library.source_record(track_id).path.name == "track.wav"
