"""Two songs of two folders selected in the Explorer tree: Del, right click, drag (132.3)."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_analysis_ui import _row_id, _rows, _wait_for
from tests.ui.test_plugin_ui import _object
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


def _drag_preview_visible(window: QQuickWindow) -> bool:
    preview = window.findChild(QObject, "explorerDragPreview")
    return preview is not None and bool(preview.property("visible"))


def _row(window: QQuickWindow, identity: str) -> QQuickItem:
    return next(row for row in _rows(window) if _row_id(row) == identity)


def _click(
    window: QQuickWindow,
    item: QQuickItem,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    QTest.mouseClick(window, button, modifiers, _center(item))
    QTest.qWait(60)


def test_songs_of_two_folders_are_selected_and_acted_on_together(qapp, tmp_path: Path) -> None:
    music = tmp_path / "music"
    for relative in ("Sets/one.wav", "Other/two.wav", "Third/keep.wav"):
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
        _wait_for(window, lambda: len(library.track_ids_in_tree(root_id, "")) == 3)
        workspace.setActivity("explorer")
        workspace.setSidebarVisible(True)
        workspace.toggleFolder(f"root:{root_id}")
        sets = f"folder:{root_id}/Sets"
        other = f"folder:{root_id}/Other"
        third = f"folder:{root_id}/Third"
        _wait_for(window, lambda: any(_row_id(row) == third for row in _rows(window)))
        workspace.toggleFolder(sets)
        workspace.toggleFolder(other)
        one = library.path_owner(music / "Sets" / "one.wav")
        two = library.path_owner(music / "Other" / "two.wav")
        _wait_for(window, lambda: any(_row_id(row) == one for row in _rows(window)))
        _wait_for(window, lambda: any(_row_id(row) == two for row in _rows(window)))

        # 1. Ctrl-click on a song of each folder: both are selected, no folder is opened.
        _wait_for(window, lambda: _row(window, one).isVisible() and _row(window, two).isVisible())
        _click(window, _row(window, one), modifiers=Qt.KeyboardModifier.ControlModifier)
        _wait_for(window, lambda: one in cast(list, workspace.selectedIds))
        # The second song is taken only once the tree has rebuilt its rows after the first click.
        _wait_for(window, lambda: two in cast(Any, workspace)._explorer_track_order())
        _click(window, _row(window, two), modifiers=Qt.KeyboardModifier.ControlModifier)
        assert sorted(cast(list, workspace.selectedIds)) == sorted([one, two])

        # 2. Del asks for both songs in the Recycle Bin dialog.
        QTest.keyClick(window, Qt.Key.Key_Delete)
        QTest.qWait(100)
        trash = cast(Any, workspace.trashModel)
        assert sorted(trash._requested_ids) == sorted([one, two])
        # Cancel the modal Recycle Bin dialog: it would block the right click and the drag below.
        QTest.keyClick(window, Qt.Key.Key_Escape)
        QTest.qWait(100)
        assert sorted(trash._requested_ids) == sorted([one, two])

        # 3. Right click on one of the selected songs: the track menu counts both.
        _click(window, _row(window, two), Qt.MouseButton.RightButton)
        menu = _object(window, "explorerTrackMenu")
        assert menu.property("visible") is True
        menu_ids = menu.property("trackIds")
        menu_ids = menu_ids.toVariant() if hasattr(menu_ids, "toVariant") else menu_ids
        assert sorted(cast(list, menu_ids)) == sorted([one, two])
        QTest.keyClick(window, Qt.Key.Key_Escape)
        QTest.qWait(60)

        # 4. Dragging a selected song moves both to a third folder (files on copies).
        _drag(
            window,
            _center(_row(window, one)),
            _center(_row(window, third)),
            release=False,
        )
        _wait_for(window, lambda: _drag_preview_visible(window))
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=_center(_row(window, third)))
        _wait_for(window, lambda: library.track_folder(one) == (root_id, "Third"))
        _wait_for(window, lambda: library.track_folder(two) == (root_id, "Third"))
        assert (music / "Third" / "one.wav").is_file()
        assert (music / "Third" / "two.wav").is_file()
        assert not (music / "Sets" / "one.wav").exists()
        assert not (music / "Other" / "two.wav").exists()
    finally:
        _shutdown(runtime)
