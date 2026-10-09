"""Column resize handle on the track list header: stable drag, clamping, plain click."""

from __future__ import annotations

import time
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtQml import QJSValue
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_player_views import _find, _UiPlayerBackend
from tests.ui.track_list_fixtures import add_folder_tracks, open_folder

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions


def _started(qtbot, tmp_path: Path, monkeypatch, count: int):
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    root_id, _track_ids = add_folder_tracks(runtime, tmp_path / "audio", count)
    workspace = open_folder(runtime, root_id)
    _wait_until_settled(qtbot, workspace)
    return application, runtime, window, workspace


def _wait_until_settled(qtbot, workspace: Any) -> None:
    # The folder list is rebuilt about once after opening; a handle found before that is destroyed.
    seen = {"revision": workspace.revision, "since": time.monotonic()}

    def stable() -> bool:
        if workspace.revision != seen["revision"]:
            seen["revision"] = workspace.revision
            seen["since"] = time.monotonic()
        return time.monotonic() - seen["since"] > 0.5

    qtbot.waitUntil(stable, timeout=10_000)


def _center(item: QQuickItem) -> QPoint:
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    return QPoint(round(point.x()), round(point.y()))


def _stored_width(workspace: Any, key: str) -> int:
    return int(workspace.columnPreferences["widths"][key])


def _local_width(view: QQuickItem, key: str) -> float:
    value = view.property("localColumnWidths")
    if isinstance(value, QJSValue):
        child = value.property(key)
        return child.toNumber() if child.isNumber() else 0.0
    if isinstance(value, dict):
        return float(value.get(key) or 0)
    return 0.0


def test_dragging_the_artist_handle_grows_the_column_by_the_pointer_distance(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, workspace = _started(qtbot, tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(
            lambda: _find(window, "columnResizeHandle_artist") is not None, timeout=10_000
        )
        view = _find(window, "trackListView")
        handle = _find(window, "columnResizeHandle_artist")
        assert view is not None and handle is not None
        before = _stored_width(workspace, "artist")

        start = _center(handle)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
        widths = [float(before)]
        for step in range(1, 7):
            QTest.mouseMove(window, QPoint(start.x() + 10 * step, start.y()), 10)
            QTest.qWait(20)
            widths.append(_local_width(view, "artist"))
        assert view.property("draggedColumnKey") == ""
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=QPoint(start.x() + 60, start.y()))

        steps = [later - earlier for earlier, later in pairwise(widths)]
        assert all(abs(delta - 10) <= 3 for delta in steps), steps
        qtbot.waitUntil(
            lambda: abs(_stored_width(workspace, "artist") - (before + 60)) <= 3, timeout=5_000
        )
        assert abs(_stored_width(workspace, "artist") - before - 60) <= 3
        assert _local_width(view, "artist") == 0
    finally:
        _shutdown(runtime)
        application.quit()


def test_dragging_far_left_stops_at_the_minimum_width(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, workspace = _started(qtbot, tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(
            lambda: _find(window, "columnResizeHandle_artist") is not None, timeout=10_000
        )
        view = _find(window, "trackListView")
        handle = _find(window, "columnResizeHandle_artist")
        assert view is not None and handle is not None

        start = _center(handle)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
        for step in range(1, 11):
            QTest.mouseMove(window, QPoint(start.x() - 50 * step, start.y()), 10)
            QTest.qWait(20)
        QTest.mouseRelease(
            window, Qt.MouseButton.LeftButton, pos=QPoint(start.x() - 500, start.y())
        )

        qtbot.waitUntil(lambda: _stored_width(workspace, "artist") == 44, timeout=5_000)
        assert _stored_width(workspace, "artist") == 44
    finally:
        _shutdown(runtime)
        application.quit()


def test_a_plain_click_on_the_handle_writes_no_width(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, workspace = _started(qtbot, tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(
            lambda: _find(window, "columnResizeHandle_artist") is not None, timeout=10_000
        )
        view = _find(window, "trackListView")
        handle = _find(window, "columnResizeHandle_artist")
        assert view is not None and handle is not None
        before = dict(cast(Any, workspace.columnPreferences)["widths"])

        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=_center(handle))
        QTest.qWait(100)
        assert dict(cast(Any, workspace.columnPreferences)["widths"]) == before
        assert _local_width(view, "artist") == 0
    finally:
        _shutdown(runtime)
        application.quit()
