"""Verified copies keep sources and acquire distinct catalog identities."""

from __future__ import annotations

import hashlib
import wave
from pathlib import Path

from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.file_operation_repository import FileOperationRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_operation_service import FileOperationService
from mtee.services.metadata_reader import MetadataReader
from mtee.services.platform.windows_file_ops import FileOperationRecoveryError, WindowsFileOps


class CopyThenFail(WindowsFileOps):
    def copy_no_replace(
        self,
        source: Path,
        temporary: Path,
        destination: Path,
        *,
        expected_revision: SourceRevision,
        expected_sha256: str,
        is_cancelled,
        report_progress,
    ) -> None:
        del destination, expected_revision, expected_sha256, is_cancelled, report_progress
        temporary.write_bytes(source.read_bytes())
        raise FileOperationRecoveryError("fixture interrupted before publish", temporary)


def test_copy_preserves_source_and_records_a_new_uuid(tmp_path: Path) -> None:
    root = tmp_path / "library"
    source = root / "Track.wav"
    source.parent.mkdir()
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 80)
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    registered = library.add_root(root)
    scan = library.begin_scan(str(registered["id"]))
    source_id = library.upsert_location(
        str(registered["id"]),
        source.name,
        source,
        SourceRevision.observe(source),
        MetadataReader().read(source),
        scan,
    )
    library.finish_scan(str(registered["id"]), scan, complete=True)
    history = FileOperationRepository(database, library)
    service = FileOperationService(library, history, FileAccessCoordinator())
    destination_folder = root / "copies"
    destination_folder.mkdir()

    preview = service.preview("copy", [source_id], str(destination_folder))
    result = service.execute_target("copy", preview.targets[0])

    copied_path = destination_folder / source.name
    rows = library.tracks_in_folder(str(registered["id"]), "copies")
    assert result.status == "completed", result.message
    assert source.is_file() and copied_path.is_file()
    assert (
        hashlib.sha256(source.read_bytes()).digest()
        == hashlib.sha256(copied_path.read_bytes()).digest()
    )
    source_record = library.source_record(source_id)
    assert source_record is not None and source_record.path == source
    assert len(rows) == 1 and rows[0]["id"] != source_id
    assert rows[0]["fileModifiedAtNs"] == copied_path.stat().st_mtime_ns
    assert rows[0]["fileCreatedAtNs"] == getattr(copied_path.stat(), "st_birthtime_ns", None)
    copied_record = library.source_record(rows[0]["id"])
    assert copied_record is not None
    assert copied_record.revision.file_id != source_record.revision.file_id
    assert (
        database.connection()
        .execute(
            "SELECT status,copied_track_id FROM file_copy_operations WHERE operation_id=?",
            (result.operation_id,),
        )
        .fetchone()["status"]
        == "completed"
    )
    assert result.operation_id

    collision = service.preview("copy", [source_id], str(destination_folder))
    assert not collision.executable
    assert "already exists" in collision.targets[0].message
    assert copied_path.read_bytes() == source.read_bytes()
    database.close()


def test_interrupted_copy_keeps_source_and_surfaces_fixture_recovery(tmp_path: Path) -> None:
    root = tmp_path / "library"
    source = root / "Track.wav"
    source.parent.mkdir()
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 80)
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    registered = library.add_root(root)
    generation = library.begin_scan(str(registered["id"]))
    track_id = library.upsert_location(
        str(registered["id"]),
        source.name,
        source,
        SourceRevision.observe(source),
        MetadataReader().read(source),
        generation,
    )
    library.finish_scan(str(registered["id"]), generation, complete=True)
    history = FileOperationRepository(database, library)
    service = FileOperationService(
        library, history, FileAccessCoordinator(), platform_ops=CopyThenFail()
    )
    folder = root / "copy"
    folder.mkdir()
    preview = service.preview("copy", [track_id], str(folder))

    result = service.execute_target("copy", preview.targets[0])
    recovery = [item for item in service.incomplete_operations() if item.get("kind") == "copy"]

    assert result.status == "recovery"
    assert source.is_file()
    assert recovery[0]["recovery_situation"] == "verified_temporary_copy"
    assert not (folder / source.name).exists()
    database.close()
