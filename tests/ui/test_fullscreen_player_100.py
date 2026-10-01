"""The fullscreen player card, island and menus (plan 100, milestone 100.4)."""

from __future__ import annotations

import wave
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.app import _build_runtime, create_application
from mtee.assets import qml_dir
from mtee.cli import AppOptions
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.demo_workspace import DemoWorkspace
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.player_backend import BackendEvent, BackendEventHandler


def _find(root: QObject, name: str) -> QQuickItem | None:
    assert isinstance(root, QQuickWindow)
    pending = [root.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def _visible(root: QObject, name: str) -> bool:
    item = _find(root, name)
    return item is not None and item.isVisible()


def _click(root: QQuickWindow, name: str) -> None:
    item = _find(root, name)
    assert item is not None and item.isVisible(), name
    point = item.mapToScene(item.boundingRect().center())
    QTest.mouseClick(
        root, Qt.MouseButton.LeftButton, pos=QPoint(round(point.x()), round(point.y()))
    )
    QCoreApplication.processEvents()


def _settle(qtbot, seconds: float = 0.05) -> None:
    qtbot.wait(int(seconds * 1000))


def _close(application, runtime) -> None:
    runtime.jobs.shutdown()
    for root in runtime.engine.rootObjects():
        root.deleteLater()
    runtime.engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    runtime.database.close()
    application.quit()


@contextmanager
def _demo(qapp, tmp_path: Path, scenario: str = "explorer-info") -> Iterator[tuple]:
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application, AppOptions(data_dir=tmp_path / scenario, demo=True, scenario=scenario)
    )
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = cast(DemoWorkspace, runtime.workspace)
    workspace.loadScenario(scenario)
    workspace.togglePlay()  # freeze the prototype clock
    QCoreApplication.processEvents()
    try:
        yield root, workspace
    finally:
        _close(application, runtime)


def test_the_island_stays_with_an_exit_icon_and_there_is_no_tag_editor(qapp, tmp_path) -> None:
    with _demo(qapp, tmp_path) as (root, workspace):
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        assert _visible(root, "fullscreenPlayer")
        assert _visible(root, "playerIsland")
        button = _find(root, "islandFullscreenButton")
        assert button is not None and button.property("icon") == "exit-fullscreen"
        assert _find(root, "fullscreenMetadataEditor") is None
        assert not _visible(root, "rightPanel")
        _click(cast(QQuickWindow, root), "islandFullscreenButton")
        assert not workspace.fullscreen


def test_the_exit_icon_and_an_activity_leave_fullscreen(qapp, tmp_path) -> None:
    with _demo(qapp, tmp_path) as (root, workspace):
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        _click(cast(QQuickWindow, root), "exitFullscreen")
        assert not workspace.fullscreen
        workspace.setFullscreen(True)
        workspace.setActivity("explorer")
        assert not workspace.fullscreen


def test_the_card_shows_title_artist_genre_and_hides_an_empty_genre(qapp, tmp_path) -> None:
    with _demo(qapp, tmp_path) as (root, workspace):
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        title = _find(root, "fullscreenTitle")
        assert title is not None and title.property("text") == workspace.playingTrack["title"]
        assert _visible(root, "fullscreenGenre")
        workspace.playTrack("smp03", "folder:samples")  # no artist, no genre
        QCoreApplication.processEvents()
        assert workspace.playingId == "smp03"
        assert not _visible(root, "fullscreenGenre")
        artist = _find(root, "fullscreenArtist")
        assert artist is not None and artist.property("text") == "Unknown artist"


def test_the_cover_disappears_when_the_window_is_too_narrow(qapp, tmp_path) -> None:
    with _demo(qapp, tmp_path) as (root, workspace):
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        assert _visible(root, "fullscreenPlayerCover")
        cast(QQuickWindow, root).resize(880, 600)
        QCoreApplication.processEvents()
        assert not _visible(root, "fullscreenPlayerCover")
        assert _visible(root, "fullscreenCard")


def test_the_heart_toggles_the_like_of_the_playing_track(qapp, tmp_path) -> None:
    with _demo(qapp, tmp_path) as (root, workspace):
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        playing = workspace.playingId
        assert not workspace.isLiked(playing)
        like = _find(root, "fullscreenLike")
        assert like is not None and like.property("icon") == "heart"
        _click(cast(QQuickWindow, root), "fullscreenLike")
        assert workspace.isLiked(playing)
        assert like.property("icon") == "heart-filled"
        _click(cast(QQuickWindow, root), "fullscreenLike")
        assert not workspace.isLiked(playing)


def test_play_follows_the_player_state_not_the_hover(qapp, tmp_path) -> None:
    with _demo(qapp, tmp_path) as (root, workspace):
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        assert not workspace.isPlaying  # the prototype clock was frozen
        play = _find(root, "fullscreenPlay")
        assert play is not None
        icon = next(
            item for item in play.childItems() if item.property("name") in {"play", "pause"}
        )
        assert icon.property("name") == "play"
        _click(cast(QQuickWindow, root), "fullscreenPlay")
        assert workspace.isPlaying
        assert icon.property("name") == "pause"


def test_the_more_menu_has_six_entries_and_targets_the_playing_track(qapp, tmp_path) -> None:
    with _demo(qapp, tmp_path) as (root, workspace):
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        playing = workspace.playingId
        assert workspace.selectedIds == ["dnb03"] and playing != "dnb03"
        _click(cast(QQuickWindow, root), "fullscreenMore")
        labels = [
            str(_find(root, name).property("text"))  # type: ignore[union-attr]
            for name in (
                "playingEditInfo",
                "playingAddToPlaylist",
                "playingConvert",
                "playingAnalyze",
                "playingReanalyze",
                "playingShowInExplorer",
            )
        ]
        assert labels == [
            "Edit info",
            "Add to playlist…",
            "Convert…",
            "Analyze",
            "Re-analyze",
            "Show in Explorer",
        ]
        menu = cast(QObject, _find(root, "playingConvert")).parent()
        assert menu.property("trackId") == playing


def test_convert_adds_the_playing_track_not_the_selection(qapp, tmp_path) -> None:
    with _demo(qapp, tmp_path) as (root, workspace):
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        playing = workspace.playingId
        _click(cast(QQuickWindow, root), "fullscreenMore")
        item = _find(root, "playingConvert")
        assert item is not None
        item.metaObject().invokeMethod(item, "triggered")
        QCoreApplication.processEvents()
        assert not workspace.fullscreen
        inputs = [str(row.get("id", "")) for row in workspace.convertInputs]
        assert playing in inputs
        assert "dnb03" not in inputs


def test_edit_info_selects_the_playing_track_and_opens_info(qapp, tmp_path) -> None:
    with _demo(qapp, tmp_path) as (root, workspace):
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        playing = workspace.playingId
        playing_before = playing
        _click(cast(QQuickWindow, root), "fullscreenMore")
        item = _find(root, "playingEditInfo")
        assert item is not None
        item.metaObject().invokeMethod(item, "triggered")
        QCoreApplication.processEvents()
        assert not workspace.fullscreen
        assert workspace.selectedIds == [playing]
        assert workspace.rightPanelTab == "info" and workspace.rightPanelVisible
        assert workspace.playingId == playing_before  # nothing is played


def test_the_source_name_opens_the_source_without_playing(qapp, tmp_path) -> None:
    with _demo(qapp, tmp_path, "playlists") as (root, workspace):
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        assert workspace.playingSource == "playlist:peak"
        playing = workspace.playingId
        _click(cast(QQuickWindow, root), "fullscreenSource")
        assert not workspace.fullscreen
        assert workspace.playingId == playing


def _marquee(engine: QQmlEngine, width: int, text: str) -> QObject:
    components = (qml_dir() / "components").as_posix()
    component = QQmlComponent(engine)
    component.setData(
        f"""
        import QtQuick
        import "file:///{components}"
        MarqueeText {{ width: {width}; text: "{text}"; pixelSize: 34; bold: true }}
        """.encode(),
        QUrl("file:///marquee-probe.qml"),
    )
    item = component.create()
    assert item is not None, component.errors()
    item.component = component  # type: ignore[attr-defined]
    return cast(QObject, item)


def test_a_long_title_scrolls_and_a_short_one_stays_still(qapp, qtbot) -> None:
    engine = QQmlEngine()
    engine.addImportPath(str(qml_dir()))
    long_title = "A very long title that will never fit in two hundred pixels of width"
    scrolling = _marquee(engine, 200, long_title)
    still = _marquee(engine, 600, "Short")
    qtbot.waitUntil(lambda: bool(scrolling.property("scrolling")), timeout=2000)
    _settle(qtbot, 0.1)
    assert scrolling.property("overflow") > 0
    assert not still.property("scrolling")
    assert still.property("overflow") == 0


class _Backend:
    def __init__(self) -> None:
        self.handler: BackendEventHandler | None = None
        self.session_id = 0

    def set_event_handler(self, handler: BackendEventHandler | None) -> None:
        self.handler = handler

    def load(self, path: Path, session_id: int) -> None:
        self.session_id = session_id
        for name, value in (("duration", 3_000_000), ("seekable", True), ("loaded", None)):
            if self.handler is not None:
                self.handler(BackendEvent(name, session_id, value))

    def set_paused(self, paused: bool) -> None:
        if self.handler is not None:
            self.handler(BackendEvent("pause", self.session_id, paused))

    def seek(self, position_us: int) -> None:
        return

    def set_volume(self, _value: int) -> None:
        return

    def position_us(self) -> int:
        return 0

    def stop(self) -> None:
        if self.handler is not None:
            self.handler(BackendEvent("stopped", self.session_id, None))

    def close(self) -> None:
        return


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 24_000)


@contextmanager
def _real(qapp, tmp_path: Path, monkeypatch) -> Iterator[tuple]:
    music = tmp_path / "library"
    music.mkdir()
    data_dir = tmp_path / "data"
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(music)
    ids = []
    for name in ("first.wav", "second.wav"):
        path = music / name
        _write_wav(path)
        ids.append(
            library.upsert_location(
                root["id"],
                name,
                path,
                SourceRevision.observe(path),
                MetadataSnapshot(
                    title=(path.stem,), technical=TechnicalInfo(duration_us=3_000_000)
                ),
                0,
            )
        )
    database.close()
    backend = _Backend()
    monkeypatch.setattr("mtee.app.MpvBackend", lambda: backend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=data_dir))
    assert runtime is not None
    window = runtime.engine.rootObjects()[0]
    assert isinstance(window, QQuickWindow)
    window.resize(1440, 900)
    workspace = cast(WorkspaceModel, runtime.workspace)
    try:
        # Let the startup scan and its queued follow-ups finish before the test starts,
        # so nothing is submitted to the job service once it shuts down.
        for _ in range(6):
            assert runtime.jobs.wait_for_done(10_000)
            QCoreApplication.processEvents()
        yield window, workspace, str(root["id"]), ids
    finally:
        runtime.jobs.wait_for_done(10_000)
        QCoreApplication.processEvents()
        _close(application, runtime)


def test_without_a_track_fullscreen_only_says_to_play_one(
    qapp, qtbot, tmp_path, monkeypatch
) -> None:
    with _real(qapp, tmp_path, monkeypatch) as (window, workspace, _root, _ids):
        workspace.setFullscreen(True)
        qtbot.waitUntil(lambda: _visible(window, "fullscreenPlayer"))
        empty = _find(window, "fullscreenEmpty")
        assert empty is not None and empty.isVisible()
        assert empty.property("text") == "Play a track"
        assert not _visible(window, "fullscreenCard")
        assert _visible(window, "exitFullscreen")
        assert not _visible(window, "playerIsland")


def test_edit_info_in_the_real_workspace_replaces_the_selection_in_the_source(
    qapp, qtbot, tmp_path, monkeypatch
) -> None:
    with _real(qapp, tmp_path, monkeypatch) as (window, workspace, root_id, ids):
        source = f"folder:{root_id}/"
        workspace.openFolder(source)
        workspace.playTrack(ids[0], source)
        qtbot.waitUntil(lambda: workspace.playingId == ids[0])
        workspace.setFullscreen(True)
        qtbot.waitUntil(lambda: _visible(window, "fullscreenCard"))
        workspace.selectTrack(ids[1], "single", [])
        assert workspace.selectedIds == [ids[1]]

        workspace.revealTrackForEdit(ids[0], workspace.playingSource)

        assert not workspace.fullscreen
        qtbot.waitUntil(lambda: workspace.selectedIds == [ids[0]], timeout=5000)
        assert workspace.rightPanelTab == "info" and workspace.rightPanelVisible
        assert workspace.playingId == ids[0]


def test_a_missing_source_falls_back_to_the_folder_of_the_file(
    qapp, qtbot, tmp_path, monkeypatch
) -> None:
    with _real(qapp, tmp_path, monkeypatch) as (_window, workspace, root_id, ids):
        source = f"folder:{root_id}/"
        workspace.playTrack(ids[0], source)
        qtbot.waitUntil(lambda: workspace.playingId == ids[0])
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        workspace.revealTrack(ids[0], "playlist:does-not-exist")
        assert not workspace.fullscreen
        qtbot.waitUntil(lambda: workspace.selectedIds == [ids[0]], timeout=5000)


def test_convert_in_the_real_workspace_takes_the_playing_track(
    qapp, qtbot, tmp_path, monkeypatch
) -> None:
    with _real(qapp, tmp_path, monkeypatch) as (_window, workspace, root_id, ids):
        source = f"folder:{root_id}/"
        workspace.openFolder(source)
        workspace.playTrack(ids[0], source)
        qtbot.waitUntil(lambda: workspace.playingId == ids[0])
        workspace.setFullscreen(True)
        workspace.selectTrack(ids[1], "single", [])
        workspace.addTracksToConvert([ids[0]])
        assert not workspace.fullscreen
        inputs = [str(row.get("trackId", "")) for row in workspace.convertInputs]
        assert inputs == [ids[0]]


def test_the_source_name_opens_the_playing_folder(qapp, qtbot, tmp_path, monkeypatch) -> None:
    with _real(qapp, tmp_path, monkeypatch) as (_window, workspace, root_id, ids):
        source = f"folder:{root_id}/"
        workspace.playTrack(ids[0], source)
        qtbot.waitUntil(lambda: workspace.playingId == ids[0])
        workspace.setFullscreen(True)
        QCoreApplication.processEvents()
        assert workspace.playingSource == source
        workspace.openPlayingSource()
        assert not workspace.fullscreen
        assert workspace.activeFolder == source
        assert workspace.playingId == ids[0]
