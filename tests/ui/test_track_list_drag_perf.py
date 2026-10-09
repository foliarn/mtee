"""Starting a drag over a large selection answers well within one interaction."""

from __future__ import annotations

import time
from pathlib import Path
from typing import cast

from PySide6.QtCore import Q_ARG
from PySide6.QtQuick import QQuickWindow
from tests.ui.test_player_views import _find, _UiPlayerBackend
from tests.ui.track_list_fixtures import add_folder_tracks, invoke_slot, open_folder, row_item

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions


def test_prepare_drag_over_six_hundred_selected_rows_is_fast(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        root_id, track_ids = add_folder_tracks(runtime, tmp_path / "audio", 600)
        workspace = open_folder(runtime, root_id)
        qtbot.waitUntil(lambda: row_item(window, 3) is not None, timeout=10_000)
        workspace.selectAll(track_ids)

        view = _find(window, "trackListView")
        row = row_item(window, 3)
        assert view is not None and row is not None
        track = cast(dict, row.property("modelData"))

        started = time.perf_counter()
        assert invoke_slot(
            view, "prepareTrackDrag", Q_ARG("QVariant", row), Q_ARG("QVariant", track)
        )
        elapsed = time.perf_counter() - started

        assert elapsed < 0.4, f"prepareTrackDrag took {elapsed:.3f}s"
        assert view.property("dragCount") == 600
        assert view.property("trackDragActive") is True

        assert invoke_slot(view, "cancelTrackDrag")
        assert view.property("trackDragActive") is False
    finally:
        _shutdown(runtime)
        application.quit()
