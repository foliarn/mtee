"""Interrupted moves remain journaled and are reported for inspection."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.file_operation_repository import FileOperationRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_operation_service import FileOperationService
from mtee.services.metadata_reader import MetadataReader
from mtee.services.platform.windows_file_ops import WindowsFileOps


class MoveThenFail:
    def move_no_replace(self, source: Path, destination: Path) -> None:
        WindowsFileOps().move_no_replace(source, destination)
        raise OSError("simulated interruption after native move")

    def move_cross_volume(self, *_args, **_kwargs) -> None:
        raise AssertionError("the same-volume recovery test must not use copy")


@pytest.mark.parametrize("change_after_inspection", [False, True])
def test_published_destination_with_old_database_record_needs_recovery(
    tmp_path: Path, change_after_inspection: bool
) -> None:
    root = tmp_path / "library"
    folder = root / "sets"
    folder.mkdir(parents=True)
    source = root / "Track.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 80)

    database_path = tmp_path / "data" / "mtee.sqlite3"
    database = Database(database_path)
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
    history = FileOperationRepository(database, library)
    service = FileOperationService(
        library,
        history,
        FileAccessCoordinator(),
        platform_ops=MoveThenFail(),
    )
    preview = service.preview("move", [track_id], str(folder))

    result = service.execute_target("move", preview.targets[0])

    destination = folder / source.name
    assert result.status == "recovery"
    assert not source.exists() and destination.is_file()
    record = library.source_record(track_id)
    assert record is not None
    assert record.path == source
    operation = history.get(result.operation_id)
    assert operation is not None
    assert operation["status"] == "needs_recovery"
    assert service.incomplete_operations()[0]["recovery_situation"] == "destination_present"
    database.close()

    reopened_database = Database(database_path)
    reopened_database.migrate()
    reopened_library = LibraryRepository(reopened_database)
    reopened_history = FileOperationRepository(reopened_database, reopened_library)
    reopened_service = FileOperationService(
        reopened_library,
        reopened_history,
        FileAccessCoordinator(),
    )

    pending = reopened_service.incomplete_operations()

    assert len(pending) == 1
    assert pending[0]["operation_id"] == result.operation_id
    assert pending[0]["recovery_situation"] == "destination_present"
    reopened_record = reopened_library.source_record(track_id)
    assert reopened_record is not None
    assert reopened_record.path == source
    assert destination.is_file()

    root_id = str(root_record["id"])
    generation = reopened_library.begin_scan(root_id)
    scanned_id = reopened_library.upsert_location(
        root_id,
        "Destination/Track.wav",
        destination,
        SourceRevision.observe(destination),
        MetadataReader().read(destination),
        generation,
    )
    reopened_library.finish_scan(root_id, generation, complete=True)
    assert scanned_id == ""
    assert (
        reopened_database.connection()
        .execute("SELECT 1 FROM track_locations WHERE path=?", (str(destination),))
        .fetchone()
        is None
    )

    if change_after_inspection:
        destination.write_bytes(destination.read_bytes() + b"changed after inspection")

    finalized = reopened_service.complete_recovery_to_destination(result.operation_id)

    completed_operation = reopened_history.get(result.operation_id)
    assert completed_operation is not None
    if change_after_inspection:
        assert finalized.status == "conflict"
        current_record = reopened_library.source_record(track_id)
        assert current_record is not None and current_record.path == source
        assert completed_operation["status"] == "needs_recovery"
    else:
        assert finalized.status == "completed"
        current_record = reopened_library.source_record(track_id)
        assert current_record is not None and current_record.path == destination
        assert completed_operation["status"] == "completed"
        assert reopened_service.incomplete_operations() == []
    reopened_database.close()
