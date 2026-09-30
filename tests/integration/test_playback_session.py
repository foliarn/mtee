"""Closing and recreating the player restores a persisted queue in pause."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtee.domain.playback import PlaybackStatus
from mtee.domain.tracks import TrackId
from mtee.persistence.database import Database
from mtee.persistence.playback_repository import PlaybackRepository, PlaybackSession
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.player_backend import BackendEvent, BackendEventHandler
from mtee.services.player_service import PlayerService


class SessionBackend:
    def __init__(self) -> None:
        self.handler: BackendEventHandler | None = None
        self.loads: list[tuple[Path, int, bool]] = []
        self.paused = False
        self.position = 0
        self.seeks: list[int] = []
        self.session_id = 0
        self.auto_loaded = True
        self.closed = False

    def set_event_handler(self, handler: BackendEventHandler | None) -> None:
        self.handler = handler

    def load(self, path: Path, session_id: int) -> None:
        self.session_id = session_id
        self.loads.append((path, session_id, self.paused))
        self.emit("duration", session_id, 12_000_000)
        self.emit("seekable", session_id, True)
        if self.auto_loaded:
            self.emit("loaded", session_id)

    def emit(self, name: str, session_id: int, value: object = None) -> None:
        if self.handler is not None:
            self.handler(BackendEvent(name, session_id, value))

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    def set_volume(self, value: int) -> None:
        pass

    def seek(self, position_us: int) -> None:
        self.position = position_us
        self.seeks.append(position_us)

    def position_us(self) -> int:
        return self.position

    def stop(self) -> None:
        self.emit("stopped", self.session_id)

    def close(self) -> None:
        self.closed = True


def test_two_player_instances_restore_current_position_and_duplicates_paused(
    qapp, qtbot, tmp_path: Path
) -> None:
    database = Database(tmp_path / "audio.sqlite3")
    database.migrate()
    repository = PlaybackRepository(database)
    tracks: dict[str, dict[str, object]] = {}
    ids = []
    for index in range(3):
        identity = str(TrackId.new())
        path = tmp_path / f"track-{index}.wav"
        path.write_bytes(b"service fixture")
        ids.append(identity)
        tracks[identity] = {
            "id": identity,
            "path": str(path),
            "title": f"Track {index}",
            "status": "readable",
            "durationUs": 12_000_000,
        }

    def resolver(identity: str) -> dict[str, object]:
        return dict(tracks[identity])

    first_backend = SessionBackend()
    first = PlayerService(resolver, FileAccessCoordinator(), first_backend, parent=qapp)
    first.attach_session(repository, None)
    first.play_queue(ids[:2], source="folder:test")
    qtbot.waitUntil(lambda: first.state.status is PlaybackStatus.PLAYING)
    duplicate_ids = first.enqueue_tracks([ids[2], ids[2]])
    first_backend.position = 3_400_000
    first.pause()
    first.flush_session()
    first.close()

    saved = repository.load()
    assert saved is not None
    assert saved.position_us == 3_400_000
    second_backend = SessionBackend()
    second = PlayerService(resolver, FileAccessCoordinator(), second_backend, parent=qapp)
    second.attach_session(repository, saved)
    assert second_backend.loads[0][2] is True
    qtbot.waitUntil(lambda: second.state.status is PlaybackStatus.PAUSED)
    qtbot.waitUntil(lambda: second.state.position_us == 3_400_000)
    assert second_backend.seeks == [3_400_000]
    assert [row["entryId"] for row in second.up_next()[:2]] == list(duplicate_ids)
    second.resume()
    assert second.state.status is PlaybackStatus.PLAYING
    second.close()

    (tmp_path / "track-0.wav").unlink()
    last_saved = repository.load()
    assert last_saved is not None
    missing_backend = SessionBackend()
    missing = PlayerService(resolver, FileAccessCoordinator(), missing_backend, parent=qapp)
    missing.attach_session(repository, last_saved)
    assert missing.state.status is PlaybackStatus.ERROR
    assert missing.state.current_id == ids[0]
    assert [row["entryId"] for row in missing.up_next()[:2]] == list(duplicate_ids)
    missing.next()
    qtbot.waitUntil(lambda: missing.state.status is PlaybackStatus.PLAYING)
    assert missing.state.current_entry_id == duplicate_ids[0]
    missing.close()
    database.close()


def test_late_restore_events_do_not_seek_a_new_track(qapp, qtbot, tmp_path: Path) -> None:
    database = Database(tmp_path / "audio.sqlite3")
    database.migrate()
    repository = PlaybackRepository(database)
    tracks: dict[str, dict[str, object]] = {}
    ids = []
    for index in range(2):
        identity = str(TrackId.new())
        path = tmp_path / f"track-{index}.wav"
        path.write_bytes(b"service fixture")
        ids.append(identity)
        tracks[identity] = {"id": identity, "path": str(path), "status": "readable"}

    def resolver(identity: str) -> dict[str, object]:
        return dict(tracks[identity])

    first_backend = SessionBackend()
    first = PlayerService(resolver, FileAccessCoordinator(), first_backend, parent=qapp)
    first.attach_session(repository, None)
    first.play_queue(ids)
    qtbot.waitUntil(lambda: first.state.status is PlaybackStatus.PLAYING)
    first_backend.position = 2_000_000
    first.flush_session()
    first.close()
    saved = repository.load()
    assert saved is not None

    second_backend = SessionBackend()
    second_backend.auto_loaded = False
    second = PlayerService(resolver, FileAccessCoordinator(), second_backend, parent=qapp)
    second.attach_session(repository, saved)
    restore_id = second.state.session_id
    second.play_queue(ids, start_index=1)
    new_id = second.state.session_id
    second_backend.emit("loaded", restore_id)
    second_backend.emit("loaded", new_id)
    qtbot.waitUntil(lambda: second.state.status is PlaybackStatus.PLAYING)
    assert second.state.current_id == ids[1]
    assert second_backend.seeks == []
    second.close()
    database.close()


def test_failed_session_save_still_closes_native_backend(qapp, tmp_path: Path) -> None:
    database = Database(tmp_path / "audio.sqlite3")
    database.migrate()

    class FailingRepository(PlaybackRepository):
        def save(self, session: PlaybackSession) -> bool:
            raise OSError("storage unavailable")

    backend = SessionBackend()
    service = PlayerService(lambda identity: {}, FileAccessCoordinator(), backend, parent=qapp)
    service.attach_session(FailingRepository(database), None)
    service.enqueue_tracks([str(TrackId.new())])
    with pytest.raises(OSError, match="storage unavailable"):
        service.close()
    assert backend.closed
    database.close()
