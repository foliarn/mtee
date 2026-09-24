"""Interrupted moves remain journaled and are reported for inspection."""

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
from mtee.services.platform.windows_file_ops import WindowsFileOps


class MoveThenFail:
    def move_no_replace(self, source: Path, destination: Path) -> None:
        WindowsFileOps().move_no_replace(source, destination)
        raise OSError("simulated interruption after native move")


def test_published_destination_with_old_database_record_needs_recovery(
    tmp_path: Path,
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
