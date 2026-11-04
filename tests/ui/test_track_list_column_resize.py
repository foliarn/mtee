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


def _cell_span(window: QQuickWindow, key: str) -> tuple[float, float]:
    cell = _find(window, f"columnHeader_{key}")
    assert cell is not None
    left = cell.mapToScene(QPointF(0, 0)).x()
    return left, left + cell.width()


def test_the_border_follows_the_pointer_and_the_title_keeps_its_width(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, workspace = _started(qtbot, tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(
            lambda: _find(window, "columnResizeHandle_artist") is not None, timeout=10_000
        )
        handle = _find(window, "columnResizeHandle_artist")
        assert handle is not None
        assert _stored_width(workspace, "title") == 0
        artist_left, artist_right = _cell_span(window, "artist")
        title_left, title_right = _cell_span(window, "title")

        start = _center(handle)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
        for step in range(1, 7):
            QTest.mouseMove(window, QPoint(start.x() + 10 * step, start.y()), 10)
            QTest.qWait(20)
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=QPoint(start.x() + 60, start.y()))

        # The left edge of the dragged column stays, its right edge moves with the pointer.
        qtbot.waitUntil(
            lambda: abs(_cell_span(window, "artist")[1] - (artist_right + 60)) <= 3, timeout=5_000
        )
        assert abs(_cell_span(window, "artist")[0] - artist_left) <= 1
        assert abs(_cell_span(window, "title")[1] - title_right) <= 1
        # The title keeps its drawn width and stays automatic: the drag moves only the border.
        assert (
            abs(
                (title_right - title_left)
                - (_cell_span(window, "title")[1] - _cell_span(window, "title")[0])
            )
            <= 1
        )
        assert _stored_width(workspace, "title") == 0
    finally:
        _shutdown(runtime)
        application.quit()


def test_the_border_can_be_taken_in_the_gap_before_the_next_column(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, workspace = _started(qtbot, tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(
            lambda: _find(window, "columnResizeHandle_artist") is not None, timeout=10_000
        )
        handle = _find(window, "columnResizeHandle_artist")
        next_left, _right = _cell_span(window, "fileCreatedAt")
        assert handle is not None
        before = _stored_width(workspace, "artist")

        # The grab zone is 8 px centred on the border, which sits half a gap before the next column.
        # Three pixels right of the border centre is still inside it.
        grab = QPoint(round(next_left) - 5, _center(handle).y())
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=grab)
        for step in range(1, 5):
            QTest.mouseMove(window, QPoint(grab.x() + 10 * step, grab.y()), 10)
            QTest.qWait(20)
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=QPoint(grab.x() + 40, grab.y()))

        qtbot.waitUntil(
            lambda: abs(_stored_width(workspace, "artist") - (before + 40)) <= 3, timeout=5_000
        )
    finally:
        _shutdown(runtime)
        application.quit()


_HEADER_KEYS = (
    "title",
    "artist",
    "album",
    "genre",
    "bpm",
    "key",
    "duration",
    "format",
    "filename",
    "bitrate",
    "fileCreatedAt",
    "fileModifiedAt",
    "playCount",
    "lastPlayed",
)


def _drawn_headers(window: QQuickWindow) -> list[tuple[str, float, float]]:
    drawn = []
    for key in _HEADER_KEYS:
        cell = _find(window, f"columnHeader_{key}")
        if cell is not None and cell.isVisible():
            left, right = _cell_span(window, key)
            drawn.append((key, left, right))
    return drawn


def test_no_column_passes_the_right_edge_while_a_border_is_dragged(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, _workspace = _started(qtbot, tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(
            lambda: _find(window, "columnResizeHandle_artist") is not None, timeout=10_000
        )
        handle = _find(window, "columnResizeHandle_artist")
        viewport = _find(window, "tableViewport")
        assert handle is not None and viewport is not None

        start = _center(handle)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
        # Far to the right: the artist border would run past the window without the hard limit.
        for step in range(1, 16):
            QTest.mouseMove(window, QPoint(start.x() + 40 * step, start.y()), 10)
            QTest.qWait(20)
        edge = viewport.mapToScene(QPointF(viewport.width(), 0)).x()
        drawn = _drawn_headers(window)
        assert len(drawn) >= 2
        for key, _left, right in drawn:
            assert right <= edge + 1, (key, right, edge)
        QTest.mouseRelease(
            window, Qt.MouseButton.LeftButton, pos=QPoint(start.x() + 600, start.y())
        )
    finally:
        _shutdown(runtime)
        application.quit()


def test_a_double_click_on_a_border_resets_its_column_to_the_default_width(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, workspace = _started(qtbot, tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(
            lambda: _find(window, "columnResizeHandle_artist") is not None, timeout=10_000
        )
        handle = _find(window, "columnResizeHandle_artist")
        assert handle is not None
        workspace.resizeColumn(workspace.activeTabId, "artist", 300)
        QTest.qWait(300)
        assert _stored_width(workspace, "artist") == 300

        QTest.mouseDClick(window, Qt.MouseButton.LeftButton, pos=_center(handle))
        qtbot.waitUntil(lambda: _stored_width(workspace, "artist") == 150, timeout=5_000)
    finally:
        _shutdown(runtime)
        application.quit()
