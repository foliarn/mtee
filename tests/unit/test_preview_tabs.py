"""Preview tabs: browsing reuses one italic tab, working in it or a setting keeps it."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.workspace_repository import WorkspaceRepository
from mtee.services.jobs import JobService

ROOT = "11111111-1111-1111-1111-111111111111"


def _tabs(workspace: WorkspaceModel) -> list[tuple[str, bool]]:
    group: dict[str, Any] = cast(list[dict[str, Any]], workspace.groups)[0]
    return [(tab["id"], bool(tab.get("preview"))) for tab in group["tabs"]]


def _make(qapp, tmp_path: Path):
    database = Database(tmp_path / "preview.sqlite3")
    database.migrate()
    session = WorkspaceRepository(database)
    jobs = JobService(qapp, max_thread_count=1)
    workspace = WorkspaceModel(library=LibraryRepository(database), session=session, jobs=jobs)
    return workspace, session, jobs, database


def test_browsing_folders_reuses_one_preview_tab(qapp, tmp_path: Path) -> None:
    workspace, _session, jobs, database = _make(qapp, tmp_path)
    workspace.openFolder(f"folder:{ROOT}/a")
    workspace.openFolder(f"folder:{ROOT}/b")
    workspace.openFolder(f"folder:{ROOT}/c")
    assert _tabs(workspace) == [(f"folder:{ROOT}/c", True)]

    workspace.keepTab(0, f"folder:{ROOT}/c")
    workspace.openFolder(f"folder:{ROOT}/d")
    workspace.openFolder(f"folder:{ROOT}/e")
    assert _tabs(workspace) == [(f"folder:{ROOT}/c", False), (f"folder:{ROOT}/e", True)]
    jobs.shutdown(1_000)
    database.close()


def test_working_in_a_preview_tab_keeps_it(qapp, tmp_path: Path) -> None:
    workspace, _session, jobs, database = _make(qapp, tmp_path)
    tab = f"folder:{ROOT}/a"
    workspace.openFolder(tab)
    workspace.setSort(tab, "title")
    workspace.openFolder(f"folder:{ROOT}/b")
    assert _tabs(workspace) == [(tab, False), (f"folder:{ROOT}/b", True)]
    workspace.setSearch(f"folder:{ROOT}/b", "x")
    assert _tabs(workspace)[1] == (f"folder:{ROOT}/b", False)
    jobs.shutdown(1_000)
    database.close()


def test_the_setting_turns_previews_off_and_is_restored(qapp, tmp_path: Path) -> None:
    workspace, session, jobs, database = _make(qapp, tmp_path)
    workspace.openFolder(f"folder:{ROOT}/a")
    workspace.setPreviewTabs(False)
    assert _tabs(workspace) == [(f"folder:{ROOT}/a", False)]
    workspace.openFolder(f"folder:{ROOT}/b")
    workspace.openFolder(f"folder:{ROOT}/c")
    assert len(_tabs(workspace)) == 3

    workspace.flush_session()
    restored = WorkspaceModel(library=LibraryRepository(database), session=session, jobs=jobs)
    assert restored.previewTabs is False
    restored.setPreviewTabs(True)
    restored.openFolder(f"folder:{ROOT}/d")
    restored.openFolder(f"folder:{ROOT}/e")
    assert len(_tabs(restored)) == 4  # the three kept tabs and one preview
    jobs.shutdown(1_000)
    database.close()
