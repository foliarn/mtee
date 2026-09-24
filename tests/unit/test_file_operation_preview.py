"""Preview rejects unsafe names, collisions, unsupported volumes, and trash."""

from __future__ import annotations

import wave
from pathlib import Path

from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.file_operation_repository import FileOperationRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_operation_service import FileOperationService
from mtee.services.metadata_reader import MetadataReader


def _service(tmp_path: Path) -> tuple[Database, LibraryRepository, FileOperationService, str, Path]:
    root_path = tmp_path / "library"
    root_path.mkdir()
    source = root_path / "Track.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 80)
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(root_path)
    scan = library.begin_scan(str(root["id"]))
    track_id = library.upsert_location(
        str(root["id"]),
        source.name,
        source,
        SourceRevision.observe(source),
        MetadataReader().read(source),
        scan,
    )
    library.finish_scan(str(root["id"]), scan, complete=True)
    service = FileOperationService(
        library,
        FileOperationRepository(database, library),
        FileAccessCoordinator(),
    )
    return database, library, service, track_id, root_path


def test_preview_uses_audio_suffix_and_refuses_reserved_or_invalid_names(
    tmp_path: Path,
) -> None:
    database, _library, service, track_id, _root = _service(tmp_path)

    good = service.preview("rename", [track_id], "New name")
    reserved = service.preview("rename", [track_id], "CON")
    invalid = service.preview("rename", [track_id], "bad:name")
    suffix_change = service.preview("rename", [track_id], "New name.mp3")
    partial = service.preview("rename", [track_id, "missing-track"], "New name")

    assert good.executable
    assert good.targets[0].destination.name == "New name.wav"
    assert not reserved.executable and "reserv" in reserved.targets[0].message
    assert not invalid.executable and "does not allow" in invalid.targets[0].message
    assert (
        not suffix_change.executable
        and "extension cannot be changed" in suffix_change.targets[0].message
    )
    assert partial.executable
    assert [target.status for target in partial.targets] == ["ready", "blocked"]
    database.close()


def test_preview_requires_a_registered_same_volume_folder_and_disables_trash(
    tmp_path: Path,
) -> None:
    database, _library, service, track_id, root = _service(tmp_path)
    destination = root / "sets"
    destination.mkdir()

    move = service.preview("move", [track_id], str(destination))
    trash = service.preview("trash", [track_id], "")
    outside = service.preview("move", [track_id], str(tmp_path))

    assert move.executable
    assert move.targets[0].destination == destination / "Track.wav"
    assert not trash.executable and "disabled" in trash.targets[0].message
    assert not outside.executable and "registered library root" in outside.targets[0].message
    database.close()
