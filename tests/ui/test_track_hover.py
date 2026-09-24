"""Track actions remain visible while the pointer crosses their boundaries."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.app import _build_runtime, create_application
from mtee.cli import AppOptions
from mtee.models.demo_workspace import DemoWorkspace


def _find(root: QQuickWindow, name: str) -> QQuickItem | None:
    pending = [root.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def _point(item: QQuickItem):
    return item.mapToScene(item.boundingRect().center()).toPoint()


def _find_within(parent: QQuickItem, name: str) -> QQuickItem | None:
    pending = list(parent.childItems())
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def test_hover_stays_active_across_track_actions(qapp, tmp_path) -> None:
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application,
        AppOptions(data_dir=tmp_path / "hover", demo=True, scenario="explorer"),
    )
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = runtime.workspace
    assert isinstance(workspace, DemoWorkspace)
    QCoreApplication.processEvents()

    try:
        row = _find(root, "trackRow")
        assert row is not None
        play = _find_within(row, "trackPlayButton")
        info = _find_within(row, "trackInfoButton")
        assert play is not None and info is not None
        assert not info.isVisible()
        QTest.mouseMove(root, _point(play))
        QTest.qWait(80)
        assert info.isVisible()
        QTest.mouseMove(root, _point(info), 50)
        QTest.qWait(80)
        assert info.isVisible()
        QTest.mouseMove(root, _point(play), 50)
        QTest.qWait(80)
        assert info.isVisible()
        for _ in range(5):
            QTest.qWait(50)
            QCoreApplication.processEvents()
            assert info.isVisible()

        previous_track = workspace.playingId
        QTest.mouseClick(root, Qt.MouseButton.LeftButton, pos=_point(play))
        QCoreApplication.processEvents()
        assert workspace.playingId
        assert workspace.playingId != previous_track
    finally:
        runtime.jobs.shutdown()
        for item in runtime.engine.rootObjects():
            item.deleteLater()
        runtime.engine.deleteLater()
        QCoreApplication.processEvents()
        runtime.database.close()
        application.quit()
