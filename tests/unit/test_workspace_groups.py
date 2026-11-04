"""Center windows by id: splitting, moving tabs, closing windows, neighbours and restoring."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from mtee.models import window_layout as layout
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.workspace_repository import WorkspaceRepository
from mtee.services.jobs import JobService


def _workspace(qapp, tmp_path: Path) -> tuple[WorkspaceModel, JobService, Database]:
    database = Database(tmp_path / "groups.sqlite3")
    database.migrate()
    jobs = JobService(qapp, max_thread_count=1)
    workspace = WorkspaceModel(
        library=LibraryRepository(database),
        session=WorkspaceRepository(database),
        jobs=jobs,
    )
    return workspace, jobs, database


def _groups(workspace: WorkspaceModel) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], workspace.groups)


def _layout(workspace: WorkspaceModel) -> dict[str, Any]:
    return cast(dict[str, Any], workspace.centerLayout)


def _ids(workspace: WorkspaceModel) -> list[str]:
    return [group["id"] for group in _groups(workspace)]


def _tabs(workspace: WorkspaceModel, group_id: str) -> list[str]:
    return [
        tab["id"]
        for group in _groups(workspace)
        if group["id"] == group_id
        for tab in group["tabs"]
    ]


def test_three_windows_nest_and_read_in_order(qapp, tmp_path: Path) -> None:
    workspace, jobs, database = _workspace(qapp, tmp_path)
    workspace.openSettings()
    workspace.openTasks()
    workspace.splitWithTab("g1", "right", "g1", "tasks:")
    assert _ids(workspace) == ["g1", "g2"]
    assert workspace.activeGroup == "g2"

    workspace.openProfile()
    workspace.splitWithTab("g2", "bottom", "g2", "profile:")
    assert _ids(workspace) == ["g1", "g2", "g3"]
    tree = _layout(workspace)
    assert tree["type"] == "split" and tree["orientation"] == "row"
    assert layout.groups(layout.node_from_dict(tree)) == ("g1", "g2", "g3")
    assert _tabs(workspace, "g3") == ["profile:"]
    assert _tabs(workspace, "g2") == ["tasks:"]
    jobs.shutdown(1_000)
    database.close()


def test_closing_the_last_tab_of_a_window_removes_the_window(qapp, tmp_path: Path) -> None:
    workspace, jobs, database = _workspace(qapp, tmp_path)
    workspace.openSettings()
    workspace.openTasks()
    workspace.splitWithTab("g1", "right", "g1", "tasks:")
    workspace.closeTab("g2", "tasks:")
    assert _ids(workspace) == ["g1"]
    assert workspace.activeGroup == "g1"
    assert _layout(workspace) == {"type": "leaf", "group": "g1"}
    jobs.shutdown(1_000)
    database.close()


def test_move_tab_to_another_window_and_back(qapp, tmp_path: Path) -> None:
    workspace, jobs, database = _workspace(qapp, tmp_path)
    workspace.openSettings()
    workspace.openTasks()
    workspace.splitWithTab("g1", "right", "g1", "tasks:")
    workspace.moveTab("g2", "tasks:", "g1", 0)
    # The window that lost its last tab is removed; the tab sits first in g1.
    assert _ids(workspace) == ["g1"]
    assert _tabs(workspace, "g1") == ["tasks:", "settings:"]
    jobs.shutdown(1_000)
    database.close()


def test_focus_neighbour_and_close_group(qapp, tmp_path: Path) -> None:
    workspace, jobs, database = _workspace(qapp, tmp_path)
    workspace.openSettings()
    workspace.openTasks()
    workspace.splitWithTab("g1", "right", "g1", "tasks:")
    workspace.focusNeighbour("left")
    assert workspace.activeGroup == "g1"
    workspace.focusNeighbour("right")
    assert workspace.activeGroup == "g2"
    workspace.closeGroup("g2")
    assert _ids(workspace) == ["g1"]
    assert workspace.activeGroup == "g1"
    jobs.shutdown(1_000)
    database.close()


def test_split_ratios_keep_every_window_above_its_minimum(qapp, tmp_path: Path) -> None:
    workspace, jobs, database = _workspace(qapp, tmp_path)
    workspace.openSettings()
    workspace.openTasks()
    workspace.splitWithTab("g1", "right", "g1", "tasks:")
    workspace.setSplitRatios([], [0.01, 0.99])
    assert _layout(workspace)["ratios"] == [0.1, 0.9]
    jobs.shutdown(1_000)
    database.close()


def test_three_windows_and_their_layout_survive_a_restart(qapp, tmp_path: Path) -> None:
    workspace, jobs, database = _workspace(qapp, tmp_path)
    workspace.openSettings()
    workspace.openTasks()
    workspace.splitWithTab("g1", "right", "g1", "tasks:")
    workspace.openProfile()
    workspace.splitWithTab("g2", "bottom", "g2", "profile:")
    workspace.focusGroup("g2")
    workspace.flush_session()
    restored = WorkspaceModel(
        library=LibraryRepository(database),
        session=WorkspaceRepository(database),
        jobs=jobs,
    )
    assert _ids(restored) == ["g1", "g2", "g3"]
    assert _layout(restored) == _layout(workspace)
    assert restored.activeGroup == "g2"
    jobs.shutdown(1_000)
    database.close()


def test_ctrl_backslash_on_a_one_tab_window_opens_the_tab_beside_and_keeps_it(
    qapp, tmp_path: Path
) -> None:
    workspace, jobs, database = _workspace(qapp, tmp_path)
    workspace.openSettings()
    assert _tabs(workspace, "g1") == ["settings:"]
    # Ctrl+\ splits the focused window with its active tab: the window has one tab, so the
    # same tab opens in a new window on the right and the original window keeps it too.
    workspace.splitWithTab("g1", "right", "g1", "settings:")
    assert _ids(workspace) == ["g1", "g2"]
    assert _layout(workspace)["type"] == "split"
    assert _tabs(workspace, "g1") == ["settings:"]
    assert _tabs(workspace, "g2") == ["settings:"]
    assert workspace.activeGroup == "g2"
    jobs.shutdown(1_000)
    database.close()
