"""The Playlists window on NavList (plan 132.4): rows, menus, Liked tracks cover, folder summary."""

from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import QObject, QPoint, Qt, QUrl
from PySide6.QtGui import QColor, QImage
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_player_views import _find, _UiPlayerBackend

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.playlists_model import PlaylistsModel
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.library_repository import LibraryRepository


def _folders(playlists: PlaylistsModel) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], playlists.folders)


def _tree(playlists: PlaylistsModel) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], playlists.tree)


def _right_click(root: QQuickWindow, name: str) -> None:
    item = _find(root, name)
    assert item is not None and item.isVisible(), name
    point = item.mapToScene(item.boundingRect().center())
    QTest.mouseClick(
        root,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(round(point.x()), round(point.y())),
    )


def _menu_ids(root: QQuickWindow) -> list[str]:
    menu = root.findChild(QObject, "playlistsContextMenu")
    assert menu is not None
    ids: list[str] = []
    groups = menu.property("groups")
    groups = groups.toVariant() if hasattr(groups, "toVariant") else groups
    for group in groups or []:
        for item in group["items"]:
            ids.append(str(item["id"]))
            for sub in item.get("submenu") or []:
                ids.append(str(sub["id"]))
    return ids


def test_rows_menus_liked_cover_and_folder_summary(qapp, qtbot, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", lambda: _UiPlayerBackend())
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = cast(WorkspaceModel, runtime.workspace)
    playlists = cast(PlaylistsModel, workspace.playlistModel)
    library = LibraryRepository(runtime.database)
    warnings: list[str] = []
    runtime.engine.warnings.connect(lambda values: warnings.extend(e.toString() for e in values))
    try:
        audio = tmp_path / "audio"
        audio.mkdir()
        record = library.add_root(audio)
        source = audio / "one.wav"
        source.write_bytes(b"RIFF" + b"\x00" * 64)
        track = library.upsert_location(
            record["id"],
            source.name,
            source,
            SourceRevision.observe(source),
            MetadataSnapshot(
                title=("One",), artist=("Test",), technical=TechnicalInfo(duration_us=1_000_000)
            ),
            0,
        )
        workspace.setActivity("playlists")
        playlists.createFolder("Mixes", "")
        qtbot.waitUntil(lambda: len(_folders(playlists)) == 1, timeout=5000)
        folder = _folders(playlists)[0]["id"]
        playlists.create("Night drive", folder, [track])
        qtbot.waitUntil(lambda: len(playlists._playlists) == 1, timeout=5000)
        identity = playlists._playlists[0]["id"]
        qtbot.waitUntil(lambda: not playlists._pending and not playlists._current_job, timeout=5000)
        playlists.toggleFolder(folder)
        qtbot.waitUntil(lambda: not playlists._pending and not playlists._current_job, timeout=5000)
        qtbot.waitUntil(lambda: _find(root, "navRow_" + identity) is not None, timeout=5000)

        # Folders and playlists are rows of the same height; Liked tracks comes first.
        folder_row = _find(root, "navRow_" + folder)
        playlist_row = _find(root, "navRow_" + identity)
        liked_row = _find(root, "navRow_liked")
        assert folder_row is not None and playlist_row is not None and liked_row is not None
        assert folder_row.property("height") == playlist_row.property("height") == 52

        # The default cover of Liked tracks is the heart; a playlist without a cover shows its note.
        assert playlists.details("liked")["coverUrl"] == ""

        # Menus (P7): a folder, a playlist and Liked tracks each list their own entries.
        _right_click(root, "navRow_" + folder)
        qtbot.waitUntil(lambda: "newPlaylist" in _menu_ids(root), timeout=5000)
        assert {"newPlaylist", "newFolder", "rename", "deleteFolder"} <= set(_menu_ids(root))
        assert "play" not in _menu_ids(root)
        QTest.keyClick(root, Qt.Key.Key_Escape)

        _right_click(root, "navRow_" + identity)
        qtbot.waitUntil(lambda: "moveTo" in _menu_ids(root), timeout=5000)
        assert {
            "play",
            "enqueue",
            "edit",
            "cover",
            "duplicate",
            "pin",
            "moveTo",
            "export",
            "delete",
        } <= set(_menu_ids(root))
        assert "move:" + folder in _menu_ids(root)
        QTest.keyClick(root, Qt.Key.Key_Escape)

        _right_click(root, "navRow_liked")
        qtbot.waitUntil(lambda: "cover" in _menu_ids(root), timeout=5000)
        assert _menu_ids(root) == ["play", "enqueue", "cover"]
        QTest.keyClick(root, Qt.Key.Key_Escape)

        # A playlist dragged onto another folder row moves into that folder (plan 132.4).
        playlists.createFolder("Other", "")
        qtbot.waitUntil(lambda: len(_folders(playlists)) == 2, timeout=5000)
        other = next(f["id"] for f in _folders(playlists) if f["name"] == "Other")
        qtbot.waitUntil(lambda: _find(root, "navRow_" + other) is not None, timeout=5000)
        dragged = _find(root, "navRow_" + identity)
        assert dragged is not None
        start = dragged.mapToScene(dragged.boundingRect().center())
        target = _find(root, "navRow_" + other)
        assert target is not None
        end = target.mapToScene(target.boundingRect().center())
        QTest.mousePress(
            root, Qt.MouseButton.LeftButton, pos=QPoint(round(start.x()), round(start.y()))
        )
        for step in range(1, 21):
            point = start + (end - start) * (step / 20)
            QTest.mouseMove(root, QPoint(round(point.x()), round(point.y())), 10)
        assert target.property("dropTarget") is True
        QTest.mouseRelease(
            root, Qt.MouseButton.LeftButton, pos=QPoint(round(end.x()), round(end.y()))
        )
        qtbot.waitUntil(lambda: playlists._playlists[0]["folder"] == other, timeout=5000)

        # Liked tracks keeps a cover of its own, and goes back to the heart when it is reset.
        cover = tmp_path / "liked.png"
        image = QImage(300, 300, QImage.Format.Format_RGB32)
        image.fill(QColor("#256f82"))
        assert image.save(str(cover))
        playlists.setCover("liked", QUrl.fromLocalFile(str(cover)).toString())
        qtbot.waitUntil(lambda: bool(playlists.details("liked")["coverUrl"]), timeout=5000)
        assert _tree(playlists)[0]["coverUrl"] == playlists.details("liked")["coverUrl"]
        playlists.setCover("liked", "")
        qtbot.waitUntil(lambda: playlists.details("liked")["coverUrl"] == "", timeout=5000)
        cover.unlink()

        # The summary decides whether a folder delete asks: a folder with a playlist is not empty.
        # The playlist moved into Other, so Mixes is empty and Other holds one playlist.
        assert playlists.folderSummary(folder)["empty"] is True
        summary = playlists.folderSummary(other)
        assert summary == {"folders": 0, "playlists": 1, "allPlaylists": 1, "empty": False}

        assert not warnings, warnings
    finally:
        _shutdown(runtime)
