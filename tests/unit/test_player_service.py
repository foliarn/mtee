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
        if self.active_session_id:
            self.emit("pause", self.active_session_id, paused)

    def seek(self, position_us: int) -> None:
        self.seeks.append(position_us)
        self.position = position_us

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


@pytest.mark.parametrize("play_index", [0, 1], ids=["reactivate-same-track", "next-track"])
def test_explicit_play_after_pause_clears_the_native_pause_state(
    qapp, qtbot, tmp_path: Path, play_index: int
) -> None:
    service, backend, _access, ids, _ = _make_service(qapp, tmp_path, count=2)
    service.play_queue(ids)
    _wait_playing(qtbot, service)

    service.pause()
    assert backend.paused
    service.play_index(play_index)
    _wait_playing(qtbot, service)

    assert service.state.current_id == ids[play_index]
    assert backend.paused is False
    assert service.state.status is PlaybackStatus.PLAYING
    service.close()


def test_pause_requested_while_loading_is_applied_when_track_loads(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, _access, ids, _ = _make_service(qapp, tmp_path, count=2)
    backend.emit_loaded_events = False

    service.play_queue(ids)
    assert service.state.status is PlaybackStatus.LOADING
    service.toggle_play()
    assert service.pause_pending
    service.toggle_play()
    assert not service.pause_pending
    service.toggle_play()
    assert service.pause_pending

    session_id = service.state.session_id
    backend.emit("loaded", session_id)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PAUSED)

    assert backend.paused
    assert not service.pause_pending
    service.toggle_play()
    assert service.state.status is PlaybackStatus.PLAYING
    assert backend.paused is False
    service.close()


def test_fast_track_changes_ignore_late_pause_and_load_events(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _access, ids, _ = _make_service(qapp, tmp_path, count=3)
    service.play_queue(ids)
    _wait_playing(qtbot, service)
    old_session = service.state.session_id
    backend.emit_loaded_events = False

    service.next()
    stale_session = service.state.session_id
    service.next()
    current_session = service.state.session_id
    backend.emit("loaded", stale_session)
    backend.emit("pause", old_session, True)
    backend.emit("loaded", current_session)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING)
    backend.emit("pause", current_session, True)
    qtbot.wait(20)

    assert service.state.current_id == ids[2]
    assert service.state.session_id == current_session
    assert service.state.status is PlaybackStatus.PLAYING
    assert backend.paused is False
    service.close()


def test_failed_new_track_does_not_report_playing_after_a_paused_track(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, _access, ids, _ = _make_service(qapp, tmp_path, count=2)
    service.play_queue(ids)
    _wait_playing(qtbot, service)
    service.pause()
    backend.fail_load = True

    service.next()

    assert service.state.current_id == ids[1]
    assert service.state.status is PlaybackStatus.ERROR
    assert service.state.error_message == "fake decoder error"
    assert backend.paused is False
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


def test_manual_entries_survive_context_change_and_are_consumed_once(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, _access, ids, tracks = _make_service(qapp, tmp_path, count=5)
    service.play_queue(ids[:3], source="folder:first")
    _wait_playing(qtbot, service)
    before_loads = len(backend.loads)
    first, second = service.enqueue_tracks([ids[4], ids[4]], tracks=[tracks[ids[4]]])
    assert first != second
    assert [row["entryId"] for row in service.up_next()[:2]] == [first, second]
    assert len(backend.loads) == before_loads
    assert service.state.position_us == 0

    service.play_queue(ids[2:4], start_index=0, source="folder:second")
    _wait_playing(qtbot, service)
    assert [row["entryId"] for row in service.up_next()[:2]] == [first, second]
    service.next()
    _wait_playing(qtbot, service)
    assert service.queue_state.current is not None
    assert service.queue_state.current.entry_id == first
    assert service.state.current_entry_id == first
    service.next()
    _wait_playing(qtbot, service)
    assert service.queue_state.current is not None
    assert service.queue_state.current.entry_id == second
    assert [row["id"] for row in service.up_next()] == [ids[3]]
    service.close()


def test_editing_upcoming_by_occurrence_does_not_reload_current(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, _access, ids, _tracks = _make_service(qapp, tmp_path, count=4)
    service.play_queue(ids)
    _wait_playing(qtbot, service)
    a, b = service.enqueue_tracks([ids[3], ids[3]])
    initial_session = service.state.session_id
    initial_loads = len(backend.loads)
    assert service.move_queue_entry(b, a)
    assert service.remove_queue_entry(a)
    assert not service.remove_queue_entry(a)
    assert service.state.session_id == initial_session
    assert len(backend.loads) == initial_loads
    assert next(row["entryId"] for row in service.up_next()) == b
    service.close()


def test_repeat_one_keeps_manual_pending_until_mode_changes(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _access, ids, _tracks = _make_service(qapp, tmp_path, count=2)
    service.play_queue(ids[:1])
    _wait_playing(qtbot, service)
    manual_entry = service.enqueue_tracks(ids[1:])[0]
    service.cycle_repeat()
    service.cycle_repeat()
    assert service.state.repeat == "one"
    backend.emit("eof", service.state.session_id)
    qtbot.waitUntil(lambda: len(backend.loads) == 2)
    _wait_playing(qtbot, service)
    assert service.state.current_id == ids[0]
    assert service.up_next()[0]["entryId"] == manual_entry
    service.cycle_repeat()
    backend.emit("eof", service.state.session_id)
    qtbot.waitUntil(lambda: service.state.current_id == ids[1])
    assert service.state.current_entry_id == manual_entry
    service.close()


def test_enqueue_without_current_waits_for_explicit_play(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _access, ids, _tracks = _make_service(qapp, tmp_path, count=1)
    entry_id = service.enqueue_tracks(ids)[0]
    assert service.state.current_id == ""
    assert not backend.loads
    service.toggle_play()
    _wait_playing(qtbot, service)
    assert service.state.current_entry_id == entry_id
    service.close()
