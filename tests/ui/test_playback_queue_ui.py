"""Queue panel renders the service's occurrence order through the Qt model."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import cast

from PySide6.QtCore import QCoreApplication, QPoint, Qt
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_player_views import _find, _UiPlayerBackend

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.player_model import PlayerModel
from mtee.models.playlists_model import PlaylistsModel
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository


def test_queue_panel_shows_distinct_upcoming_occurrences(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    backend = _UiPlayerBackend()
    monkeypatch.setattr("mtee.app.MpvBackend", lambda: backend)
    data_dir = tmp_path / "data"
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    folder = tmp_path / "audio"
    folder.mkdir()
    root_record = library.add_root(folder)
    ids = []
    for index in range(2):
        source = folder / f"track-{index}.wav"
        with wave.open(str(source), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8_000)
            handle.writeframes(b"\x00\x00" * 24_000)
        ids.append(
            library.upsert_location(
                root_record["id"],
                source.name,
                source,
                SourceRevision.observe(source),
                MetadataSnapshot(
                    title=(f"Track {index}",), technical=TechnicalInfo(duration_us=3_000_000)
                ),
                0,
            )
        )
    database.close()

    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=data_dir))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = cast(WorkspaceModel, runtime.workspace)
    player = cast(PlayerModel, workspace.playerModel)
    service = runtime.player_service
    assert service is not None
    warnings: list[str] = []
    runtime.engine.warnings.connect(
        lambda values: warnings.extend(item.toString() for item in values)
    )
    try:
        workspace.openFolder(f"folder:{root_record['id']}/")
        workspace.showRightPanel("queue")
        workspace.playTrack(ids[0], f"folder:{root_record['id']}/")
        qtbot.waitUntil(lambda: service.state.current_id == ids[0])
        workspace.enqueueTracks([ids[1], ids[1]], f"folder:{root_record['id']}/", [])
        qtbot.waitUntil(lambda: len(service.queue_state.upcoming) >= 2)
        qtbot.waitUntil(lambda: _find(root, "playbackQueueView") is not None)
        QCoreApplication.processEvents()
        rows = player._upcoming_queue_model.rows_snapshot()
        manual = [row for row in rows if row["origin"] == "manual"]
        assert len(manual) == 2
        assert manual[0]["entryId"] != manual[1]["entryId"]
        assert manual[0]["id"] == manual[1]["id"] == ids[1]
        first_id, second_id = manual[0]["entryId"], manual[1]["entryId"]
        queue_row = _find(root, "queueEntry_" + second_id)
        assert queue_row is not None
        point = queue_row.mapToScene(queue_row.boundingRect().center())
        QTest.mouseClick(
            root,
            Qt.MouseButton.RightButton,
            pos=QPoint(round(point.x()), round(point.y())),
        )
        qtbot.waitUntil(lambda: _find(root, "removeQueueAction") is not None)
        remove = _find(root, "removeQueueAction")
        assert remove is not None
        action_point = remove.mapToScene(remove.boundingRect().center())
        QTest.mouseClick(
            root,
            Qt.MouseButton.LeftButton,
            pos=QPoint(round(action_point.x()), round(action_point.y())),
        )
        qtbot.waitUntil(
            lambda: (
                second_id
                not in [row["entryId"] for row in player._upcoming_queue_model.rows_snapshot()]
            )
        )
        assert first_id in [row["entryId"] for row in player._upcoming_queue_model.rows_snapshot()]
        track_row = _find(root, "trackRow_2")
        assert track_row is not None
        track_point = track_row.mapToScene(track_row.boundingRect().center())
        QTest.mouseClick(
            root,
            Qt.MouseButton.RightButton,
            pos=QPoint(round(track_point.x()), round(track_point.y())),
        )
        qtbot.waitUntil(lambda: _find(root, "addToQueueAction") is not None)
        add = _find(root, "addToQueueAction")
        assert add is not None
        add_point = add.mapToScene(add.boundingRect().center())
        QTest.mouseClick(
            root,
            Qt.MouseButton.LeftButton,
            pos=QPoint(round(add_point.x()), round(add_point.y())),
        )
        qtbot.waitUntil(
            lambda: (
                len(
                    [
                        row
                        for row in player._upcoming_queue_model.rows_snapshot()
                        if row["origin"] == "manual"
                    ]
                )
                == 2
            )
        )
        before = [row["entryId"] for row in player._upcoming_queue_model.rows_snapshot()]
        moved_id = before[0]
        assert len(before) >= 2
        moved = _find(root, "queueEntry_" + moved_id)
        target = _find(root, "queueEntry_" + before[-1])
        assert moved is not None and target is not None
        start = moved.mapToScene(moved.boundingRect().center())
        end = target.mapToScene(target.boundingRect().center())
        start_point = QPoint(round(start.x() - moved.width() / 2 + 14), round(start.y()))
        end_point = QPoint(start_point.x(), round(end.y() + target.height() / 3))
        QTest.mousePress(root, Qt.MouseButton.LeftButton, pos=start_point)
        QTest.mouseMove(root, QPoint(start_point.x(), start_point.y() + 12))
        QTest.mouseMove(root, end_point)
        queue_view = _find(root, "playbackQueueView")
        assert queue_view is not None
        assert queue_view.property("dragActive") is True
        assert queue_view.property("dragEntryId") == moved_id
        assert queue_view.property("dropBeforeId") == ""
        QTest.mouseRelease(root, Qt.MouseButton.LeftButton, pos=end_point)
        qtbot.waitUntil(
            lambda: (
                [row["entryId"] for row in player._upcoming_queue_model.rows_snapshot()] != before
            )
        )
        assert player._upcoming_queue_model.rows_snapshot()[-1]["entryId"] == moved_id
        after_move = [row["entryId"] for row in player._upcoming_queue_model.rows_snapshot()]
        moved = _find(root, "queueEntry_" + moved_id)
        assert moved is not None
        position = moved.mapToScene(moved.boundingRect().center())
        handle_point = QPoint(round(position.x() - moved.width() / 2 + 14), round(position.y()))
        QTest.mousePress(root, Qt.MouseButton.LeftButton, pos=handle_point)
        QTest.mouseMove(root, QPoint(handle_point.x(), handle_point.y() - 15))
        assert queue_view.property("dragActive") is True
        QTest.keyClick(root, Qt.Key.Key_Escape)
        QTest.mouseRelease(root, Qt.MouseButton.LeftButton, pos=handle_point)
        assert [
            row["entryId"] for row in player._upcoming_queue_model.rows_snapshot()
        ] == after_move
        playlists = cast(PlaylistsModel, workspace.playlistModel)
        playlist_id = playlists.service.repository.create(
            "Queue test",
            entries=[
                {"track_id": identity, "snapshot": {"title": f"Track {index}"}}
                for index, identity in enumerate(ids)
            ],
        )
        playlists.refresh()
        workspace.setActivity("playlists")
        qtbot.waitUntil(lambda: _find(root, "playlistNode_" + playlist_id) is not None)
        playlist_node = _find(root, "playlistNode_" + playlist_id)
        assert playlist_node is not None
        playlist_point = playlist_node.mapToScene(playlist_node.boundingRect().center())
        QTest.mouseClick(
            root,
            Qt.MouseButton.RightButton,
            pos=QPoint(round(playlist_point.x()), round(playlist_point.y())),
        )
        qtbot.waitUntil(lambda: _find(root, "enqueuePlaylistAction") is not None)
        playlist_action = _find(root, "enqueuePlaylistAction")
        assert playlist_action is not None
        action_point = playlist_action.mapToScene(playlist_action.boundingRect().center())
        QTest.mouseClick(
            root,
            Qt.MouseButton.LeftButton,
            pos=QPoint(round(action_point.x()), round(action_point.y())),
        )
        qtbot.waitUntil(lambda: len(service.queue_state.upcoming) == len(after_move) + 2)
        assert [entry.track_id for entry in service.queue_state.upcoming[-2:]] == ids
        workspace.setActivity("explorer")
        track_list = _find(root, "trackListView")
        assert track_list is not None
        visible_order = list(track_list.property("orderedIds"))
        assert set(visible_order) == set(ids)
        workspace.selectTrack(visible_order[-1], "single", [])
        workspace.selectTrack(visible_order[0], "toggle", [])
        assert workspace.selectedIds == list(reversed(visible_order))
        first_track_row = _find(root, "trackRow_1")
        assert first_track_row is not None
        first_point = first_track_row.mapToScene(first_track_row.boundingRect().center())
        QTest.mouseClick(
            root,
            Qt.MouseButton.RightButton,
            pos=QPoint(round(first_point.x()), round(first_point.y())),
        )
        add = _find(root, "addToQueueAction")
        assert add is not None
        add_point = add.mapToScene(add.boundingRect().center())
        QTest.mouseClick(
            root,
            Qt.MouseButton.LeftButton,
            pos=QPoint(round(add_point.x()), round(add_point.y())),
        )
        qtbot.waitUntil(lambda: len(service.queue_state.upcoming) == len(after_move) + 4)
        assert [entry.track_id for entry in service.queue_state.upcoming[-2:]] == visible_order
        assert not warnings
    finally:
        _shutdown(runtime)
        application.quit()
