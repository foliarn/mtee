"""Both player presentations follow the same playing track across view changes."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import cast

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.demo_workspace import DemoWorkspace
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.player_backend import BackendEvent, BackendEventHandler


def _find(root: QQuickWindow, name: str) -> QQuickItem | None:
    pending = [root.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def _visible(root: QQuickWindow, name: str) -> bool:
    item = _find(root, name)
    return item is not None and item.isVisible()


class _UiPlayerBackend:
    def __init__(self) -> None:
        self.handler: BackendEventHandler | None = None
        self.session_id = 0
        self.paused = False
        self.seeks: list[int] = []

    def set_event_handler(self, handler: BackendEventHandler | None) -> None:
        self.handler = handler

    def load(self, path: Path, session_id: int) -> None:
        assert path.is_file()
        self.session_id = session_id
        self._emit("duration", 3_000_000)
        self._emit("seekable", True)
        self._emit("loaded")

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self._emit("pause", paused)

    def seek(self, position_us: int) -> None:
        self.seeks.append(position_us)

    def set_volume(self, _value: int) -> None:
        return

    def set_gain_db(self, _value: float) -> None:
        return

    def position_us(self) -> int:
        return 0

    def stop(self) -> None:
        self._emit("stopped")

    def close(self) -> None:
        return

    def _emit(self, name: str, value: object = None) -> None:
        if self.handler is not None:
            self.handler(BackendEvent(name, self.session_id, value))


def test_fullscreen_and_island_keep_one_shared_playback_state(qapp, tmp_path: Path) -> None:
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application,
        AppOptions(data_dir=tmp_path / "views", demo=True, scenario="explorer-info"),
    )
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = cast(DemoWorkspace, runtime.workspace)
    workspace.togglePlay()  # Freeze the prototype clock so view changes are observable.
    QCoreApplication.processEvents()
    playing_id = workspace.playingId
    position = workspace.position

    try:
        assert _visible(root, "playerIsland")
        for _ in range(10):
            workspace.setFullscreen(True)
            QCoreApplication.processEvents()
            assert _visible(root, "fullscreenPlayer")
            assert _find(root, "waveformView") is not None
            assert _visible(root, "playerIsland")
            workspace.selectTrack("dnb04", "single", [])
            assert workspace.selectedIds == ["dnb04"]
            assert workspace.playingId == playing_id
            workspace.setFullscreen(False)
            QCoreApplication.processEvents()
            assert _visible(root, "playerIsland")
            assert workspace.position == position
    finally:
        runtime.jobs.shutdown()
        for item in runtime.engine.rootObjects():
            item.deleteLater()
        runtime.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        runtime.database.close()
        application.quit()


def test_space_goes_to_search_while_a_track_is_playing(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    audio_path = tmp_path / "library" / "track.wav"
    audio_path.parent.mkdir(parents=True)
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 24_000)

    data_dir = tmp_path / "space-test"
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root_record = library.add_root(audio_path.parent)
    track_id = library.upsert_location(
        root_record["id"],
        audio_path.name,
        audio_path,
        SourceRevision.observe(audio_path),
        MetadataSnapshot(title=("Track",), technical=TechnicalInfo(duration_us=3_000_000)),
        0,
    )
    database.close()

    backend = _UiPlayerBackend()
    monkeypatch.setattr("mtee.app.MpvBackend", lambda: backend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=data_dir))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    workspace = cast(WorkspaceModel, runtime.workspace)
    root_id = str(root_record["id"])

    try:
        assert runtime.jobs.wait_for_done(10_000)
        workspace.openFolder(f"folder:{root_id}/")
        workspace.playTrack(track_id, f"folder:{root_id}/")
        QCoreApplication.processEvents()
        assert workspace.playingId == track_id

        previous = _find(root, "previousButton")
        assert previous is not None and previous.isVisible()
        point = previous.mapToScene(previous.boundingRect().center())
        QTest.mouseClick(
            root, Qt.MouseButton.LeftButton, pos=QPoint(round(point.x()), round(point.y()))
        )
        assert backend.seeks == [0]
        workspace.setFullscreen(True)
        qtbot.waitUntil(lambda: _visible(root, "fullscreenPlayer"))
        # The island stays above the fullscreen player, with the same transport.
        assert _visible(root, "playerIsland")
        fullscreen_previous = _find(root, "previousButton")
        assert fullscreen_previous is not None and fullscreen_previous.isVisible()
        point = fullscreen_previous.mapToScene(fullscreen_previous.boundingRect().center())
        QTest.mouseClick(
            root, Qt.MouseButton.LeftButton, pos=QPoint(round(point.x()), round(point.y()))
        )
        assert backend.seeks == [0, 0]
        workspace.setFullscreen(False)
        QCoreApplication.processEvents()
        QTest.keyClick(root, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
        assert backend.seeks == [0, 0, 0]

        QTest.keyClick(root, Qt.Key.Key_Space)
        assert backend.paused
        previous.forceActiveFocus()
        QCoreApplication.processEvents()
        QTest.keyClick(root, Qt.Key.Key_Space)
        assert not backend.paused
        assert backend.seeks == [0, 0, 0]
        workspace.showRightPanel("queue")
        qtbot.waitUntil(lambda: _visible(root, "queuePanel"))
        QTest.keyClick(root, Qt.Key.Key_Space)
        assert backend.paused
        workspace.openSettings()
        QTest.keyClick(root, Qt.Key.Key_Space)
        assert not backend.paused
        workspace.openConvert()
        QTest.keyClick(root, Qt.Key.Key_Space)
        assert backend.paused
        QTest.keyClick(root, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        assert backend.paused
        workspace.setActivity("explorer")
        QTest.keyClick(root, Qt.Key.Key_Space)
        assert not backend.paused
        workspace.openFolder(f"folder:{root_id}/")
        QCoreApplication.processEvents()

        search = _find(root, "folderSearchField")
        assert search is not None and search.isVisible()
        search.forceActiveFocus()
        QCoreApplication.processEvents()
        assert search.hasActiveFocus()
        QTest.keyClick(root, Qt.Key.Key_Space)
        QCoreApplication.processEvents()

        assert " " in str(search.property("text"))
        assert not backend.paused
        assert workspace.playingId == track_id
    finally:
        _shutdown(runtime)
        application.quit()
