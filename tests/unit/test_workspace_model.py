"""Workspace navigation, per-panel selection and session restoration."""

from __future__ import annotations

import json
import wave
from pathlib import Path

from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.tracks import SourceRevision
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.workspace_repository import WorkspaceRepository
from mtee.services.jobs import JobService


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 8)


def test_clear_selection_is_scoped_to_group_and_persisted(qapp, tmp_path: Path) -> None:
    database = Database(tmp_path / "selection.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    session = WorkspaceRepository(database)
    jobs = JobService(qapp, max_thread_count=1)
    workspace = WorkspaceModel(library=library, session=session, jobs=jobs)
    workspace.openSettings()
    workspace.selectTrack("first", "single", [])
    workspace.toggleSplit()
    workspace.setActiveGroup(1)
    workspace.selectTrack("second", "single", [])
    workspace.clearSelection()
    assert workspace.selectedIds == []
    workspace.setActiveGroup(0)
    assert workspace.selectedIds == ["first"]
    workspace.clearSelection(0)
    assert workspace.selectedIds == []
    workspace.flush_session()
    restored = WorkspaceModel(library=library, session=session, jobs=jobs)
    assert restored.selectedIds == []
    restored.setActiveGroup(1)
    assert restored.selectedIds == []
    jobs.shutdown(1_000)
    database.close()


def test_same_tab_keeps_distinct_filtered_models_per_group(qapp, qtbot, tmp_path: Path) -> None:
    folder = tmp_path / "audio"
    first = folder / "first.wav"
    second = folder / "second.wav"
    _write_wav(first)
    _write_wav(second)
    database = Database(tmp_path / "views.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(folder)
    generation = library.begin_scan(root["id"])
    first_id = library.upsert_location(
        root["id"],
        first.name,
        first,
        SourceRevision.observe(first),
        MetadataSnapshot(title=("First",)),
        generation,
    )
    second_id = library.upsert_location(
        root["id"],
        second.name,
        second,
        SourceRevision.observe(second),
        MetadataSnapshot(title=("Second",)),
        generation,
    )
    library.finish_scan(root["id"], generation, complete=True)
    jobs = JobService(qapp, max_thread_count=2)
    workspace = WorkspaceModel(library=library, session=WorkspaceRepository(database), jobs=jobs)
    tab_id = f"folder:{root['id']}/"
    workspace.openFolder(tab_id)
    workspace.setSearch(tab_id, "first")
    workspace.toggleSplit()
    workspace.setActiveGroup(1)
    workspace.setSearch(tab_id, "second")
    first_model = workspace.trackModelForTab(tab_id, "folder", f"{root['id']}/", "index", True, 0)
    second_model = workspace.trackModelForTab(tab_id, "folder", f"{root['id']}/", "index", True, 1)
    qtbot.waitUntil(lambda: first_model.trackIds == [first_id])
    qtbot.waitUntil(lambda: second_model.trackIds == [second_id])
    assert first_model is not second_model
    jobs.shutdown(1_000)
    database.close()


def test_page_history_replays_settings_and_forks_per_group(qapp, tmp_path: Path) -> None:
    database = Database(tmp_path / "history.sqlite3")
    database.migrate()
    jobs = JobService(qapp, max_thread_count=1)
    workspace = WorkspaceModel(
        library=LibraryRepository(database),
        session=WorkspaceRepository(database),
        jobs=jobs,
    )
    workspace.openSettings()
    workspace.setSettingsPage("analysis")
    workspace.openConvert()
    assert workspace.canNavigateBack
    workspace.navigateBack()
    assert workspace.groups_snapshot()[0]["active"] == "settings:"
    assert workspace.settingsPage == "analysis"
    assert workspace.canNavigateForward
    workspace.openSettings()
    workspace.setSettingsPage("general")
    assert not workspace.canNavigateForward
    workspace.toggleSplit()
    workspace.setActiveGroup(1)
    workspace.openConvert()
    workspace.navigateBack()
    assert workspace.groups_snapshot()[1]["active"] == "settings:"
    workspace.setActiveGroup(0)
    assert workspace.groups_snapshot()[0]["active"] == "settings:"
    workspace.closeTab(0, "settings:")
    workspace.navigateBack()
    assert workspace.groups_snapshot()[0]["active"] == "settings:"
    assert any(tab["id"] == "settings:" for tab in workspace.groups_snapshot()[0]["tabs"])
    jobs.shutdown(1_000)
    database.close()


def test_navigation_keeps_each_panel_selection_and_restores_it(qapp, tmp_path: Path) -> None:
    root_path = tmp_path / "collection"
    first = root_path / "first.wav"
    second = root_path / "second.wav"
    _write_wav(first)
    _write_wav(second)
    database = Database(tmp_path / "library.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(root_path)
    generation = library.begin_scan(root["id"])
    first_id = library.upsert_location(
        root["id"],
        "first.wav",
        first,
        SourceRevision.observe(first),
        MetadataSnapshot(),
        generation,
    )
    second_id = library.upsert_location(
        root["id"],
        "second.wav",
        second,
        SourceRevision.observe(second),
        MetadataSnapshot(),
        generation,
    )
    library.finish_scan(root["id"], generation, complete=True)
    session = WorkspaceRepository(database)
    jobs = JobService(qapp, max_thread_count=1)

    workspace = WorkspaceModel(library=library, session=session, jobs=jobs)
    assert workspace.islandEnabled
    workspace.openFolder(f"root:{root['id']}")
    workspace.selectTrack(first_id)
    workspace.toggleSplit()
    workspace.setActiveGroup(1)
    assert workspace.selected_ids_snapshot() == []
    workspace.selectTrack(second_id)
    assert workspace.selected_ids_snapshot() == [second_id]
    workspace.setActiveGroup(0)
    assert workspace.selected_ids_snapshot() == [first_id]

    workspace.setActiveGroup(1)
    group_state = workspace.groups_snapshot()[1]
    tab = group_state["tabs"][0]
    track_model = workspace.trackModelForTab(tab["id"], tab["kind"], tab["ref"], "index", True)
    assert track_model.trackIds == [first_id, second_id]
    workspace.setTabView(tab["id"], "artwork")
    assert track_model.trackIds == [first_id, second_id]
    workspace.toggleColumn(tab["id"], "duration")
    workspace.toggleColumn(tab["id"], "bitrate")
    workspace.resizeColumn(tab["id"], "genre", 155)
    workspace.moveColumn(tab["id"], "genre", -1)
    assert workspace._jobs.wait_for_done(1_000)

    restored = WorkspaceModel(library=library, session=session, jobs=jobs)
    restored_tab = restored.groups_snapshot()[1]["tabs"][0]
    assert restored.groups_snapshot()[1]["active"] == tab["id"]
    assert restored.selected_ids_snapshot() == [second_id]
    assert "duration" not in restored_tab["hiddenColumns"]
    assert "bitrate" not in restored_tab["hiddenColumns"]
    assert restored.islandEnabled
    restored.setIslandEnabled(False)
    assert not WorkspaceModel(library=library, session=session, jobs=jobs).islandEnabled
    assert restored_tab["columnWidths"]["genre"] == 155
    assert (
        restored_tab["columnOrder"].index("genre") == restored_tab["columnOrder"].index("album") - 1
    )
    restored.setActiveGroup(0)
    assert restored.selected_ids_snapshot() == [first_id]
    jobs.shutdown()
    database.close()


def test_invalid_session_is_replaced_with_safe_layout_and_diagnostic(qapp, tmp_path: Path) -> None:
    database = Database(tmp_path / "library.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    session = WorkspaceRepository(database)
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO workspace_state(workspace_id,value_json,updated_at_utc) "
            "VALUES('main',?, '2026-01-01T00:00:00+00:00')",
            (json.dumps({"version": 1, "roots": [], "groups": [], "activeGroup": "broken"}),),
        )
    workspace = WorkspaceModel(library=library, session=session, jobs=JobService(qapp))

    assert session.load_recovered
    assert workspace.groups_snapshot() == [{"tabs": [], "active": ""}]
    assert "safe default layout" in workspace._message
    database.close()
