"""The centre window tree of plan 131.7: a split puts two windows side by side, a handle resizes
them, and a drop on a window edge calls the right workspace slot."""

from __future__ import annotations

from typing import Any, cast

import pytest
from PySide6.QtCore import Q_ARG, QMetaObject, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from tests.ui.test_player_views import _find, _UiPlayerBackend

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.models.workspace_model import WorkspaceModel


def _scene_box(item: QQuickItem) -> tuple[float, float, float, float]:
    origin = item.mapToScene(item.boundingRect().topLeft())
    return origin.x(), origin.y(), item.width(), item.height()


def _groups(workspace: WorkspaceModel) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], workspace.groups)


def _layout(workspace: WorkspaceModel) -> dict[str, Any]:
    return cast(dict[str, Any], workspace.centerLayout)


def _windows(root: QQuickWindow) -> list[QQuickItem]:
    found = []
    for index in range(8):
        item = _find(root, f"editorGroup{index}")
        if item is not None:
            found.append(item)
    return found


def test_a_split_makes_two_windows_and_a_drop_on_an_edge_calls_the_slot(
    qapp, qtbot, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = cast(WorkspaceModel, runtime.workspace)
    try:
        workspace.openSettings()
        workspace.openProfile()
        qtbot.waitUntil(lambda: _find(root, "editorGroup0") is not None, timeout=5000)
        first_group = str(workspace.activeGroup)
        tabs = [str(tab["id"]) for tab in _groups(workspace)[0]["tabs"]]
        assert len(tabs) == 2
        assert len(_groups(workspace)) == 1

        # A split on the right: two windows side by side, the tab moves to the new one.
        workspace.splitWithTab(first_group, "right", first_group, tabs[1])
        qtbot.waitUntil(lambda: len(_windows(root)) == 2, timeout=5000)
        left, right = _windows(root)
        left_x, left_y, left_w, left_h = _scene_box(left)
        right_x, right_y, right_w, right_h = _scene_box(right)
        assert left.isVisible() and right.isVisible()
        assert abs(left_y - right_y) < 1
        assert left_x < right_x
        assert right_x - (left_x + left_w) > 0
        assert left_w >= 320 and right_w >= 320
        assert abs(left_h - right_h) < 1
        assert _layout(workspace)["type"] == "split"
        assert _layout(workspace)["orientation"] == "row"

        # A handle drag: the ratios go to setSplitRatios and both windows follow.
        workspace.setSplitRatios([], [0.3, 0.7])
        assert _layout(workspace)["ratios"] == pytest.approx([0.3, 0.7])
        qtbot.waitUntil(
            lambda: abs(_scene_box(_windows(root)[0])[2] - 0.3 * (left_w + right_w)) < 3,
            timeout=5000,
        )
        qtbot.waitUntil(
            lambda: abs(_scene_box(_windows(root)[1])[2] - 0.7 * (left_w + right_w)) < 3,
            timeout=5000,
        )

        # A profile tab (alone in the right window) dropped on the bottom edge of the left window:
        # the tab opens in a new window below the left one and the emptied right window goes away.
        left_group = str(_groups(workspace)[0]["id"])
        right_group = str(_groups(workspace)[1]["id"])
        profile_tab = str(_groups(workspace)[1]["tabs"][0]["id"])
        ok = cast(Any, QMetaObject).invokeMethod(
            _windows(root)[0],
            "dropOn",
            Qt.ConnectionType.DirectConnection,
            Q_ARG("QVariant", "bottom"),
            Q_ARG("QVariant", {"type": "tab", "groupId": right_group, "tabId": profile_tab}),
        )
        assert ok is True
        qtbot.waitUntil(lambda: _layout(workspace)["orientation"] == "column", timeout=5000)
        assert len(_groups(workspace)) == 2
        assert _layout(workspace)["type"] == "split"
        assert _layout(workspace)["orientation"] == "column"
        assert _groups(workspace)[0]["id"] == left_group
        assert [tab["id"] for tab in _groups(workspace)[1]["tabs"]] == [profile_tab]
        assert workspace.activeGroup == _groups(workspace)[1]["id"]
    finally:
        _shutdown(runtime)
