"""System media controls: commands, flyout content and fallback, with a fake transport.

The player is the real ``PlayerService`` over a fake native backend; the transport is a
recording fake, so no Windows runtime is needed. Commands cross a queued signal, so each
press is followed by a wait for the interface thread to process it.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QColor, QImage

from mtee.domain.playback import PlaybackStatus
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.platform import media_transport
from mtee.platform.media_transport import (
    MediaMetadata,
    NullMediaTransport,
    TransportCommand,
    TransportState,
    command_for_button,
    create_media_transport,
)
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.media_controls import COVER_SIZE, MediaControls
from mtee.services.player_backend import BackendEvent, BackendEventHandler
from mtee.services.player_service import PlayerService

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class FakeBackend:
    def __init__(self) -> None:
        self.handler: BackendEventHandler | None = None
        self.paused = False
        self.pause_calls = 0
        self.position = 0
        self.seeks: list[int] = []
        self.active_session_id = 0

    def set_event_handler(self, handler: BackendEventHandler | None) -> None:
        self.handler = handler

    def load(self, path: Path, session_id: int) -> None:
        self.active_session_id = session_id
        self.position = 0
        self.emit("duration", session_id, 4_000_000)
        self.emit("seekable", session_id, True)
        self.emit("loaded", session_id)

    def set_paused(self, paused: bool) -> None:
        self.pause_calls += 1
        self.paused = paused
        if self.active_session_id:
            self.emit("pause", self.active_session_id, paused)

    def seek(self, position_us: int) -> None:
        self.seeks.append(position_us)
        self.position = position_us

    def set_volume(self, value: int) -> None:
        return

    def set_gain_db(self, value: float) -> None:
        return

    def position_us(self) -> int:
        return self.position

    def stop(self) -> None:
        self.emit("stopped", self.active_session_id)

    def close(self) -> None:
        return

    def emit(self, name: str, session_id: int, value: object = None) -> None:
        if self.handler is not None:
            self.handler(BackendEvent(name, session_id, value))


class FakeTransport:
    def __init__(self) -> None:
        self.handler = None
        self.metadata: list[MediaMetadata | None] = []
        self.states: list[TransportState] = []
        self.closed = False

    def set_command_handler(self, handler) -> None:
        self.handler = handler

    def set_metadata(self, metadata: MediaMetadata | None) -> None:
        self.metadata.append(metadata)

    def set_state(self, state: TransportState) -> None:
        self.states.append(state)

    def close(self) -> None:
        self.closed = True

    def press(self, command: TransportCommand) -> None:
        assert self.handler is not None
        self.handler(command)


class FakeLibrary:
    def __init__(self) -> None:
        self.paths: dict[str, Path] = {}

    def artwork_source(self, track_id: str):
        path = self.paths.get(track_id)
        if path is None:
            return None
        return path, SourceRevision(size_bytes=1, mtime_ns=1, file_id=None, generation=3)


class FakeArtwork:
    """Tracks whose file stem is in ``covered`` have embedded artwork; the others have none."""

    def __init__(self, covered: set[str]) -> None:
        self.covered = covered
        self.thumbnail_reads: list[str] = []

    def image_bytes(self, path: Path | str) -> bytes | None:
        return b"image" if Path(path).stem in self.covered else None

    def thumbnail(self, path: Path | str, size: int) -> QImage:
        self.thumbnail_reads.append(Path(path).stem)
        image = QImage(size, size, QImage.Format.Format_RGB32)
        image.fill(QColor("#E0245E"))
        return image


def _make(qapp, tmp_path: Path, *, covered: frozenset[str] = frozenset(), count: int = 3):
    tracks: dict[str, dict[str, object]] = {}
    library = FakeLibrary()
    ids: list[str] = []
    for index in range(count):
        track_id = str(TrackId.new())
        path = tmp_path / f"track-{index}.wav"
        path.write_bytes(b"synthetic audio fixture")
        tracks[track_id] = {
            "id": track_id,
            "title": f"Title {index}",
            "artist": "Artist A",
            "album": "Album B",
            "path": str(path),
            "seconds": 4,
            "durationUs": 4_000_000,
            "status": "readable",
        }
        library.paths[track_id] = path
        ids.append(track_id)
    backend = FakeBackend()
    service = PlayerService(
        lambda track_id: dict(tracks.get(track_id, {})),
        FileAccessCoordinator(),
        backend,
        parent=qapp,
    )
    transport = FakeTransport()
    artwork = FakeArtwork(set(covered))
    controls = MediaControls(
        service,
        library,  # type: ignore[arg-type]
        transport,
        qapp,
        artwork=artwork,  # type: ignore[arg-type]
    )
    return service, backend, transport, controls, ids, artwork


def _start(qapp, qtbot, tmp_path: Path, **options):
    service, backend, transport, controls, ids, artwork = _make(qapp, tmp_path, **options)
    service.play_queue(ids, 0, source="folder:root/album", source_title="album")
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING)
    return service, backend, transport, controls, ids, artwork


def test_media_keys_drive_the_existing_player_actions(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, transport, _controls, _ids, _ = _start(qapp, qtbot, tmp_path)

    transport.press(TransportCommand.PAUSE)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PAUSED)
    assert backend.paused is True

    transport.press(TransportCommand.PLAY)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING)
    assert backend.paused is False

    # Play on a track that already plays must leave the native pause property alone.
    calls = backend.pause_calls
    transport.press(TransportCommand.PLAY)
    qapp.processEvents()
    assert backend.pause_calls == calls
    assert service.state.status is PlaybackStatus.PLAYING

    transport.press(TransportCommand.STOP)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PAUSED)
    transport.press(TransportCommand.PLAY)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING)


def test_next_and_previous_keep_the_restart_rule(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, transport, _controls, ids, _ = _start(qapp, qtbot, tmp_path)

    transport.press(TransportCommand.NEXT)
    qtbot.waitUntil(lambda: service.state.current_id == ids[1])
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING)

    # Under three seconds played: Previous goes to the earlier track.
    backend.position = 1_000_000
    transport.press(TransportCommand.PREVIOUS)
    qtbot.waitUntil(lambda: service.state.current_id == ids[0])
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING)

    # Three seconds or more: Previous restarts the current track instead.
    backend.position = 3_500_000
    seeks = len(backend.seeks)
    transport.press(TransportCommand.PREVIOUS)
    qtbot.waitUntil(lambda: len(backend.seeks) > seeks)
    assert backend.seeks[-1] == 0
    assert service.state.current_id == ids[0]


def test_flyout_shows_the_loaded_track_and_its_playback_state(qapp, qtbot, tmp_path: Path) -> None:
    service, _backend, transport, _controls, _ids, _ = _start(qapp, qtbot, tmp_path)

    shown = transport.metadata[-1]
    assert shown is not None
    assert (shown.title, shown.artist, shown.album) == ("Title 0", "Artist A", "Album B")
    assert transport.states[-1] is TransportState.PLAYING

    service.pause()
    assert transport.states[-1] is TransportState.PAUSED

    service.stop_and_release()
    assert transport.metadata[-1] is None
    assert transport.states[-1] is TransportState.STOPPED


def test_cover_is_encoded_once_then_served_from_the_cache(qapp, qtbot, tmp_path: Path) -> None:
    service, _backend, transport, _controls, ids, artwork = _start(
        qapp, qtbot, tmp_path, covered=frozenset({"track-0"})
    )

    # The text comes first, without a cover; the cover follows when it is decoded.
    # pytest-qt reads a None result as "assert form": the predicate must be a real bool.
    qtbot.waitUntil(lambda: bool(transport.metadata[-1] and transport.metadata[-1].cover_png))
    pushed = transport.metadata[-1]
    assert pushed is not None
    cover = pushed.cover_png
    assert cover is not None
    assert cover.startswith(PNG_MAGIC)
    image = QImage()
    assert image.loadFromData(QByteArray(cover))
    assert image.width() == COVER_SIZE

    # Leaving for a track without artwork, then coming back: the cached cover is pushed
    # at once and the cover is not decoded a second time.
    service.play_index(1)
    qtbot.waitUntil(lambda: service.state.current_id == ids[1])
    qtbot.waitUntil(
        lambda: transport.metadata[-1] is not None and transport.metadata[-1].title == "Title 1"
    )
    service.play_index(0)
    qtbot.waitUntil(lambda: service.state.current_id == ids[0])
    qtbot.waitUntil(
        lambda: transport.metadata[-1] is not None and transport.metadata[-1].title == "Title 0"
    )
    cached = transport.metadata[-1]
    assert cached is not None
    assert cached.cover_png == cover
    assert artwork.thumbnail_reads == ["track-0"]


def test_track_without_embedded_artwork_has_no_cover(qapp, qtbot, tmp_path: Path) -> None:
    _service, _backend, transport, controls, _ids, artwork = _start(qapp, qtbot, tmp_path)
    # The cover cache records the finished decode, even when it found no artwork.
    qtbot.waitUntil(lambda: len(controls._covers) == 1)
    assert transport.metadata[-1] is not None
    assert transport.metadata[-1].cover_png is None
    assert artwork.thumbnail_reads == []


def test_button_presses_from_another_thread_reach_the_player_on_the_interface_thread(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, _backend, transport, _controls, _ids, _ = _start(qapp, qtbot, tmp_path)

    threads: list[int] = []
    original_pause = service.pause

    def recording_pause() -> None:
        threads.append(threading.get_ident())
        original_pause()

    service.pause = recording_pause  # type: ignore[method-assign]
    worker = threading.Thread(target=transport.press, args=(TransportCommand.PAUSE,))
    worker.start()
    worker.join()
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PAUSED)
    assert threads == [threading.get_ident()]


def test_close_detaches_the_system_and_ignores_later_commands(qapp, qtbot, tmp_path: Path) -> None:
    service, _backend, transport, controls, _ids, _ = _start(qapp, qtbot, tmp_path)

    controls.close()
    assert transport.closed is True
    assert transport.handler is None
    controls.close()  # idempotent
    states = list(transport.states)
    service.pause()
    service.resume()
    assert transport.states == states


def test_nothing_loaded_at_start_reports_a_stopped_session(qapp, tmp_path: Path) -> None:
    _service, _backend, transport, _controls, _ids, _ = _make(qapp, tmp_path)
    assert transport.states == [TransportState.STOPPED]
    assert transport.metadata == []


def test_button_codes_map_to_commands_and_others_are_ignored() -> None:
    assert command_for_button(0) is TransportCommand.PLAY
    assert command_for_button(1) is TransportCommand.PAUSE
    assert command_for_button(2) is TransportCommand.STOP
    assert command_for_button(6) is TransportCommand.NEXT
    assert command_for_button(7) is TransportCommand.PREVIOUS
    for ignored in (3, 4, 5, 8, 9):
        assert command_for_button(ignored) is None


def test_unavailable_system_controls_fall_back_to_a_silent_transport(monkeypatch) -> None:
    monkeypatch.setattr(media_transport.sys, "platform", "linux")
    assert isinstance(create_media_transport(), NullMediaTransport)

    monkeypatch.setattr(media_transport.sys, "platform", "win32")

    def unavailable(self) -> None:
        raise OSError("the Windows runtime is missing")

    monkeypatch.setattr(media_transport.WindowsMediaTransport, "__init__", unavailable)
    transport = create_media_transport()
    assert isinstance(transport, NullMediaTransport)
    transport.set_metadata(MediaMetadata(title="t"))
    transport.set_state(TransportState.PLAYING)
    transport.set_command_handler(None)
    transport.close()
