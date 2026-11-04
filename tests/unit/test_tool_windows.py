"""Tool window registry and dock slots of the workspace (plan 131.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtee.models.tool_windows import core_tool_windows, tool_window_entries
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.workspace_repository import WorkspaceRepository
from mtee.services.jobs import JobService


def _ids(entries: list[dict[str, object]], side: str) -> list[str]:
    return [str(entry["id"]) for entry in entries if entry["side"] == side]


def test_core_windows_are_listed_per_bar_and_place() -> None:
    entries = core_tool_windows(convert_enabled=False)
    assert _ids(entries, "left") == ["explorer", "playlists", "artists", "plugins"]
    assert _ids(entries, "right") == ["info", "queue", "history", "settings"]
    places = {entry["id"]: entry["place"] for entry in entries}
    assert places["plugins"] == "bottom"
    assert places["settings"] == "bottom"
    kinds = {entry["id"]: entry["kind"] for entry in entries}
    assert kinds["settings"] == "action"


def test_convert_window_only_when_its_plugin_is_on() -> None:
    assert "convert" in _ids(core_tool_windows(convert_enabled=True), "left")
    assert "convert" not in _ids(core_tool_windows(convert_enabled=False), "left")


def test_plugin_windows_follow_core_windows_on_their_side() -> None:
    activities = [
        {"id": "sample.left_pane", "tip": "Left pane", "icon": "x", "side": "left"},
        {"id": "sample.right_pane", "tip": "Right pane", "icon": "y", "side": "right"},
    ]
    entries = tool_window_entries(activities, convert_enabled=False)
    left = _ids(entries, "left")
    right = _ids(entries, "right")
    assert left.index("sample.left_pane") > left.index("artists")
    assert right == ["info", "queue", "history", "sample.right_pane", "settings"]
    owners = {entry["id"]: entry["owner"] for entry in entries}
    assert owners["sample.right_pane"] == "sample"
    assert owners["explorer"] == ""


def test_an_unknown_side_falls_back_to_the_left_bar() -> None:
    entries = tool_window_entries(
        [{"id": "sample.odd", "tip": "Odd", "icon": "z", "side": "top"}], convert_enabled=False
    )
    assert "sample.odd" in _ids(entries, "left")


@pytest.fixture
def workspace(qapp, tmp_path: Path):  # type: ignore[no-untyped-def]
    database = Database(tmp_path / "library.sqlite3")
    database.migrate()
    jobs = JobService(qapp)
    model = WorkspaceModel(
        library=LibraryRepository(database),
        session=WorkspaceRepository(database),
        jobs=jobs,
    )
    yield model
    jobs.shutdown(1_000)
    database.close()


def test_open_below_stacks_and_close_gives_the_other_full_height(workspace: WorkspaceModel) -> None:
    workspace.openToolWindow("explorer", False)
    workspace.openToolWindow("playlists", True)
    state = workspace.dockState("left")
    assert state["open"] is True
    assert state["windows"] == ["explorer", "playlists"]
    workspace.closeToolWindow("explorer")
    assert workspace.dockState("left")["windows"] == ["playlists"]
    workspace.closeToolWindow("playlists")
    assert workspace.dockState("left")["open"] is False


def test_toggle_dock_and_widths_are_clamped(workspace: WorkspaceModel) -> None:
    workspace.toggleDock("left")
    assert workspace.sidebarVisible is False
    workspace.toggleDock("left")
    assert workspace.sidebarVisible is True
    workspace.setDockWidth("left", 9999)
    assert workspace.dockState("left")["width"] == 480
    workspace.setDockWidth("right", 1)
    assert workspace.dockState("right")["width"] == 220
    workspace.setDockRatio("left", 0.99)
    assert workspace.dockState("left")["ratio"] == 0.9


def test_settings_action_and_unknown_windows_do_not_open_a_dock(workspace: WorkspaceModel) -> None:
    before = workspace.dockState("right")
    workspace.openToolWindow("settings", False)
    workspace.openToolWindow("no.such.window", False)
    assert workspace.dockState("right") == before


def test_set_activity_is_an_alias_of_open_tool_window(workspace: WorkspaceModel) -> None:
    workspace.setActivity("artists")
    assert workspace.activity == "artists"
    assert workspace.sidebarVisible is True


def test_dock_state_survives_a_session_round_trip(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    database = Database(tmp_path / "library.sqlite3")
    database.migrate()

    def make() -> WorkspaceModel:
        return WorkspaceModel(
            library=LibraryRepository(database),
            session=WorkspaceRepository(database),
            jobs=JobService(qapp),
        )

    first = make()
    first.openToolWindow("artists", False)
    first.setDockWidth("left", 300)
    first.toggleDock("right")
    session = first._session_snapshot()
    assert session["version"] == 2
    WorkspaceRepository(database).save(session)
    second = make()
    assert second.activity == "artists"
    assert second.dockState("left")["width"] == 300
    assert second.dockState("right")["open"] is True
    second_jobs = second._jobs if hasattr(second, "_jobs") else None
    if second_jobs is not None:
        second_jobs.shutdown(1_000)
    first_jobs = first._jobs if hasattr(first, "_jobs") else None
    if first_jobs is not None:
        first_jobs.shutdown(1_000)
    database.close()
