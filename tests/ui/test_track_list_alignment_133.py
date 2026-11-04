"""Cell alignment of the track list (plan 133.4, decision 130 U19).

Text is anchored to the left edge of its column and numbers to the right edge; the Key badge stays
at the left when its column widens.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QPointF
from PySide6.QtQuick import QQuickItem, QQuickWindow
from tests.ui.test_track_list_column_resize import _cell_span, _started, _wait_until_settled

from mtee.app import _shutdown


def _visible_named(window: QQuickWindow, name: str) -> QQuickItem | None:
    """The first drawn item with this object name (a row can hold several of the same name)."""
    pending = [window.contentItem()]
    while pending:
        item = cast(QQuickItem, pending.pop())
        if item.objectName() == name and item.isVisible():
            return item
        pending.extend(item.childItems())
    return None


def _scene_x(item: QQuickItem, x: float = 0.0) -> float:
    return item.mapToScene(QPointF(x, 0)).x()


def test_the_key_badge_stays_at_the_left_of_a_widened_column(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, workspace = _started(qtbot, tmp_path, monkeypatch, 3)
    try:
        workspace.resizeColumn(workspace.activeTabId, "key", 200)
        _wait_until_settled(qtbot, workspace)
        qtbot.waitUntil(lambda: _visible_named(window, "cell_key") is not None, timeout=5_000)
        badge = _visible_named(window, "cell_key")
        assert badge is not None

        left, right = _cell_span(window, "key")
        assert abs((right - left) - 200) <= 1
        assert abs(_scene_x(badge) - left) <= 1
    finally:
        _shutdown(runtime)
        application.quit()


def test_numbers_end_at_the_right_edge_and_text_starts_at_the_left_edge(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    application, runtime, window, workspace = _started(qtbot, tmp_path, monkeypatch, 3)
    try:
        workspace.toggleColumn(workspace.activeTabId, "duration")
        _wait_until_settled(qtbot, workspace)
        qtbot.waitUntil(lambda: _visible_named(window, "cell_duration") is not None, timeout=5_000)
        duration = _visible_named(window, "cell_duration")
        bpm = _visible_named(window, "cell_bpm")
        artist = _visible_named(window, "cell_artist")
        assert duration is not None and bpm is not None and artist is not None

        _left, duration_right = _cell_span(window, "duration")
        assert abs(_scene_x(duration) + duration.width() - duration_right) <= 1
        _bpm_left, bpm_right = _cell_span(window, "bpm")
        assert abs(_scene_x(bpm) + bpm.width() - bpm_right) <= 1
        artist_left, _artist_right = _cell_span(window, "artist")
        assert abs(_scene_x(artist) - artist_left) <= 1
    finally:
        _shutdown(runtime)
        application.quit()
