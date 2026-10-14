"""Exercise real List and Artwork pointer gestures for playlist batches."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import cast

from PySide6.QtCore import QPoint, QPointF, Qt
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


def _center(item) -> QPoint:
    point = item.mapToScene(item.boundingRect().center())
    return QPoint(round(point.x()), round(point.y()))


def _drag(root: QQuickWindow, start: QPoint, end: QPoint, *, release: bool = True) -> None:
    QTest.mousePress(root, Qt.MouseButton.LeftButton, pos=start)
    for step in range(1, 16):
        position = QPoint(
            round(start.x() + (end.x() - start.x()) * step / 15),
            round(start.y() + (end.y() - start.y()) * step / 15),
        )
        QTest.mouseMove(root, position, 10)
    if release:
        QTest.mouseRelease(root, Qt.MouseButton.LeftButton, pos=end)


def test_list_batch_artwork_batch_and_escape(qapp, qtbot, tmp_path: Path, monkeypatch) -> None:
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
        library = LibraryRepository(runtime.database)
        audio = tmp_path / "audio"
        audio.mkdir()
        root_record = library.add_root(audio)
        track_ids = []
        for index, title in enumerate(("Alpha", "Bravo", "Charlie")):
            path = audio / f"{index}.wav"
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(8000)
                handle.writeframes(b"\x00\x00" * 24000)
            track_ids.append(
                library.upsert_location(
                    root_record["id"],
                    path.name,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(
                        title=(title,),
                        artist=("Example",),
                        technical=TechnicalInfo(duration_us=3_000_000),
                    ),
                    0,
                )
            )
        playlists.create("Drag test", "", track_ids)
        qtbot.waitUntil(lambda: len(playlists._playlists) == 1, timeout=5000)
        identity = playlists._playlists[0]["id"]
        workspace.setActivity("playlists")
        source = "playlist:" + identity
        model = workspace.trackModelForTab(source, "playlist", identity, "index", True)
        qtbot.waitUntil(lambda: model.count == 3, timeout=5000)
        original = model.track_ids_snapshot()
        workspace.selectTrack(original[2], "single", [])
        workspace.selectTrack(original[0], "toggle", original)
        qtbot.waitUntil(lambda: _find(root, "trackRow_3") is not None)
        third = _find(root, "trackRow_3")
        second = _find(root, "trackRow_2")
        assert third is not None and second is not None
        end_point = second.mapToScene(QPointF(second.width() / 2, second.height() / 4))
        _drag(
            root, _center(third), QPoint(round(end_point.x()), round(end_point.y())), release=False
        )
        preview = _find(root, "trackDragPreview")
        assert preview is not None and preview.isVisible()
        assert preview.property("count") == 2
        assert preview.property("trackTitle") == "Alpha"
        QTest.mouseRelease(
            root, Qt.MouseButton.LeftButton, pos=QPoint(round(end_point.x()), round(end_point.y()))
        )
        qtbot.waitUntil(
            lambda: model.track_ids_snapshot() == [original[0], original[2], original[1]],
            timeout=5000,
        )
        assert set(cast(list[str], workspace.selectedIds)) == {original[0], original[2]}

        persisted = [entry["entry_id"] for entry in playlists.repository.entries(identity)]
        workspace.setSort(source, "title")
        qtbot.waitUntil(lambda: _find(root, "trackRow_3") is not None)
        first_sorted = _find(root, "trackRow_1")
        last_sorted = _find(root, "trackRow_3")
        assert first_sorted is not None and last_sorted is not None
        sorted_target = first_sorted.mapToScene(
            QPointF(first_sorted.width() / 2, first_sorted.height() / 4)
        )
        _drag(
            root,
            _center(last_sorted),
            QPoint(round(sorted_target.x()), round(sorted_target.y())),
            release=False,
        )
        view = _find(root, "trackListView")
        assert view is not None and view.property("dropIndex") == -1
        QTest.mouseRelease(
            root,
            Qt.MouseButton.LeftButton,
            pos=QPoint(round(sorted_target.x()), round(sorted_target.y())),
        )
        assert [entry["entry_id"] for entry in playlists.repository.entries(identity)] == persisted
        workspace.customPlaylistOrder(source)
        qtbot.waitUntil(lambda: model.track_ids_snapshot() == persisted, timeout=5000)

        workspace.setTabView(source, "artwork")
        qtbot.waitUntil(lambda: _find(root, "trackTile_3") is not None)
        current = model.track_ids_snapshot()
        workspace.selectTrack(current[1], "single", [])
        workspace.selectTrack(current[0], "toggle", current)
        first = _find(root, "trackTile_1")
        last = _find(root, "trackTile_3")
        assert first is not None and last is not None
        target = last.mapToScene(QPointF(last.width() * 3 / 4, last.height() / 2))
        _drag(root, _center(first), QPoint(round(target.x()), round(target.y())))
        qtbot.waitUntil(
            lambda: model.track_ids_snapshot() == [current[2], current[0], current[1]], timeout=5000
        )

        after = model.track_ids_snapshot()
        first = _find(root, "trackTile_1")
        last = _find(root, "trackTile_3")
        assert first is not None and last is not None
        _drag(root, _center(first), _center(last), release=False)
        QTest.keyClick(root, Qt.Key.Key_Escape)
        QTest.mouseRelease(root, Qt.MouseButton.LeftButton, pos=_center(last))
        QTest.qWait(200)
        assert model.track_ids_snapshot() == after
        assert not preview.isVisible()
    finally:
        _shutdown(runtime)
        application.quit()
