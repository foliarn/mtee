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
from mtee.services.platform.windows_file_ops import (
    FileOperationRecoveryError,
    WindowsFileOps,
)


class ForcedCrossVolumeService(FileOperationService):
    @staticmethod
    def _same_volume(source: Path, destination_folder: Path) -> bool:
        """Exercise copy choreography on this host when no second volume is mounted."""
        del source, destination_folder
        return False


class PublishThenFailToRemoveSource(WindowsFileOps):
    def move_cross_volume(
        self,
        source: Path,
        temporary: Path,
        destination: Path,
        *,
        expected_revision: SourceRevision,
        expected_sha256: str,
        is_cancelled,
        report_progress,
        phase_changed,
    ) -> None:
        temporary.write_bytes(source.read_bytes())
        phase_changed("copying", temporary)
        self.move_no_replace(temporary, destination)
        phase_changed("destination_published", None)
        raise FileOperationRecoveryError(
            "simulated source-removal failure",
            None,
            phase="destination_published",
        )


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
def test_cross_volume_copy_verifies_content_and_keeps_the_track_uuid(library_case) -> None:
    database, library, _service, history, access, track_id, root, source = library_case
    folder = root / "other-library"
    folder.mkdir()
    service = ForcedCrossVolumeService(library, history, access)
    target = service.preview("move", [track_id], str(folder)).targets[0]
    expected_revision = target.revision
    supported_attributes = 0x00000001 | 0x00000002 | 0x00000004 | 0x00000020 | 0x00002000
    original_attributes = (
        int(getattr(source.stat(), "st_file_attributes", 0)) & supported_attributes
    )
    original_creation_time = source.stat().st_ctime_ns

    result = service.execute_target("move", target)

    destination = folder / source.name
    assert result.status == "completed", (result.message, history.get(result.operation_id))
    assert not source.exists() and destination.read_bytes()
    assert destination.stat().st_mtime_ns == expected_revision.mtime_ns
    assert destination.stat().st_ctime_ns == original_creation_time
    assert int(getattr(destination.stat(), "st_file_attributes", 0)) & supported_attributes == (
        original_attributes
    )
    assert library.source_record(track_id).path == destination
    assert library.track(track_id)["id"] == track_id
    journal = history.get(result.operation_id)
    assert journal["status"] == "completed"
    assert journal["phase"] == "completed"
    database.close()


@pytest.mark.windows_file_ops
def test_cross_volume_copy_can_be_cancelled_without_losing_the_source(library_case) -> None:
    database, library, _service, history, access, track_id, root, source = library_case
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * (1024 * 1024))
    root_id = str(library.roots()[0]["id"])
    scan_generation = library.begin_scan(root_id)
    refreshed_id = library.upsert_location(
        root_id,
        source.name,
        source,
        SourceRevision.observe(source),
        MetadataReader().read(source),
        scan_generation,
    )
    library.finish_scan(root_id, scan_generation, complete=True)
    assert refreshed_id == track_id
    folder = root / "other-library"
    folder.mkdir()
    service = ForcedCrossVolumeService(library, history, access)
    target = service.preview("move", [track_id], str(folder)).targets[0]
    progress: list[tuple[int, int]] = []

    def report_progress(copied: int, total: int) -> None:
        progress.append((copied, total))

    result = service.execute_target(
        "move",
        target,
        is_cancelled=lambda: bool(progress),
        report_progress=report_progress,
    )

    assert result.status == "cancelled"
    assert source.is_file() and not (folder / source.name).exists()
    assert not list(folder.glob(".mtee-move-*.tmp"))
    assert library.source_record(track_id).path == source
    assert progress and 0 < progress[0][0] < progress[0][1]
    journal = history.get(result.operation_id)
    assert journal["status"] == "failed"
    assert journal["phase"] == "cancelled"
    assert journal["recovery_path"] is None
    database.close()


@pytest.mark.windows_file_ops
def test_source_removal_failure_retains_both_copies_for_recovery(library_case) -> None:
    database, library, _service, history, access, track_id, root, source = library_case
    folder = root / "other-library"
    folder.mkdir()
    service = ForcedCrossVolumeService(
        library,
        history,
        access,
        platform_ops=PublishThenFailToRemoveSource(),
    )
    target = service.preview("move", [track_id], str(folder)).targets[0]

    result = service.execute_target("move", target)

    destination = folder / source.name
    assert result.status == "recovery"
    assert source.is_file() and destination.read_bytes() == source.read_bytes()
    assert library.source_record(track_id).path == source
    journal = history.get(result.operation_id)
    assert journal["status"] == "needs_recovery"
    assert journal["phase"] == "destination_published"
    assert service.incomplete_operations()[0]["recovery_situation"] == "both_copies_present"
    database.close()


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
