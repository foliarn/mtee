"""Pointer and keyboard gestures on the track list: hit area, focus frames, deselection."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtQml import QJSValue
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_player_views import _find, _UiPlayerBackend
from tests.ui.test_track_drag_98 import _drag
from tests.ui.track_list_fixtures import add_folder_tracks, open_folder, row_item

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions


def _point(scene_point: QPointF) -> QPoint:
    return QPoint(round(scene_point.x()), round(scene_point.y()))


def _track_id(row: QQuickItem) -> str:
    return str(cast(dict, row.property("modelData"))["id"])


def _frame(row: QQuickItem) -> QQuickItem:
    frames = [item for item in row.childItems() if item.objectName() == "trackFocusFrame"]
    assert len(frames) == 1
    return frames[0]


def _frame_visible(row: QQuickItem) -> bool:
    return _frame(row).isVisible()


def _started(tmp_path: Path, monkeypatch, count: int):
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    root_id, track_ids = add_folder_tracks(runtime, tmp_path / "audio", count)
    workspace = open_folder(runtime, root_id)
    return application, runtime, window, workspace, track_ids


def test_left_margin_is_not_part_of_the_row(qapp, qtbot, tmp_path: Path, monkeypatch) -> None:
    application, runtime, window, workspace, track_ids = _started(tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(lambda: row_item(window, 1) is not None, timeout=10_000)
        row = row_item(window, 1)
        assert row is not None
        columns = cast(QJSValue, row.property("columns"))
        padding = columns.property("padding").toInt()
        assert padding > 0

        margin = row.mapToScene(QPointF(padding / 2, row.height() / 2))
        QTest.mouseDClick(window, Qt.MouseButton.LeftButton, pos=_point(margin))
        QTest.qWait(300)
        assert workspace.selectedIds == []
        assert workspace.playingId == ""

        # A single click in the margin clears an existing selection without playing.
        workspace.selectTrack(_track_id(row), "single", [])
        qtbot.waitUntil(lambda: workspace.selectedIds == [_track_id(row)])
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=_point(margin))
        qtbot.waitUntil(lambda: workspace.selectedIds == [], timeout=5_000)
        assert workspace.playingId == ""

        inside = row.mapToScene(QPointF(row.width() / 2, row.height() / 2))
        QTest.mouseDClick(window, Qt.MouseButton.LeftButton, pos=_point(inside))
        qtbot.waitUntil(lambda: workspace.playingId == _track_id(row), timeout=5_000)
        assert workspace.selectedIds == [_track_id(row)]
        assert _track_id(row) in track_ids
    finally:
        _shutdown(runtime)
        application.quit()


def test_selected_rows_share_the_frame_and_escape_or_a_plain_click_clears(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, workspace, track_ids = _started(tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(lambda: row_item(window, 3) is not None, timeout=10_000)
        rows = [row for row in (row_item(window, number) for number in (1, 2, 3)) if row]
        by_id = {_track_id(row): row for row in rows}
        view = _find(window, "trackListView")
        assert view is not None and len(by_id) == 3

        first, second, third = track_ids
        workspace.selectTrack(first, "single", [])
        workspace.selectTrack(second, "toggle", track_ids)
        view.forceActiveFocus()
        qtbot.waitUntil(lambda: _frame_visible(by_id[first]) and _frame_visible(by_id[second]))
        assert not _frame_visible(by_id[third])

        QTest.keyClick(window, Qt.Key.Key_Escape)
        qtbot.waitUntil(lambda: workspace.selectedIds == [])
        assert not any(_frame_visible(row) for row in rows)

        workspace.selectTrack(first, "single", [])
        workspace.selectTrack(second, "toggle", track_ids)
        target = by_id[second].mapToScene(
            QPointF(by_id[second].width() / 2, by_id[second].height() / 2)
        )
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=_point(target))
        qtbot.waitUntil(lambda: workspace.selectedIds == [second])
    finally:
        _shutdown(runtime)
        application.quit()


def test_contiguous_selection_is_framed_as_one_block(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, workspace, track_ids = _started(tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(lambda: row_item(window, 3) is not None, timeout=10_000)
        rows = [cast(QQuickItem, row_item(window, number)) for number in (1, 2, 3)]
        view = _find(window, "trackListView")
        assert view is not None
        first, second, third = track_ids

        # Rows 1 to 3 form one block: only the outer ends get top and bottom edges.
        workspace.selectTrack(first, "single", [])
        workspace.selectTrack(third, "range", track_ids)
        view.forceActiveFocus()
        qtbot.waitUntil(lambda: all(_frame_visible(row) for row in rows), timeout=10_000)
        edges = [
            (_frame(row).property("edgeTop"), _frame(row).property("edgeBottom")) for row in rows
        ]
        assert edges == [(True, False), (False, False), (False, True)]

        # A lone selected row keeps the full frame.
        workspace.selectTrack(second, "single", [])
        qtbot.waitUntil(
            lambda: _frame_visible(rows[1]) and not _frame_visible(rows[0]), timeout=10_000
        )
        assert not _frame_visible(rows[2])
        lone = _frame(rows[1])
        assert (lone.property("edgeTop"), lone.property("edgeBottom")) == (True, True)
    finally:
        _shutdown(runtime)
        application.quit()


def test_drag_position_matches_the_pointer_inside_the_hit_area(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, _workspace, _track_ids = _started(tmp_path, monkeypatch, 3)
    try:
        qtbot.waitUntil(lambda: row_item(window, 1) is not None, timeout=10_000)
        row = row_item(window, 1)
        view = _find(window, "trackListView")
        assert row is not None and view is not None
        start = _point(row.mapToScene(QPointF(row.width() / 2, row.height() / 2)))
        end = QPoint(start.x() - 40, start.y() + 4)

        _drag(window, start, end, release=False)
        qtbot.waitUntil(lambda: view.property("trackDragActive") is True, timeout=5_000)
        expected = view.mapFromScene(QPointF(end.x(), end.y()))
        assert abs(view.property("dragX") - expected.x()) < 1.5
        assert abs(view.property("dragY") - expected.y()) < 1.5

        QTest.keyClick(window, Qt.Key.Key_Escape)
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
        qtbot.waitUntil(lambda: view.property("trackDragActive") is False, timeout=5_000)
    finally:
        _shutdown(runtime)
        application.quit()
