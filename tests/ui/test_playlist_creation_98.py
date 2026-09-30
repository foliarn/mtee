"""Check the one-click playlist entry point and header controls in real QML."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_player_views import _find, _UiPlayerBackend, _visible

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.playlists_model import PlaylistsModel
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.library_repository import LibraryRepository


def _click(root: QQuickWindow, name: str) -> None:
    item = _find(root, name)
    assert item is not None and item.isVisible()
    point = item.mapToScene(item.boundingRect().center())
    QTest.mouseClick(
        root, Qt.MouseButton.LeftButton, pos=QPoint(round(point.x()), round(point.y()))
    )


def test_menu_creation_count_and_title_edit(qapp, qtbot, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = cast(WorkspaceModel, runtime.workspace)
    playlists = cast(PlaylistsModel, workspace.playlistModel)
    try:
        workspace.setActivity("playlists")
        _click(root, "playlistsPlusButton")
        qtbot.waitUntil(lambda: _visible(root, "newPlaylistMenuItem"))
        resume = root.findChild(QObject, "resumeImportMenuItem")
        assert resume is not None
        assert not resume.property("visible") and resume.property("height") == 0
        first = _find(root, "newPlaylistMenuItem")
        second = _find(root, "newFolderMenuItem")
        third = _find(root, "importPlaylistMenuItem")
        assert first is not None and second is not None and third is not None
        assert abs(second.y() - first.y() - first.height()) < 1
        assert abs(third.y() - second.y() - second.height()) < 1
        _click(root, "newPlaylistMenuItem")
        qtbot.waitUntil(lambda: len(playlists._playlists) == 1, timeout=5000)
        identity = playlists._playlists[0]["id"]
        assert playlists._playlists[0]["name"] == "Untitled playlist 01"
        assert not _visible(root, "playlistNameInput")
        qtbot.waitUntil(lambda: _find(root, "playlistTitleText") is not None)
        _click(root, "playlistTitleText")
        qtbot.waitUntil(lambda: _visible(root, "playlistNameInput"))
        QTest.keyClick(root, Qt.Key.Key_Escape)
        qtbot.waitUntil(lambda: not _visible(root, "playlistNameInput"))
        assert playlists.details(identity)["name"] == "Untitled playlist 01"
        cover_hover = _find(root, "playlistCoverHover")
        assert cover_hover is not None
        hover_point = cover_hover.mapToScene(cover_hover.boundingRect().center())
        QTest.mouseMove(root, QPoint(round(hover_point.x()), round(hover_point.y())))
        qtbot.waitUntil(cover_hover.isVisible)
        QTest.mouseMove(root, QPoint(800, 500))
        qtbot.waitUntil(lambda: not cover_hover.isVisible())

        playlists._pending_imports = [{"operation_id": "review-only"}]
        playlists.changed.emit()
        _click(root, "playlistsPlusButton")
        qtbot.waitUntil(lambda: bool(resume.property("visible")))
        assert resume.property("height") == 28
        QTest.keyClick(root, Qt.Key.Key_Escape)
        playlists._pending_imports = []
        playlists.changed.emit()

        playlists.createUntitled("", [])
        playlists.createUntitled("", [])
        qtbot.waitUntil(lambda: len(playlists._playlists) == 3, timeout=5000)
        assert sorted(p["name"] for p in playlists._playlists) == [
            "Untitled playlist 01",
            "Untitled playlist 02",
            "Untitled playlist 03",
        ]
        playlists.delete(identity)
        qtbot.waitUntil(lambda: len(playlists._playlists) == 2, timeout=5000)
        playlists.createUntitled("", [])
        qtbot.waitUntil(lambda: len(playlists._playlists) == 3, timeout=5000)
        assert sum(p["name"] == "Untitled playlist 03" for p in playlists._playlists) == 2

        audio = tmp_path / "uncertain"
        audio.mkdir()
        path = audio / "unknown.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 24000)
        library = LibraryRepository(runtime.database)
        root_record = library.add_root(audio)
        track_id = library.upsert_location(
            root_record["id"],
            path.name,
            path,
            SourceRevision.observe(path),
            MetadataSnapshot(title=("No credit",), technical=TechnicalInfo(duration_us=3_000_000)),
            0,
        )
        known_path = audio / "known.wav"
        with wave.open(str(known_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 24000)
        known_id = library.upsert_location(
            root_record["id"],
            known_path.name,
            known_path,
            SourceRevision.observe(known_path),
            MetadataSnapshot(
                title=("Known song",),
                artist=("Example",),
                technical=TechnicalInfo(duration_us=3_000_000),
            ),
            0,
        )
        playlists.createUntitled("", [known_id, track_id])
        qtbot.waitUntil(lambda: bool(playlists._ambiguity.get("trackIds")), timeout=5000)
        assert len(playlists._playlists) == 3
        playlists.confirmAmbiguity(False)
        assert len(playlists._playlists) == 3
        playlists.createUntitled("", [known_id, track_id])
        qtbot.waitUntil(lambda: bool(playlists._ambiguity.get("trackIds")), timeout=5000)
        playlists.confirmAmbiguity(True)
        qtbot.waitUntil(lambda: len(playlists._playlists) == 4, timeout=5000)
        assert playlists._playlists[-1]["name"] == "Untitled playlist 04"
    finally:
        _shutdown(runtime)
        application.quit()
