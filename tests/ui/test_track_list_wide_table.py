"""Wide track table: highlight stops at the visible edge and the row actions stay in view."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QPointF
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_player_views import _find, _UiPlayerBackend
from tests.ui.track_list_fixtures import add_folder_tracks, open_folder, row_item

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions


def _started(tmp_path: Path, monkeypatch, count: int):
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    root_id, track_ids = add_folder_tracks(runtime, tmp_path / "audio", count)
    workspace = open_folder(runtime, root_id)
    return application, runtime, window, workspace, root_id, track_ids


def _span(item: QQuickItem) -> tuple[float, float]:
    left = item.mapToScene(QPointF(0, 0)).x()
    return left, left + item.width()


def _viewport(window: QQuickWindow) -> tuple[float, float]:
    viewport = _find(window, "tableViewport")
    assert viewport is not None
    return _span(viewport)


def _frame(row: QQuickItem) -> QQuickItem:
    frames = [item for item in row.childItems() if item.objectName() == "trackFocusFrame"]
    assert len(frames) == 1
    return frames[0]


def test_actions_stay_visible_and_highlight_stops_at_the_viewport_edge(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, workspace, root_id, track_ids = _started(tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(lambda: row_item(window, 1) is not None, timeout=10_000)
        viewport = _find(window, "tableViewport")
        view = _find(window, "trackListView")
        row = row_item(window, 1)
        assert viewport is not None and view is not None and row is not None

        # Make the columns wider than the viewport, as a user would by dragging the headers.
        tab_id = f"folder:{root_id}/"
        workspace.resizeColumn(tab_id, "artist", 640)
        workspace.resizeColumn(tab_id, "fileCreatedAt", 640)
        qtbot.waitUntil(
            lambda: viewport.property("contentWidth") > viewport.property("width") + 200,
            timeout=5_000,
        )

        track_id = str(cast(dict, row.property("modelData"))["id"])
        assert track_id in track_ids
        like = _find(window, f"trackLike_{track_id}")
        assert like is not None and like.isVisible()

        def like_visible() -> bool:
            left, right = _span(like)
            view_left, view_right = _viewport(window)
            return left >= view_left and right <= view_right

        qtbot.waitUntil(like_visible, timeout=5_000)

        # The selected row's frame ends at the visible edge, not at the wide table's end.
        workspace.selectTrack(track_id, "single", [])
        view.forceActiveFocus()
        frame = _frame(row)
        qtbot.waitUntil(lambda: frame.isVisible(), timeout=5_000)
        _view_left, view_right = _viewport(window)
        assert _span(frame)[1] <= view_right + 0.5

        # Scroll the columns sideways: the actions stay at the visible right edge.
        max_x = viewport.property("contentWidth") - viewport.property("width")
        viewport.setProperty("contentX", min(max_x, 300.0))
        qtbot.waitUntil(lambda: abs(viewport.property("contentX") - min(max_x, 300.0)) < 0.5)
        qtbot.waitUntil(like_visible, timeout=5_000)
        assert _span(frame)[1] <= _viewport(window)[1] + 0.5
        QTest.qWait(50)
        assert like_visible()
    finally:
        _shutdown(runtime)
        application.quit()


def test_actions_keep_their_natural_place_when_the_table_fits(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, _workspace, _root_id, _track_ids = _started(
        tmp_path, monkeypatch, 3
    )
    try:
        qtbot.waitUntil(lambda: row_item(window, 1) is not None, timeout=10_000)
        viewport = _find(window, "tableViewport")
        row = row_item(window, 1)
        assert viewport is not None and row is not None
        assert viewport.property("contentWidth") <= viewport.property("width") + 0.5

        # No overflow: the rightmost action (add to playlist) ends at the row's padded right edge.
        track_id = str(cast(dict, row.property("modelData"))["id"])
        add = _find(window, f"trackAdd_{track_id}")
        assert add is not None
        columns = row.property("columns")
        padding = columns.property("padding").toInt()
        _left, right = _span(add)
        _row_left, row_right = _span(row)
        assert abs(right - (row_right - padding)) <= 1.5
    finally:
        _shutdown(runtime)
        application.quit()
