"""The responsive frame and the window shortcuts (plan 131.9 and 131.10): an open dock floats
below 1100 px and closes on a click outside, below 760 px only the focused window is drawn, the
header keeps its controls at 560 px, and Ctrl+1 and Ctrl+Tab act on the windows and the tabs."""

from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import QPoint, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_player_views import _find, _UiPlayerBackend

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.models.workspace_model import WorkspaceModel


def _center(item: QQuickItem) -> QPoint:
    point = item.mapToScene(item.boundingRect().center())
    return QPoint(round(point.x()), round(point.y()))


def _left_edge(item: QQuickItem) -> float:
    return item.mapToScene(item.boundingRect().topLeft()).x()


def _windows(root: QQuickWindow) -> list[QQuickItem]:
    found = []
    for index in range(8):
        item = _find(root, f"editorGroup{index}")
        if item is not None and item.isVisible():
            found.append(item)
    return found


def _groups(workspace: WorkspaceModel) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], workspace.groups)


def _open_runtime(qapp: Any, tmp_path: Any, monkeypatch: Any) -> Any:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    return runtime, root


def test_an_open_dock_floats_below_1100_px_and_a_click_outside_closes_it(
    qapp, qtbot, tmp_path, monkeypatch
) -> None:
    runtime, root = _open_runtime(qapp, tmp_path, monkeypatch)
    workspace = cast(WorkspaceModel, runtime.workspace)
    try:
        root.resize(1440, 900)
        workspace.openToolWindow("explorer", False)
        qtbot.waitUntil(lambda: _find(root, "leftDock") is not None, timeout=5000)
        dock = _find(root, "leftDock")
        left_bar = _find(root, "leftToolBar")
        main = _find(root, "mainArea")
        assert dock is not None and left_bar is not None and main is not None
        qtbot.waitUntil(lambda: dock.width() > 0 and main.width() > 800, timeout=5000)
        # Wide: the dock pushes the centre, so the centre starts well after the bar.
        assert _left_edge(main) - (_left_edge(left_bar) + left_bar.width()) > 200

        # Narrow: the dock floats over the centre, the centre keeps its gap to the bar.
        root.resize(1000, 800)
        qtbot.waitUntil(
            lambda: abs(_left_edge(main) - (_left_edge(left_bar) + left_bar.width()) - 5) < 1,
            timeout=5000,
        )
        assert workspace.dockState("left")["open"] is True

        # A click on the centre, outside the dock, closes the floating dock.
        QTest.mouseClick(root, Qt.MouseButton.LeftButton, pos=_center(main))
        qtbot.waitUntil(lambda: workspace.dockState("left")["open"] is False, timeout=5000)
    finally:
        _shutdown(runtime)


def test_below_760_px_only_the_focused_window_is_drawn_and_wider_shows_both(
    qapp, qtbot, tmp_path, monkeypatch
) -> None:
    runtime, root = _open_runtime(qapp, tmp_path, monkeypatch)
    workspace = cast(WorkspaceModel, runtime.workspace)
    try:
        root.resize(1440, 900)
        workspace.openSettings()
        workspace.openProfile()
        qtbot.waitUntil(lambda: _find(root, "editorGroup0") is not None, timeout=5000)
        first_group = str(workspace.activeGroup)
        profile_tab = str(_groups(workspace)[0]["tabs"][1]["id"])
        workspace.splitWithTab(first_group, "right", first_group, profile_tab)
        qtbot.waitUntil(lambda: len(_windows(root)) == 2, timeout=5000)

        root.resize(700, 800)
        qtbot.waitUntil(lambda: len(_windows(root)) == 1, timeout=5000)

        root.resize(1000, 800)
        qtbot.waitUntil(lambda: len(_windows(root)) == 2, timeout=5000)
    finally:
        _shutdown(runtime)


def test_the_header_hides_back_and_forward_then_the_status_icons_at_560_px(
    qapp, qtbot, tmp_path, monkeypatch
) -> None:
    runtime, root = _open_runtime(qapp, tmp_path, monkeypatch)
    try:
        assert root.property("minimumWidth") == 560
        assert root.property("minimumHeight") == 420
        root.resize(560, 600)
        qtbot.waitUntil(lambda: root.width() == 560, timeout=5000)
        back = _find(root, "navigateBackButton")
        status = _find(root, "statusIcons")
        assert back is not None and status is not None
        assert back.isVisible() is False
        assert status.isVisible() is False
    finally:
        _shutdown(runtime)


def test_ctrl_tab_cycles_the_tabs_of_the_focused_window(qapp, qtbot, tmp_path, monkeypatch) -> None:
    runtime, root = _open_runtime(qapp, tmp_path, monkeypatch)
    workspace = cast(WorkspaceModel, runtime.workspace)
    try:
        root.resize(1440, 900)
        workspace.openSettings()
        workspace.openProfile()
        qtbot.waitUntil(lambda: _find(root, "editorGroup0") is not None, timeout=5000)
        group = _groups(workspace)[0]
        first_tab, second_tab = (str(tab["id"]) for tab in group["tabs"][:2])
        assert workspace.activeGroup == group["id"]
        workspace.activateTab(str(group["id"]), second_tab)
        root.requestActivate()
        qtbot.waitUntil(lambda: root.isActive(), timeout=5000)

        QTest.keyClick(root, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
        qtbot.waitUntil(lambda: _groups(workspace)[0]["active"] == first_tab, timeout=5000)
        QTest.keyClick(root, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
        qtbot.waitUntil(lambda: _groups(workspace)[0]["active"] == second_tab, timeout=5000)
    finally:
        _shutdown(runtime)


def test_ctrl_1_focuses_the_first_centre_window_in_reading_order(
    qapp, qtbot, tmp_path, monkeypatch
) -> None:
    runtime, root = _open_runtime(qapp, tmp_path, monkeypatch)
    workspace = cast(WorkspaceModel, runtime.workspace)
    try:
        root.resize(1440, 900)
        workspace.openSettings()
        workspace.openProfile()
        qtbot.waitUntil(lambda: _find(root, "editorGroup0") is not None, timeout=5000)
        first_group = str(workspace.activeGroup)
        profile_tab = str(_groups(workspace)[0]["tabs"][1]["id"])
        workspace.splitWithTab(first_group, "right", first_group, profile_tab)
        qtbot.waitUntil(lambda: len(_groups(workspace)) == 2, timeout=5000)
        second_group = str(_groups(workspace)[1]["id"])
        workspace.focusGroup(second_group)
        root.requestActivate()
        qtbot.waitUntil(lambda: root.isActive(), timeout=5000)

        QTest.keyClick(root, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
        qtbot.waitUntil(lambda: workspace.activeGroup == first_group, timeout=5000)
        QTest.keyClick(root, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
        qtbot.waitUntil(lambda: workspace.activeGroup == second_group, timeout=5000)
    finally:
        _shutdown(runtime)
