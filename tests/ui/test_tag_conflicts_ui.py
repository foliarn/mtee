"""The Tasks pane lists tag conflicts and its small buttons replace or dismiss them."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from mutagen.flac import FLAC
from PySide6.QtCore import QCoreApplication
from PySide6.QtQuick import QQuickWindow
from tests.helpers.analysis_library import AnalysisLibrary, require_ffmpeg
from tests.integration.test_tag_conflicts import _flac_with_aliases
from tests.ui.test_analysis_ui import _click, _first, _items, _wait_for

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions, parse_arguments
from mtee.domain.tag_conflicts import TagConflict, TagConflictEntry
from mtee.models.workspace_model import WorkspaceModel


def _settle(seconds: float = 0.3) -> None:
    """Let the layout of freshly created rows finish before a click uses their position."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)


def _open_tasks(workspace: WorkspaceModel) -> None:
    workspace.setActivity("tasks")
    workspace.setSidebarVisible(True)


def test_the_replace_button_fixes_the_tags_of_a_conflicting_file(qapp, tmp_path: Path) -> None:
    require_ffmpeg()
    fixture = AnalysisLibrary(tmp_path)
    track_id, path = _flac_with_aliases(fixture)
    fixture.close()

    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(tmp_path / "data")]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        workspace = cast(WorkspaceModel, runtime.workspace)
        settings = cast(Any, workspace.property("analysisSettings"))
        conflicts = cast(Any, workspace.property("tagConflicts"))
        settings.setWriteTags(True)
        workspace.analyzeTracks([track_id], False)

        _wait_for(window, lambda: conflicts.count == 1)
        assert "Open Tasks" in workspace.message
        _open_tasks(workspace)
        _wait_for(window, lambda: bool(_items(window.contentItem(), "tagConflictRow")))
        header = _first(window.contentItem(), "tagConflictsHeader")
        assert header.isVisible()
        _settle()
        row = _first(window.contentItem(), "tagConflictRow")
        assert FLAC(path)["key"] == ["Gm"]  # nothing is written before the user asks

        _click(window, _first(row, "replaceConflict"))

        _wait_for(window, lambda: conflicts.count == 0)
        tags = {key.casefold(): list(values) for key, values in FLAC(path).tags.items()}
        assert "key" not in tags and "tempo" not in tags
        assert tags["initialkey"] and tags["bpm"] != ["100"]
        assert tags["mytag"] == ["keep me"]
        repository = cast(Any, cast(Any, workspace)._analysis_model)._service._repository
        stored = repository.get(track_id)
        assert tags["initialkey"] == [stored.key.text("camelot")]
    finally:
        _shutdown(runtime)


def test_dismissing_and_a_failed_replacement_are_shown_in_the_list(qapp, tmp_path: Path) -> None:
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application, AppOptions(data_dir=tmp_path / "data", demo=False, scenario="explorer")
    )
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        workspace = cast(WorkspaceModel, runtime.workspace)
        conflicts = cast(Any, workspace.property("tagConflicts"))
        for index in range(2):
            conflicts.add(
                TagConflict(
                    f"00000000-0000-0000-0000-00000000000{index}",
                    f"ghost{index}.flac",
                    (TagConflictEntry("key", ("KEY", "INITIALKEY"), "8A"),),
                )
            )
        _open_tasks(workspace)
        _wait_for(window, lambda: len(_items(window.contentItem(), "tagConflictRow")) == 2)

        # A file that is not in the library cannot be written: the row says why.
        _settle()
        first = _items(window.contentItem(), "tagConflictRow")[0]
        _click(window, _first(first, "replaceConflict"))
        _wait_for(window, lambda: _error_shown(window))
        assert conflicts.count == 2

        # Dismissing removes one entry without writing anything.
        rows = _items(window.contentItem(), "tagConflictRow")
        _click(window, _first(rows[-1], "dismissConflict"))
        _wait_for(window, lambda: conflicts.count == 1)

        _click(window, _first(window.contentItem(), "dismissAllConflicts"))
        _wait_for(window, lambda: conflicts.count == 0)
        assert not _first_or_none(window, "tagConflictsHeader")
    finally:
        _shutdown(runtime)


def _error_shown(window: QQuickWindow) -> bool:
    return any(
        "no longer in the library" in str(item.property("error") or "")
        for item in _items(window.contentItem(), "tagConflictRow")
    )


def _first_or_none(window: QQuickWindow, name: str) -> bool:
    found = _items(window.contentItem(), name)
    return bool(found) and found[0].isVisible()
