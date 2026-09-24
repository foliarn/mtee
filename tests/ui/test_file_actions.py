"""QML workspace file actions retain track identity through move and Undo."""

from __future__ import annotations

import wave
from pathlib import Path
from threading import Event
from typing import Any, cast

from PySide6.QtGui import QWindow
from PySide6.QtQuick import QQuickItem, QQuickWindow

from mtee.app import _build_runtime, _shutdown
from mtee.cli import parse_arguments
from mtee.domain.tracks import SourceRevision
from mtee.models.file_operation_model import FileOperationModel
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.file_operation_repository import FileOperationRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_operation_service import FileOperationService
from mtee.services.jobs import JobContext, JobService
from mtee.services.metadata_reader import MetadataReader


def test_live_file_actions_move_and_undo_the_captured_track(qapp, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root = tmp_path / "Library"
    source = root / "Tracks" / "track.wav"
    source.parent.mkdir(parents=True)
    (root / "Destination").mkdir(parents=True)
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 80)

    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    root_record = LibraryRepository(database).add_root(root)
    database.close()

    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(data_dir)]))
    assert runtime is not None
    try:
        assert isinstance(runtime.workspace, WorkspaceModel)
        assert runtime.jobs.wait_for_done(10_000)
        qapp.processEvents()

        workspace = runtime.workspace
        rows = workspace.tabTracks("folder", f"{root_record['id']}/Tracks", "index", True)
        assert len(rows) == 1
        track_id = str(rows[0]["id"])
        operations = workspace.fileOperations
        assert isinstance(operations, FileOperationModel)

        root_id = str(root_record["id"])
        workspace.openFolder(f"folder:{root_id}/Tracks")
        workspace.toggleSplit()
        workspace.setActiveGroup(1)
        workspace.openFolder(f"folder:{root_id}/Destination")
        workspace.setActiveGroup(0)
        workspace.selectTrack(track_id)
        qapp.processEvents()
        window = runtime.engine.rootObjects()[0]
        assert isinstance(window, QQuickWindow)
        pending = [window.contentItem()]
        destination_view: QQuickItem | None = None
        while pending:
            item = pending.pop()
            if item.objectName() == "trackListView" and int(item.property("groupIndex")) == 1:
                destination_view = item
                break
            pending.extend(item.childItems())
        assert destination_view is not None
        assert cast(Any, destination_view).acceptTrackDrop(0, [track_id]), (
            workspace.groups_snapshot(),
            workspace._selection_by_tab,
            destination_view.property("tab"),
        )
        preview_targets = cast(list[dict[str, Any]], operations.previewTargets)
        assert preview_targets[0]["destination"] == str(root / "Destination" / source.name)
        assert operations.state == "preview"

        assert operations.openOperation("rename", "renamed", [track_id])
        assert operations.canExecute
        operations.execute()
        assert runtime.jobs.wait_for_done(10_000)
        qapp.processEvents()

        moved = root / "Tracks" / "renamed.wav"
        results = cast(list[dict[str, Any]], operations.results)
        assert results[0]["status"] == "completed"
        assert moved.is_file() and not source.exists()
        assert workspace.track(track_id)["id"] == track_id
        assert workspace.track(track_id)["path"] == str(moved)
        assert operations.canUndo

        operations.undo()
        assert runtime.jobs.wait_for_done(10_000)
        qapp.processEvents()

        assert source.is_file() and not moved.exists()
        assert workspace.track(track_id)["path"] == str(source)
        window = runtime.engine.rootObjects()[0]
        assert isinstance(window, QWindow)
        window.close()
        qapp.processEvents()
    finally:
        _shutdown(runtime)


def test_queued_file_operation_can_be_cancelled_before_mutation(qapp, tmp_path: Path) -> None:
    root = tmp_path / "Library"
    source = root / "Tracks" / "track.wav"
    source.parent.mkdir(parents=True)
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
        "Tracks/track.wav",
        source,
        SourceRevision.observe(source),
        MetadataReader().read(source),
        generation,
    )
    library.finish_scan(str(root_record["id"]), generation, complete=True)
    service = FileOperationService(
        library,
        FileOperationRepository(database, library),
        FileAccessCoordinator(),
    )
    jobs = JobService(qapp, max_thread_count=1)
    blocker_started = Event()
    release_blocker = Event()

    def blocker(_context: JobContext) -> None:
        blocker_started.set()
        release_blocker.wait(5)

    jobs.submit(blocker, label="Hold the test worker")
    assert blocker_started.wait(5)
    operations = FileOperationModel(service, jobs)
    try:
        assert operations.openOperation("rename", "renamed", [track_id])
        operations.execute()
        operations.cancel()
        release_blocker.set()
        assert jobs.wait_for_done(5_000)
        qapp.processEvents()

        assert operations.state == "cancelled"
        assert source.is_file()
        assert not source.with_name("renamed.wav").exists()
    finally:
        release_blocker.set()
        jobs.shutdown()
        database.close()
