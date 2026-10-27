"""Qt smoke checks for the prototype scenarios and transitions."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtQuick import QQuickItem, QQuickWindow

from mtee.app import _build_runtime, create_application
from mtee.cli import AppOptions
from mtee.demo.scenarios import SCENARIO_NAMES
from mtee.models.demo_workspace import DemoWorkspace


def _runtime(qapp, tmp_path: Path, scenario: str):
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application,
        AppOptions(data_dir=tmp_path / scenario, demo=True, scenario=scenario),
    )
    assert runtime is not None
    # The offscreen screen is small; review the reference 1440x900 layout.
    window = runtime.engine.rootObjects()[0]
    assert isinstance(window, QQuickWindow)
    window.resize(1440, 900)
    cast(DemoWorkspace, runtime.workspace).loadScenario(
        scenario
    )  # undo the fold applied at the small size
    QCoreApplication.processEvents()
    return application, runtime


def _close(application, runtime) -> None:
    runtime.jobs.shutdown()
    for root in runtime.engine.rootObjects():
        root.deleteLater()
    runtime.engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    runtime.database.close()
    application.quit()


def _find(root: QObject, name: str) -> QQuickItem | None:
    """Search the visual tree: Repeater and Loader items are not QObject children."""
    assert isinstance(root, QQuickWindow)
    pending = [root.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def _visible(root: QObject, name: str) -> bool:
    item = _find(root, name)
    return item is not None and item.isVisible()


@pytest.mark.parametrize("scenario", SCENARIO_NAMES)
def test_every_scenario_loads_the_window(qapp, tmp_path: Path, scenario: str) -> None:
    application, runtime = _runtime(qapp, tmp_path, scenario)
    try:
        QCoreApplication.processEvents()
        root = runtime.engine.rootObjects()[0]
        assert root.objectName() == "mteeWindow"
        assert cast(DemoWorkspace, runtime.workspace).scenarioName == scenario
    finally:
        _close(application, runtime)


def test_the_demo_starts_without_the_convert_plugin(qapp, tmp_path: Path) -> None:
    application, runtime = _runtime(qapp, tmp_path, "tasks")
    try:
        QCoreApplication.processEvents()
        workspace = cast(DemoWorkspace, runtime.workspace)
        assert workspace.pluginUiEnabled is False
        assert workspace.activity == "tasks"
    finally:
        _close(application, runtime)


def test_fullscreen_keeps_the_island_and_restores_the_editor(qapp, tmp_path: Path) -> None:
    application, runtime = _runtime(qapp, tmp_path, "explorer-info")
    try:
        root = runtime.engine.rootObjects()[0]
        QCoreApplication.processEvents()
        assert _visible(root, "playerIsland")
        assert _visible(root, "rightPanel")

        workspace = cast(DemoWorkspace, runtime.workspace)
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        assert _visible(root, "fullscreenPlayer")
        assert _visible(root, "playerIsland")  # fixed and floating, as in normal mode
        assert not _visible(root, "rightPanel")

        workspace.setFullscreen(False)
        QCoreApplication.processEvents()
        assert _visible(root, "playerIsland")
        assert _visible(root, "rightPanel")
        assert workspace.selectedIds == ["dnb03"]
    finally:
        _close(application, runtime)


def test_the_island_setting_hides_the_island(qapp, tmp_path: Path) -> None:
    application, runtime = _runtime(qapp, tmp_path, "settings")
    try:
        root = runtime.engine.rootObjects()[0]
        QCoreApplication.processEvents()
        assert _visible(root, "settingsView")
        cast(DemoWorkspace, runtime.workspace).setIslandEnabled(False)
        QCoreApplication.processEvents()
        assert not _visible(root, "playerIsland")
    finally:
        _close(application, runtime)
