from __future__ import annotations

import os
import wave
from pathlib import Path
from typing import Any, cast

import pytest
from PySide6.QtCore import QMetaObject, QPoint, Qt, QUrl
from PySide6.QtGui import QColor, QImage
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_player_views import _find, _UiPlayerBackend, _visible

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.playlists_model import PlaylistsModel
from mtee.models.track_list_model import TrackListModel
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository


def _click(root: QQuickWindow, name: str) -> None:
    item = _find(root, name)
    assert item is not None and item.isVisible(), name
    point = item.mapToScene(item.boundingRect().center())
    QTest.mouseClick(
        root,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(round(point.x()), round(point.y())),
    )


@pytest.mark.parametrize("early_schema_16", [False, True])
def test_create_add_like_search_visible_playback_and_reload(
    qapp, qtbot, tmp_path, monkeypatch, early_schema_16
):
    backend = _UiPlayerBackend()
    monkeypatch.setattr("mtee.app.MpvBackend", lambda: backend)
    application = create_application(["mtee"])
    if early_schema_16:
        legacy_migrations = tmp_path / "schema-v16"
        legacy_migrations.mkdir()
        for migration in Database(tmp_path / "unused.sqlite3").migrations:
            if migration.version <= 16:
                sql = migration.read_sql()
                if migration.version == 16:
                    sql = sql.split("CREATE TABLE playlist_imports (")[0]
                (legacy_migrations / migration.file_name).write_text(sql, encoding="utf-8")
        database = Database(tmp_path / "data" / "mtee.sqlite3", migrations_dir=legacy_migrations)
        database.migrate()
        database.close()
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = cast(WorkspaceModel, runtime.workspace)
    playlists = cast(PlaylistsModel, workspace.playlistModel)
    library = LibraryRepository(runtime.database)
    warnings = []
    runtime.engine.warnings.connect(lambda values: warnings.extend(e.toString() for e in values))
    try:
        audio = tmp_path / "audio"
        audio.mkdir()
        record = library.add_root(audio)
        identities = []
        for index, title in enumerate(["Northline", "Horizon"]):
            source = audio / f"{index}.wav"
            with wave.open(str(source), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(8000)
                handle.writeframes(b"\x00\x00" * 24000)
            identities.append(
                library.upsert_location(
                    record["id"],
                    source.name,
                    source,
                    SourceRevision.observe(source),
                    MetadataSnapshot(
                        title=(title,),
                        artist=("Test artist",),
                        technical=TechnicalInfo(duration_us=3_000_000),
                    ),
                    0,
                )
            )
        workspace.addToNewPlaylist(identities)
        qtbot.waitUntil(lambda: _visible(root, "playlistNameInput"))
        field = _find(root, "playlistNameInput")
        assert field is not None
        field.setProperty("text", "Night drive")
        _click(root, "playlistFormSave")
        qtbot.waitUntil(lambda: len(playlists._playlists) == 1, timeout=5000)
        identity = playlists._playlists[0]["id"]
        workspace.setActivity("playlists")
        qtbot.waitUntil(lambda: _find(root, "playlistPlay") is not None, timeout=5000)
        tab_id = "playlist:" + identity
        model = cast(
            TrackListModel, workspace.trackModelForTab(tab_id, "playlist", identity, "index", True)
        )
        qtbot.waitUntil(lambda: model.count == 2, timeout=5000)
        assert [r["trackId"] for r in model.rows_snapshot()] == identities
        assert model.trackIds != identities
        folder_widths = dict(workspace._column_preferences["widths"])
        workspace.resizeColumn(tab_id, "artist", 210)
        qtbot.waitUntil(lambda: playlists._columns["widths"]["artist"] == 210)
        assert workspace._column_preferences["widths"] == folder_widths
        workspace.moveColumn(tab_id, "duration", -1)
        qtbot.waitUntil(lambda: playlists._columns["order"][-1] == "key")
        playlists.setCreator("Local curator")
        qtbot.waitUntil(lambda: playlists.creator == "Local curator")
        cover = tmp_path / "cover.png"
        image = QImage(500, 500, QImage.Format.Format_RGB32)
        image.fill(QColor("#256f82"))
        assert image.save(str(cover))
        playlists.setCover(identity, QUrl.fromLocalFile(str(cover)).toString())
        qtbot.waitUntil(lambda: bool(playlists.details(identity)["coverUrl"]))
        cover.unlink()
        assert Path(QUrl(playlists.details(identity)["coverUrl"]).toLocalFile()).is_file()
        QTest.qWait(200)
        capture = os.environ.get("MTEE_PLAYLIST_CAPTURE")
        if capture:
            Path(capture).mkdir(parents=True, exist_ok=True)
            assert root.grabWindow().save(str(Path(capture) / "playlist.png"))
        _click(root, "playlistSearchButton")
        field = _find(root, "playlistSearchField")
        assert field is not None
        field.forceActiveFocus()
        for character in "northline":
            QTest.keyClick(root, ord(character.upper()), Qt.KeyboardModifier.NoModifier)
        qtbot.waitUntil(lambda: model.count == 1, timeout=5000)
        _click(root, "playlistPlay")
        qtbot.waitUntil(lambda: workspace.playingId == identities[0], timeout=5000)
        assert runtime.player_service is not None
        assert [r["id"] for r in runtime.player_service.queue_rows()] == [identities[0]]
        _click(root, "playlistSearchButton")
        assert str(field.property("text")).casefold() == "northline"
        playlists.create("Archive", "", [])
        qtbot.waitUntil(lambda: len(playlists._playlists) == 2, timeout=5000)
        target = next(p["id"] for p in playlists._playlists if p["name"] == "Archive")
        workspace.openPlaylist(identity)
        qtbot.waitUntil(lambda: model.count == 1, timeout=5000)
        entry_id = model.rows_snapshot()[0]["id"]
        qtbot.waitUntil(lambda: _find(root, "trackAdd_" + entry_id) is not None, timeout=5000)
        _click(root, "trackAdd_" + entry_id)
        qtbot.waitUntil(lambda: _find(root, "playlistMenuEntry_" + target) is not None)
        _click(root, "playlistMenuEntry_" + target)
        qtbot.waitUntil(lambda: target in playlists.containing(identities[0]))
        assert _visible(root, "playlistMenuSearch")
        if capture:
            QTest.qWait(200)
            assert root.grabWindow().save(str(Path(capture) / "add-menu.png"))
        _click(root, "playlistMenuEntry_" + target)
        qtbot.waitUntil(lambda: target not in playlists.containing(identities[0]))
        assert _visible(root, "playlistMenuSearch")
        QTest.keyClick(root, Qt.Key.Key_Escape)
        qtbot.waitUntil(
            lambda: (
                _find(root, "playlistMenuSearch") is None
                or not _visible(root, "playlistMenuSearch")
            )
        )
        add = _find(root, "trackAdd_" + entry_id)
        assert add is not None
        row = add
        while not row.objectName().startswith("trackRow_"):
            row = row.parentItem()
            assert row is not None
        target_item = _find(root, "playlistNode_" + target)
        assert target_item is not None
        start = row.mapToScene(row.boundingRect().center())
        end = target_item.mapToScene(target_item.boundingRect().center())
        QTest.mousePress(
            root, Qt.MouseButton.LeftButton, pos=QPoint(round(start.x()), round(start.y()))
        )
        for step in range(1, 21):
            point = start + (end - start) * (step / 20)
            QTest.mouseMove(root, QPoint(round(point.x()), round(point.y())), 10)
        QTest.mouseRelease(
            root, Qt.MouseButton.LeftButton, pos=QPoint(round(end.x()), round(end.y()))
        )
        qtbot.waitUntil(lambda: target in playlists.containing(identities[0]))
        playlists.toggleLike(identities[0])
        qtbot.waitUntil(lambda: playlists.isLiked(identities[0]), timeout=5000)
        workspace.selectTrack(model.rows_snapshot()[0]["id"], "single", [])
        assert workspace.selected_ids_snapshot() == [identities[0]]
        assert workspace._session_snapshot()["groups"][0]["tabs"][0]["kind"] == "playlist"
        workspace.customPlaylistOrder(tab_id)
        qtbot.waitUntil(lambda: model.count == 2)
        entries = model.track_ids_snapshot()
        list_view = _find(root, "trackRowsList")
        assert list_view is not None
        list_view.setProperty("contentY", 0)
        QTest.mouseMove(root, QPoint(700, 300))
        # PySide accepts str here; the generated stub declares bytes only.
        assert cast(Any, QMetaObject.invokeMethod)(list_view, "forceLayout")
        qtbot.waitUntil(lambda: _find(root, "trackRow_2") is not None)
        first_row = _find(root, "trackRow_1")
        second_row = _find(root, "trackRow_2")
        assert first_row is not None and second_row is not None
        start = second_row.mapToScene(second_row.boundingRect().center())
        end = first_row.mapToScene(first_row.boundingRect().center())
        QTest.mousePress(
            root, Qt.MouseButton.LeftButton, pos=QPoint(round(start.x()), round(start.y()))
        )
        for step in range(1, 11):
            point = start + (end - start) * (step / 10)
            QTest.mouseMove(root, QPoint(round(point.x()), round(point.y())), 15)
        QTest.mouseRelease(
            root, Qt.MouseButton.LeftButton, pos=QPoint(round(end.x()), round(end.y()))
        )
        qtbot.waitUntil(lambda: model.track_ids_snapshot() == entries[::-1])
        assert [r["id"] for r in runtime.player_service.queue_rows()] == [identities[0]]
        missing_path = audio / "1.wav"
        missing_path.rename(audio / "moved.wav")
        workspace.openPlaylist(identity)
        qtbot.waitUntil(lambda: not model.rows_snapshot()[0]["available"])
        assert model.rows_snapshot()[0]["id"] == entries[1]
        assert workspace.localTrackIds(["not-a-visible-entry"]) == []
        if capture:
            QTest.qWait(200)
            assert root.grabWindow().save(str(Path(capture) / "missing.png"))
            root.resize(1000, 760)
            QTest.qWait(250)
            assert root.grabWindow().save(str(Path(capture) / "narrow.png"))
        workspace.openPlaylist("liked")
        liked = cast(
            TrackListModel,
            workspace.trackModelForTab("playlist:liked", "playlist", "liked", "index", True),
        )
        qtbot.waitUntil(lambda: liked.count == 1, timeout=5000)
        playlists.export(
            identity, QUrl.fromLocalFile(str(tmp_path / "backup.mteeplaylist")).toString(), False
        )
        qtbot.waitUntil(lambda: (tmp_path / "backup.mteeplaylist").is_file(), timeout=5000)
        playlists.prepareImport(
            QUrl.fromLocalFile(str(tmp_path / "backup.mteeplaylist")).toString(), ""
        )
        qtbot.waitUntil(lambda: _visible(root, "playlistImportCreate"))
        playlists.chooseImportMatch(0, "")
        _click(root, "playlistImportCreate")
        qtbot.waitUntil(lambda: len(playlists._playlists) == 3)
        assert not warnings, warnings
    finally:
        _shutdown(runtime)
    restored = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert restored is not None
    try:
        restored_workspace = cast(WorkspaceModel, restored.workspace)
        restored_playlists = cast(PlaylistsModel, restored_workspace.playlistModel)
        qtbot.waitUntil(lambda: len(restored_playlists._playlists) == 3)
        assert restored_playlists._creator == "Local curator"
        assert restored_playlists._columns["widths"]["artist"] == 210
        assert restored_playlists.isLiked(identities[0])
        restored_workspace.openPlaylist(identity)
        restored_model = cast(
            TrackListModel,
            restored_workspace.trackModelForTab(tab_id, "playlist", identity, "index", True),
        )
        qtbot.waitUntil(lambda: restored_model.count == 2)
        assert restored_model.track_ids_snapshot() == entries[::-1]
        assert not restored_model.rows_snapshot()[0]["available"]
    finally:
        _shutdown(restored)
