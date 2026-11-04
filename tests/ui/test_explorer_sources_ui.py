"""Removing a source from the library through the Explorer menu, in the live QML window (132.1)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.helpers.analysis_audio import drum_loop, write_wav

from mtee.app import _build_runtime, _shutdown
from mtee.cli import parse_arguments
from mtee.models.workspace_model import WorkspaceModel

_RATE = 44_100


def _items(root: QQuickItem, name: str) -> list[QQuickItem]:
    found: list[QQuickItem] = []
    pending = [root]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            found.append(item)
        pending.extend(item.childItems())
    return found


def _visible(window: QQuickWindow, name: str) -> QQuickItem:
    visible = [item for item in _items(window.contentItem(), name) if item.isVisible()]
    assert len(visible) == 1, f"expected one open entry {name}, found {len(visible)}"
    return visible[0]


def _click(window: QQuickWindow, item: QQuickItem, button=Qt.MouseButton.LeftButton) -> None:
    point = item.mapToScene(item.boundingRect().center()).toPoint()
    QTest.mouseClick(window, button, Qt.KeyboardModifier.NoModifier, point)
    QTest.qWait(30)


def _wait_for(predicate, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    assert predicate()


def test_a_source_is_removed_from_the_library_and_its_files_stay(qapp, tmp_path: Path) -> None:
    music = tmp_path / "music"
    write_wav(music / "Sets" / "one.wav", drum_loop(128.0, 10, rate=_RATE), _RATE)
    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(tmp_path / "data")]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        workspace = cast(WorkspaceModel, runtime.workspace)
        root = workspace.addRoot(str(music))
        library = cast(Any, workspace)._library
        _wait_for(lambda: len(library.track_ids_in_tree(root, "")) == 1)
        track = library.track_ids_in_tree(root, "")[0]

        _wait_for(
            lambda: any(
                str(row.property("modelData").get("id", "")) == f"root:{root}"
                for row in _items(window.contentItem(), "explorerRow")
            )
        )
        row = next(
            row
            for row in _items(window.contentItem(), "explorerRow")
            if str(row.property("modelData").get("id", "")) == f"root:{root}"
        )
        _click(window, row, Qt.MouseButton.RightButton)
        assert _visible(window, "removeRootAction").property("text") == "Remove from library…"
        assert _visible(window, "rescanAction").property("text") == "Rescan"
        assert _visible(window, "newFolderAction").property("text") == "New folder"
        _click(window, _visible(window, "removeRootAction"))

        _click(window, _visible(window, "confirmButton_remove"))

        _wait_for(lambda: library.roots() == [])
        assert library.track(track)["rootId"] in ("", None)
        assert (music / "Sets" / "one.wav").is_file()
        assert "Your files stay on disk" in str(workspace.message)
    finally:
        _shutdown(runtime)
