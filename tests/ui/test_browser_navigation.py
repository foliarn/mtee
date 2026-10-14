"""Exercise the live QML window against a tiny isolated audio library."""

from __future__ import annotations

import wave
from pathlib import Path

from mtee.app import _build_runtime, _shutdown
from mtee.cli import parse_arguments
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 80)


def test_live_window_indexes_and_navigates_a_nested_folder(qapp, qtbot, tmp_path: Path) -> None:
    data_dir = tmp_path / "validation data"
    root_path = tmp_path / "Ma collection épurée"
    track_path = root_path / "Été" / "Live" / "track.wav"
    _write_wav(track_path)

    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(root_path)
    database.close()

    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(data_dir)]))
    assert runtime is not None
    try:
        assert isinstance(runtime.workspace, WorkspaceModel)
        assert runtime.engine.rootObjects()
        workspace = runtime.workspace
        # Start-up reads the saved folders in a job, then scans each one in a second job: wait
        # for that scan to report before reading the index.
        with qtbot.waitSignal(workspace.scanFinished, timeout=10_000):
            qapp.processEvents()
        assert runtime.jobs.wait_for_done(10_000)
        qapp.processEvents()

        root_id = str(root["id"])
        tab_id = f"folder:{root_id}/Été/Live"
        workspace.openFolder(tab_id)
        # Rows are read by a background job and delivered to the model the view owns, so the
        # model is requested first and the test waits for it to be filled.
        model = workspace.trackModelForTab(tab_id, "folder", f"{root_id}/Été/Live", "index", True)
        qtbot.waitUntil(lambda: len(model.trackIds) == 1, timeout=10_000)
        rows = workspace.tabTracks("folder", f"{root_id}/Été/Live", "index", True)
        assert len(rows) == 1
        track_id = rows[0]["id"]
        assert model.trackIds == [track_id]
        workspace.setTabView(tab_id, "artwork")
        assert model.trackIds == [track_id]
        workspace.selectTrack(track_id)
        assert workspace.selected_ids_snapshot() == [track_id]
        workspace.setActiveGroup(0)
        qapp.processEvents()
    finally:
        _shutdown(runtime)
