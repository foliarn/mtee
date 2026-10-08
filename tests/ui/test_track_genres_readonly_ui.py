"""The local genre result is visible in real list rows and Info, without audio edits."""

from pathlib import Path
from typing import cast

from PySide6.QtQuick import QQuickWindow
from tests.integration.test_genre_seed import fixture_library
from tests.ui.test_analysis_ui import _items, _wait_for

from mtee.app import _build_runtime, _destroy_windows, _shutdown
from mtee.cli import parse_arguments
from mtee.models.workspace_model import WorkspaceModel
from mtee.services.genre_seed_service import GenreSeedService
from mtee.services.player_backend import PlayerBackendError


def test_seeded_local_genres_are_readable_in_list_and_info(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    def unavailable_backend():
        raise PlayerBackendError("Audio is not required for the local genre display test")

    monkeypatch.setattr("mtee.app.MpvBackend", unavailable_backend)
    path, root, ids = fixture_library(tmp_path)
    service = GenreSeedService(path)
    service.apply(service.preview(root))
    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(path.parent)]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        workspace = cast(WorkspaceModel, runtime.workspace)
        workspace.openFolder(f"folder:{root}/house")
        _wait_for(
            window,
            lambda: any(
                item.isVisible() and item.property("text") == "MTEE genres: House"
                for item in _items(window.contentItem(), "trackLocalGenres")
            ),
        )
        workspace.selectTrack(ids[1])
        workspace.showRightPanel("info")
        _wait_for(
            window,
            lambda: any(
                item.isVisible() and item.property("text") == "House"
                for item in _items(window.contentItem(), "infoLocalGenres")
            ),
        )
        assert workspace.track(ids[1])["mteeGenres"] == ["House"]
        assert not workspace.isPlaying
    finally:
        _shutdown(runtime)
        _destroy_windows(runtime)
