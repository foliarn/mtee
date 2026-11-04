"""Track table at any width: columns that do not fit leave from the right, nothing scrolls,
and the row actions never overlap a column (plan 133.1 and 133.2)."""

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


def _action_cell(row: QQuickItem) -> QQuickItem:
    cells = [item for item in row.findChildren(QQuickItem) if item.objectName() == "trackActions"]
    assert len(cells) == 1
    return cells[0]


def _header_cells(window: QQuickWindow) -> list[QQuickItem]:
    return [
        item
        for item in window.findChildren(QQuickItem)
        if item.objectName().startswith("columnHeader_") and item.isVisible()
    ]


def test_columns_that_do_not_fit_leave_from_the_right_and_nothing_scrolls(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    # Plan 133.1: the table is never wider than the window. Columns that do not fit are hidden
    # for this render; the saved widths stay, and the highlight and the buttons stay in view.
    application, runtime, window, workspace, root_id, track_ids = _started(tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(lambda: row_item(window, 1) is not None, timeout=10_000)
        view = _find(window, "trackListView")
        row = row_item(window, 1)
        assert view is not None and row is not None

        # Make the columns wider than the viewport, as a user would by dragging the headers.
        tab_id = f"folder:{root_id}/"
        workspace.resizeColumn(tab_id, "artist", 640)
        workspace.resizeColumn(tab_id, "fileCreatedAt", 640)
        qtbot.waitUntil(lambda: _find(window, "columnHeader_fileCreatedAt") is None, timeout=5_000)
        assert _find(window, "columnHeader_title") is not None
        assert _find(window, "columnHeader_artist") is not None
        # The saved preference is kept: only the drawing leaves the table.
        assert "fileCreatedAt" in cast(dict, workspace.columnPreferences)["order"]

        track_id = str(cast(dict, row.property("modelData"))["id"])
        assert track_id in track_ids
        like = _find(window, f"trackLike_{track_id}")
        assert like is not None and like.isVisible()
        view_left, view_right = _viewport(window)
        for cell in _header_cells(window):
            assert _span(cell)[1] <= view_right + 0.5, cell.objectName()
        left, right = _span(like)
        assert left >= view_left and right <= view_right

        workspace.selectTrack(track_id, "single", [])
        view.forceActiveFocus()
        frame = _frame(row)
        qtbot.waitUntil(lambda: frame.isVisible(), timeout=5_000)
        assert _span(frame)[1] <= view_right + 0.5
    finally:
        _shutdown(runtime)
        application.quit()


def test_the_action_cell_never_meets_a_column_when_the_window_is_resized(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    # Plan 133.2: stepping the width from the smallest window the app allows (Theme.minWindowWidth,
    # 560 px) to 1 920 px, no column reaches past the window and the action cell (heart, add, info)
    # never overlaps another cell. Narrower windows cannot be reached by the user.
    application, runtime, window, _workspace, _root_id, _track_ids = _started(
        tmp_path, monkeypatch, 3
    )
    try:
        qtbot.waitUntil(lambda: row_item(window, 1) is not None, timeout=10_000)
        for target in [560, 640, 760, 880, 1100, 1280, 1440, 1600, 1920]:
            window.resize(target, 900)
            QTest.qWait(60)
            row = row_item(window, 1)
            assert row is not None
            action_left, action_right = _span(_action_cell(row))
            _view_left, view_right = _viewport(window)
            assert action_right <= view_right + 0.5, target
            for cell in _header_cells(window):
                cell_left, cell_right = _span(cell)
                assert cell_right <= view_right + 0.5, (target, cell.objectName())
                overlaps = cell_left < action_right - 0.5 and action_left < cell_right - 0.5
                assert not overlaps, (target, cell.objectName())
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
        row = row_item(window, 1)
        assert row is not None

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
