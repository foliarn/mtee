"""The loudness normalization rows of the Playback group, in the live QML window."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.models.demo_workspace import DemoWorkspace


def _first(root: QQuickItem, name: str) -> QQuickItem:
    pending = [root]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    raise AssertionError(f"no QML item named {name}")


def _click(window: QQuickWindow, item: QQuickItem) -> None:
    centre = item.mapToScene(item.boundingRect().center()).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre)
    QTest.qWait(30)


def test_the_playback_group_offers_normalization_on_at_normal(qapp, tmp_path: Path) -> None:
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application, AppOptions(data_dir=tmp_path / "playback", demo=True, scenario="explorer")
    )
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 1500)  # tall enough to show the rows without scrolling
    workspace = cast(DemoWorkspace, runtime.workspace)
    playback = cast(QObject, workspace.property("playbackSettings"))
    try:
        workspace.openSettings()
        QTest.qWait(100)
        view = _first(window.contentItem(), "settingsView")

        assert playback.property("normalizationEnabled") is True
        assert playback.property("normalizationLevel") == "normal"

        toggle = _first(view, "normalizationSetting")
        switch = toggle.mapToScene(QPointF(toggle.width() - 20, toggle.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, switch)
        assert playback.property("normalizationEnabled") is False

        _click(window, _first(_first(view, "normalizationLevelSetting"), "choice_loud"))
        assert playback.property("normalizationLevel") == "loud"
    finally:
        _shutdown(runtime)
