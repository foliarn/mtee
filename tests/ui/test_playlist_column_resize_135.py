"""Column borders of a playlist track list resize like the folder list (plan 135, item 6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QPoint, Qt
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_player_views import _find, _UiPlayerBackend
from tests.ui.test_track_list_column_resize import _cell_span, _center, _wait_until_settled
from tests.ui.track_list_fixtures import add_folder_tracks

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions


def _playlist_width(workspace: Any, key: str) -> int:
    columns = dict(workspace.playlistModel.columns)
    return int(dict(columns.get("widths", {})).get(key, 0))


def test_a_playlist_border_drag_saves_the_column_width(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        _root_id, track_ids = add_folder_tracks(runtime, tmp_path / "audio", 3)
        assert runtime.jobs.wait_for_done(10_000)
        workspace: Any = runtime.workspace
        playlists = workspace.playlistModel
        workspace.addToNewPlaylist(track_ids)
        qtbot.waitUntil(lambda: len(playlists._playlists) == 1, timeout=5_000)
        workspace.openPlaylist(playlists._playlists[0]["id"])
        _wait_until_settled(qtbot, workspace)
        qtbot.waitUntil(
            lambda: _find(window, "columnResizeHandle_artist") is not None, timeout=10_000
        )
        handle = _find(window, "columnResizeHandle_artist")
        assert handle is not None
        before = _playlist_width(workspace, "artist") or 150

        start = _center(handle)
        artist_left, artist_right = _cell_span(window, "artist")
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
        for step in range(1, 7):
            QTest.mouseMove(window, QPoint(start.x() + 10 * step, start.y()), 10)
            QTest.qWait(20)
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=QPoint(start.x() + 60, start.y()))

        qtbot.waitUntil(
            lambda: abs(_playlist_width(workspace, "artist") - (before + 60)) <= 3, timeout=5_000
        )
        # The drawn column follows too, once the saved width is read back.
        qtbot.waitUntil(
            lambda: abs(_cell_span(window, "artist")[1] - (artist_right + 60)) <= 3, timeout=5_000
        )
        assert abs(_cell_span(window, "artist")[0] - artist_left) <= 1
    finally:
        _shutdown(runtime)
        application.quit()
