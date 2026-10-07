"""Drag audio files onto an Explorer folder with real pointer gestures: they move on disk."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_analysis_ui import _items, _row_id, _rows, _wait_for
from tests.ui.test_track_drag_98 import _center, _drag

from mtee.app import _build_runtime, _shutdown
from mtee.cli import parse_arguments
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)


def _explorer_row(window: QQuickWindow, identity: str) -> QQuickItem:
    return next(row for row in _rows(window) if _row_id(row) == identity)


def _find(window: QQuickWindow, name: str) -> QQuickItem | None:
    found = _items(window.contentItem(), name)
    return found[0] if found else None


def test_files_are_dragged_from_the_list_and_from_the_sidebar(qapp, tmp_path: Path) -> None:
    music = tmp_path / "music"
    for relative in ("Sets/one.wav", "Sets/two.wav", "Sets/three.wav", "Other/four.wav"):
        _write(music / relative)
    data_dir = tmp_path / "data"
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    root = LibraryRepository(database).add_root(music)
    database.close()
    root_id = str(root["id"])

    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(data_dir)]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        workspace = cast(WorkspaceModel, runtime.workspace)
        library = cast(Any, workspace)._library
        _wait_for(window, lambda: len(library.track_ids_in_tree(root_id, "")) == 4)
        workspace.setActivity("explorer")
        workspace.setSidebarVisible(True)
        workspace.toggleFolder(f"root:{root_id}")
        other = f"folder:{root_id}/Other"
        _wait_for(window, lambda: any(_row_id(row) == other for row in _rows(window)))

        owners = {
            name: library.path_owner(music / "Sets" / name) for name in ("one.wav", "two.wav")
        }
        three = library.path_owner(music / "Sets" / "three.wav")

        # 1. From the list in the main page: one file shows a one-line preview.
        workspace.openFolder(f"folder:{root_id}/Sets")
        _wait_for(window, lambda: _find(window, "trackRow_3") is not None)
        QTest.qWait(400)
        rows = [_find(window, f"trackRow_{index}") for index in (1, 2, 3)]
        titles = {
            str(cast(dict, row.property("modelData"))["title"]): row
            for row in rows
            if row is not None
        }
        dragged = titles["one"]
        _drag(
            window,
            _center(dragged),
            _center(_explorer_row(window, other)),
            release=False,
        )
        preview = _find(window, "trackDragPreview")
        assert preview is not None and preview.isVisible()
        assert preview.property("count") == 1
        assert preview.height() == 36
        QTest.mouseRelease(
            window, Qt.MouseButton.LeftButton, pos=_center(_explorer_row(window, other))
        )
        _wait_for(window, lambda: library.track_folder(owners["one.wav"]) == (root_id, "Other"))
        assert (music / "Other" / "one.wav").is_file()
        assert not (music / "Sets" / "one.wav").exists()

        # 2. Several files from the list: the preview keeps its two-line layout.
        QTest.qWait(500)
        workspace.selectTrack(owners["two.wav"], "single", [])
        workspace.selectTrack(three, "toggle", [owners["two.wav"], three])
        rows = [_find(window, f"trackRow_{index}") for index in (1, 2)]
        first = next(row for row in rows if row is not None)
        _drag(window, _center(first), _center(_explorer_row(window, other)), release=False)
        preview = _find(window, "trackDragPreview")
        assert preview is not None and preview.property("count") == 2
        assert preview.height() == 72
        QTest.keyClick(window, Qt.Key.Key_Escape)
        QTest.mouseRelease(
            window, Qt.MouseButton.LeftButton, pos=_center(_explorer_row(window, other))
        )
        QTest.qWait(300)
        assert (music / "Sets" / "two.wav").is_file()  # Escape cancelled the drop
        workspace.clearSelection()

        # 3. From the sidebar: the same preview follows the pointer.
        workspace.toggleFolder(f"folder:{root_id}/Sets")
        _wait_for(window, lambda: any(_row_id(row) == owners["two.wav"] for row in _rows(window)))
        source = _explorer_row(window, owners["two.wav"])
        _drag(window, _center(source), _center(_explorer_row(window, other)), release=False)
        QTest.keyClick(window, Qt.Key.Key_Escape)
        QTest.mouseRelease(
            window, Qt.MouseButton.LeftButton, pos=_center(_explorer_row(window, other))
        )
        QTest.qWait(300)
        assert (music / "Sets" / "two.wav").is_file()  # Escape cancels a sidebar drag too
        source = _explorer_row(window, owners["two.wav"])
        _drag(window, _center(source), _center(_explorer_row(window, other)), release=False)
        side_preview = _find(window, "explorerDragPreview")
        assert side_preview is not None and side_preview.isVisible()
        assert side_preview.property("count") == 1
        assert side_preview.height() == 36
        QTest.mouseRelease(
            window, Qt.MouseButton.LeftButton, pos=_center(_explorer_row(window, other))
        )
        _wait_for(window, lambda: library.track_folder(owners["two.wav"]) == (root_id, "Other"))
        assert (music / "Other" / "two.wav").is_file()
        assert not side_preview.isVisible()
    finally:
        _shutdown(runtime)
