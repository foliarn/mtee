"""Deterministic playback transitions with an event-driven fake backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtee.domain.playback import PlaybackStatus
from mtee.domain.tracks import TrackId
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError
from mtee.services.player_backend import BackendEvent, BackendEventHandler
from mtee.services.player_service import PlayerService


class FakeBackend:
    def __init__(self) -> None:
        self.handler: BackendEventHandler | None = None
        self.loads: list[tuple[Path, int]] = []
        self.volume = 72
        self.paused = False
        self.position = 0
        self.seeks: list[int] = []
        self.ab_loops: list[tuple[int | None, int | None]] = []
        self.stops = 0
        self.active_session_id = 0
        self.emit_stopped_events = True
        self.emit_loaded_events = True
        self.closed = False
        self.fail_load = False

    def set_event_handler(self, handler: BackendEventHandler | None) -> None:
        self.handler = handler

    def load(self, path: Path, session_id: int) -> None:
        if self.fail_load:
            raise OSError("fake decoder error")
        self.active_session_id = session_id
        self.loads.append((path, session_id))
        self.emit("duration", session_id, 4_000_000)
        self.emit("seekable", session_id, True)
        self.emit("codec", session_id, "pcm_s16le")
        if self.emit_loaded_events:
            self.emit("loaded", session_id)

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self.emit("pause", self.loads[-1][1], paused)

    def seek(self, position_us: int) -> None:
        self.seeks.append(position_us)
        self.position = position_us

    def set_ab_loop(self, start_us: int | None, end_us: int | None) -> None:
        self.ab_loops.append((start_us, end_us))

    def set_volume(self, value: int) -> None:
        self.volume = value

    def position_us(self) -> int:
        return self.position

    def stop(self) -> None:
        self.stops += 1
        if self.emit_stopped_events:
            self.emit("stopped", self.active_session_id)

    def close(self) -> None:
        self.closed = True

    def emit(self, name: str, session_id: int, value: object = None) -> None:
        if self.handler is not None:
            self.handler(BackendEvent(name, session_id, value))


def _track(track_id: str, path: Path) -> dict[str, object]:
    return {
        "id": track_id,
        "title": path.stem,
        "artist": "Test artist",
        "path": str(path),
        "seconds": 4,
        "durationUs": 4_000_000,
        "duration": "0:04",
        "status": "ok",
        "revision": 1,
    }


def _make_service(qapp, tmp_path: Path, *, count: int = 3):
    tracks: dict[str, dict[str, object]] = {}
    ids = []
    for index in range(count):
        track_id = str(TrackId.new())
        path = tmp_path / f"track-{index}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic audio fixture")
        tracks[track_id] = _track(track_id, path)
        ids.append(track_id)
    backend = FakeBackend()
    access = FileAccessCoordinator()
    service = PlayerService(
        lambda track_id: dict(tracks.get(track_id, {})), access, backend, parent=qapp
    )
    return service, backend, access, ids, tracks


def _wait_playing(qtbot, service: PlayerService) -> None:
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING)
    qtbot.waitUntil(lambda: service.state.seekable)


def test_queue_is_a_copy_and_transport_transitions_follow_its_order(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, _backend, access, ids, _ = _make_service(qapp, tmp_path)
    visible_order = list(ids)
    service.play_queue(visible_order, 1, source="folder:root/album", source_title="album")
    visible_order.reverse()
    _wait_playing(qtbot, service)

    assert service.state.track_ids == tuple(ids)
    assert service.state.current_id == ids[1]
    assert service.state.source_title == "album"
    assert service.current_track["title"] == "track-1"
    assert service.state.codec == "pcm_s16le"
    assert access.is_busy(TrackId.parse(ids[1]))

    service.next()
    _wait_playing(qtbot, service)
    assert service.state.current_id == ids[2]
    service.previous()
    _wait_playing(qtbot, service)
    assert service.state.current_id == ids[1]

    service.stop_and_release()
    qtbot.waitUntil(lambda: not access.is_busy(TrackId.parse(ids[1])))
    service.close()


def test_previous_at_first_seeks_to_start_and_last_next_ends(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, access, ids, _ = _make_service(qapp, tmp_path, count=1)
    service.play_queue(ids)
    _wait_playing(qtbot, service)

    backend.position = 1_500_000
    service.previous()
    assert backend.seeks == [0]

    service.next()
    assert service.state.status is PlaybackStatus.ENDED
    assert service.state.current_id == ids[0]
    qtbot.waitUntil(lambda: not access.is_busy(TrackId.parse(ids[0])))
    service.close()


def test_ab_loop_bounds_are_validated_and_cleared_on_track_change(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, _access, ids, _ = _make_service(qapp, tmp_path, count=2)
    service.play_queue(ids)
    _wait_playing(qtbot, service)
    service.set_ab_loop(500_000, 1_500_000)
    assert backend.ab_loops[-1] == (500_000, 1_500_000)
    with pytest.raises(ValueError):
        service.set_ab_loop(2_000_000, 1_000_000)
    service.next()
    _wait_playing(qtbot, service)
    assert backend.ab_loops[-1] == (None, None)
    service.close()


def test_stale_backend_errors_do_not_replace_a_new_session(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _access, ids, _ = _make_service(qapp, tmp_path, count=2)
    service.play_queue(ids)
    _wait_playing(qtbot, service)
    stale_session = service.state.session_id

    service.next()
    _wait_playing(qtbot, service)
    current_session = service.state.session_id
    backend.emit("error", stale_session, "old track failed")
    qtbot.wait(20)

    assert current_session != stale_session
    assert service.state.status is PlaybackStatus.PLAYING
    assert service.state.error_message == ""
    service.close()


def test_previous_file_stays_read_locked_until_backend_confirms_it_closed(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, access, ids, _ = _make_service(qapp, tmp_path, count=2)
    service.play_queue(ids)
    _wait_playing(qtbot, service)
    old_session = service.state.session_id
    old_track = TrackId.parse(ids[0])
    backend.emit_stopped_events = False
    backend.emit_loaded_events = False

    service.next()
    qtbot.waitUntil(lambda: len(backend.loads) == 2)

    assert access.is_busy(old_track)
    with (
        pytest.raises(FileAccessTimeoutError),
        access.acquire(old_track, "write tags", timeout_seconds=0),
    ):
        pytest.fail("exclusive access must wait for libmpv to close the old file")

    backend.emit("stopped", old_session)
    qtbot.waitUntil(lambda: not access.is_busy(old_track))
    backend.emit("loaded", service.state.session_id)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING)
    assert access.is_busy(TrackId.parse(ids[1]))
    service.close()


def test_retry_resolves_the_current_path_again(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _access, ids, tracks = _make_service(qapp, tmp_path, count=1)
    service.play_queue(ids)
    _wait_playing(qtbot, service)
    replacement = tmp_path / "moved-track.wav"
    replacement.write_bytes(b"replacement audio")
    tracks[ids[0]] = _track(ids[0], replacement)

    service.retry()
    _wait_playing(qtbot, service)

    assert backend.loads[-1][0] == replacement
    assert service.current_track["path"] == str(replacement)
    service.close()


def test_busy_track_shows_error_and_missing_track_can_be_skipped(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, _backend, access, ids, _tracks = _make_service(qapp, tmp_path, count=2)
    with access.acquire(TrackId.parse(ids[0]), "write tags"):
        service.play_queue(ids)
        assert service.state.status is PlaybackStatus.ERROR
        assert "write tags" in service.state.error_message

    service.next()
    _wait_playing(qtbot, service)
    assert service.state.current_id == ids[1]
    service.close()

    missing_service, _backend, missing_access, missing_ids, _ = _make_service(
        qapp, tmp_path / "missing", count=2
    )
    Path(str(_track(missing_ids[0], tmp_path / "missing" / "track-0.wav")["path"])).unlink()
    missing_service.play_queue(missing_ids)
    assert missing_service.state.status is PlaybackStatus.ERROR
    missing_service.next()
    _wait_playing(qtbot, missing_service)
    assert missing_service.state.current_id == missing_ids[1]
    assert not missing_access.is_busy(TrackId.parse(missing_ids[0]))
    missing_service.close()


def test_explicit_stop_releases_exclusive_access_and_closes_one_backend(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, access, ids, _ = _make_service(qapp, tmp_path, count=1)
    service.play_queue(ids)
    _wait_playing(qtbot, service)
    with (
        pytest.raises(FileAccessTimeoutError),
        access.acquire(TrackId.parse(ids[0]), "write tags", timeout_seconds=0),
    ):
        pass

    assert service.stop_and_release(ids[0])
    qtbot.waitUntil(lambda: not access.is_busy(TrackId.parse(ids[0])))
    with access.acquire(TrackId.parse(ids[0]), "write tags", timeout_seconds=0):
        assert access.holder_of(TrackId.parse(ids[0])) == "write tags"
    assert len(backend.loads) == 1
    service.close()
    assert backend.closed
