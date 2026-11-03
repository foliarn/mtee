"""The one track menu of plan 130: its groups, the Explorer tree, and Rename file on copies."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_analysis_ui import _items, _row_id, _rows, _wait_for
from tests.ui.test_plugin_ui import _object

from mtee.app import _build_runtime, _shutdown
from mtee.cli import parse_arguments
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository

_TRACK_MENU_ORDER = [
    "Add to queue",
    "Add to playlist…",
    "Analyze",
    "Edit info",
    "Open in Windows Explorer",
    "Rename file…",
    "Delete file…",
]


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)


def _start(qapp, tmp_path: Path):
    music = tmp_path / "music"
    for relative in ("Sets/one.wav", "Sets/two.wav", "Other/three.wav"):
        _write(music / relative)
    data_dir = tmp_path / "data"
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    root = LibraryRepository(database).add_root(music)
    database.close()
    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(data_dir)]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    workspace = cast(WorkspaceModel, runtime.workspace)
    library = cast(Any, workspace)._library
    root_id = str(root["id"])
    _wait_for(window, lambda: len(library.track_ids_in_tree(root_id, "")) == 3)
    workspace.setActivity("explorer")
    workspace.setSidebarVisible(True)
    return runtime, window, workspace, library, music, root_id


def _entries(menu: QObject) -> list[QQuickItem]:
    content = cast(QQuickItem, menu.property("contentItem"))
    return sorted(content.childItems()[0].childItems(), key=lambda item: item.y())


def _labels(menu: QObject) -> list[str]:
    return [
        str(item.property("text"))
        for item in _entries(menu)
        if item.property("text") and item.isVisible() and item.height() > 0
    ]


def _separators(menu: QObject) -> int:
    return sum(
        1
        for item in _entries(menu)
        if not item.property("text") and item.isVisible() and item.height() > 0
    )


def _right_click(window: QQuickWindow, item: QQuickItem) -> None:
    QTest.mouseClick(
        window,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
        item.mapToScene(item.boundingRect().center()).toPoint(),
    )
    QTest.qWait(150)


def _item(window: QQuickWindow, name: str) -> QQuickItem:
    found = _items(window.contentItem(), name)
    assert found, f"no QML item named {name}"
    return found[0]


def test_the_folder_list_menu_has_the_groups_of_the_new_order(qapp, tmp_path: Path) -> None:
    runtime, window, workspace, _library, _music, root_id = _start(qapp, tmp_path)
    try:
        workspace.openFolder(f"folder:{root_id}/Sets")
        _wait_for(window, lambda: bool(_items(window.contentItem(), "trackRow_1")))
        QTest.qWait(300)
        _right_click(window, _item(window, "trackRow_1"))
        menu = _object(window, "trackContextMenu")
        labels = _labels(menu)
        assert labels == _TRACK_MENU_ORDER
        # Four groups: queue and playlist, tools, and the files (no artist, folder list).
        assert _separators(menu) == 2
        assert "Play" not in labels and "Move up" not in labels and "Move down" not in labels
        assert "Show in folder" not in labels  # the list is the track's own folder
        QTest.keyClick(window, Qt.Key.Key_Escape)
    finally:
        _shutdown(runtime)


def test_a_track_of_the_explorer_tree_opens_the_same_menu(qapp, tmp_path: Path) -> None:
    runtime, window, workspace, library, music, root_id = _start(qapp, tmp_path)
    try:
        workspace.toggleFolder(f"root:{root_id}")
        sets = f"folder:{root_id}/Sets"
        _wait_for(window, lambda: any(_row_id(row) == sets for row in _rows(window)))
        workspace.toggleFolder(sets)
        one = library.path_owner(music / "Sets" / "one.wav")
        _wait_for(window, lambda: any(_row_id(row) == one for row in _rows(window)))
        row = next(row for row in _rows(window) if _row_id(row) == one)
        _right_click(window, row)
        labels = _labels(_object(window, "explorerTrackMenu"))
        assert labels == _TRACK_MENU_ORDER
        QTest.keyClick(window, Qt.Key.Key_Escape)
    finally:
        _shutdown(runtime)


def test_rename_file_renames_a_copy_on_disk_and_refuses_an_existing_name(
    qapp, tmp_path: Path
) -> None:
    runtime, window, workspace, library, music, root_id = _start(qapp, tmp_path)
    try:
        workspace.openFolder(f"folder:{root_id}/Sets")
        _wait_for(window, lambda: bool(_items(window.contentItem(), "trackRow_1")))
        QTest.qWait(300)
        one = library.path_owner(music / "Sets" / "one.wav")
        two = library.path_owner(music / "Sets" / "two.wav")

        # The menu asks for the name in a dialog; the field starts on the current name.
        workspace.requestRenameFile(one)
        QTest.qWait(200)
        field = _item(window, "renameFileField")
        assert field.property("text") == "one"
        field.setProperty("text", "two")
        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            _item(window, "confirmButton_rename")
            .mapToScene(_item(window, "confirmButton_rename").boundingRect().center())
            .toPoint(),
        )
        QTest.qWait(300)
        assert runtime.jobs.wait_for_done(20_000)
        QTest.qWait(200)
        # Refused: the other file has this name. Nothing changed on disk.
        assert (music / "Sets" / "one.wav").is_file() and (music / "Sets" / "two.wav").is_file()
        assert "already exists" in cast(str, workspace.message)

        workspace.renameTrackFile(one, "Renamed song")
        assert runtime.jobs.wait_for_done(20_000)
        QTest.qWait(300)
        assert not (music / "Sets" / "one.wav").exists()
        assert (music / "Sets" / "Renamed song.wav").is_file()
        assert library.path_owner(music / "Sets" / "Renamed song.wav") == one
        assert "Renamed" in cast(str, workspace.message)
        _wait_for(
            window,
            lambda: (
                "Renamed song"
                in [
                    str(cast(dict, row.property("modelData")).get("title", ""))
                    for row in _rows_of_list(window)
                ]
            ),
        )
        assert two == library.path_owner(music / "Sets" / "two.wav")
    finally:
        _shutdown(runtime)


def _rows_of_list(window: QQuickWindow) -> list[QQuickItem]:
    return [
        item
        for number in range(1, 8)
        for item in _items(window.contentItem(), f"trackRow_{number}")
    ]
