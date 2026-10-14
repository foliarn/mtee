"""Player-level recording of the permanent listening log, with a fake backend and clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from mtee.domain.play_log import ClockReading
from mtee.domain.playback import PlaybackStatus
from mtee.domain.tracks import TrackId
from mtee.persistence.database import Database
from mtee.persistence.play_log_repository import PlayLogRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.player_backend import BackendEvent, BackendEventHandler
from mtee.services.player_service import PlayerService

BASE_WALL = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)
LONG_US = 180_000_000
SHORT_US = 20_000_000
DEVICE = str(uuid4())


class FakeClock:
    """Monotonic time that moves only when the test says so."""

    def __init__(self) -> None:
        self.mono_us = 0

    def __call__(self) -> ClockReading:
        return ClockReading(self.mono_us, BASE_WALL + timedelta(microseconds=self.mono_us))

    def advance(self, seconds: float) -> None:
        self.mono_us += round(seconds * 1_000_000)


class FakeBackend:
    """Event-driven stand-in for libmpv: the durations come from the file name."""

    def __init__(self, durations: dict[str, int]) -> None:
        self.durations = durations
        self.handler: BackendEventHandler | None = None
        self.active_session_id = 0
        self.position = 0
        self.fail_load = False

    def set_event_handler(self, handler: BackendEventHandler | None) -> None:
        self.handler = handler

    def load(self, path: Path, session_id: int) -> None:
        if self.fail_load:
            raise OSError("fake decoder error")
        self.active_session_id = session_id
        self.position = 0
        self.emit("duration", session_id, self.durations[path.stem])
        self.emit("seekable", session_id, True)
        self.emit("loaded", session_id)

    def set_paused(self, paused: bool) -> None:
        if self.active_session_id:
            self.emit("pause", self.active_session_id, paused)

    def seek(self, position_us: int) -> None:
        self.position = position_us

    def set_volume(self, value: int) -> None:
        pass

    def set_gain_db(self, value: float) -> None:
        pass

    def position_us(self) -> int:
        return self.position

    def stop(self) -> None:
        self.emit("stopped", self.active_session_id)

    def close(self) -> None:
        pass

    def emit(self, name: str, session_id: int, value: object = None) -> None:
        if self.handler is not None:
            self.handler(BackendEvent(name, session_id, value))


def _setup(qapp, tmp_path: Path, names: dict[str, int]):
    """Create one audio file per name, a database with the play log, and the service."""
    rows: dict[str, dict[str, object]] = {}
    ids: dict[str, str] = {}
    for name, duration_us in names.items():
        track_id = str(TrackId.new())
        path = tmp_path / "media" / f"{name}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic audio fixture")
        ids[name] = track_id
        rows[track_id] = {
            "id": track_id,
            "title": f"Title {name}",
            "artist": f"Artist {name}",
            "album": "Album",
            "path": str(path),
            "seconds": duration_us // 1_000_000,
            "durationUs": duration_us,
            "status": "readable",
        }
    clock = FakeClock()
    backend = FakeBackend({name: duration for name, duration in names.items()})
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    service = PlayerService(
        lambda track_id: dict(rows.get(track_id, {})),
        FileAccessCoordinator(),
        backend,
        parent=qapp,
        clock=clock,
    )
    service.attach_play_log(PlayLogRepository(database), DEVICE)
    return service, backend, clock, database, ids


def _playing(qtbot, service: PlayerService, track_id: str, session_id: int | None = None) -> None:
    def ready() -> bool:
        if service.state.status is not PlaybackStatus.PLAYING:
            return False
        if service.state.current_id != track_id:
            return False
        return session_id is None or service.state.session_id == session_id

    qtbot.waitUntil(ready)
    qtbot.waitUntil(lambda: service.state.seekable)


def _rows(database: Database) -> list[dict[str, object]]:
    cursor = database.connection().execute(
        "SELECT * FROM play_events ORDER BY started_at_utc, event_id"
    )
    return [dict(row) for row in cursor.fetchall()]


def test_pause_resume_and_track_change_are_recorded(qapp, qtbot, tmp_path: Path) -> None:
    service, _backend, clock, database, ids = _setup(qapp, tmp_path, {"a": LONG_US, "b": LONG_US})
    service.play_queue([ids["a"], ids["b"]], 0, source="folder:media", source_title="media")
    _playing(qtbot, service, ids["a"])

    clock.advance(40)
    service.pause()
    clock.advance(100)
    service.resume()
    clock.advance(20)
    service.next()
    _playing(qtbot, service, ids["b"])
    clock.advance(5)
    service.close()

    rows = _rows(database)
    assert [row["track_id"] for row in rows] == [ids["a"], ids["b"]]
    first, second = rows
    assert first["heard_ms"] == 60_000
    assert first["counted"] == 1
    assert first["started_at_utc"] == "2026-10-14T18:00:00.000000Z"
    assert first["ended_at_utc"] == "2026-10-14T18:02:40.000000Z"
    assert first["artist"] == "Artist a"
    assert first["title"] == "Title a"
    assert first["album"] == "Album"
    assert first["duration_us"] == LONG_US
    assert str(first["path_at_play"]).endswith("a.wav")
    assert first["device_id"] == DEVICE
    assert second["heard_ms"] == 5_000
    assert second["counted"] == 0
    database.close()


def test_seek_and_previous_to_start_begin_a_new_listening(qapp, qtbot, tmp_path: Path) -> None:
    service, _backend, clock, database, ids = _setup(qapp, tmp_path, {"a": LONG_US})
    service.play_queue([ids["a"]], 0)
    _playing(qtbot, service, ids["a"])

    clock.advance(5)
    service.seek(120_000_000)  # the skipped two minutes are not heard
    clock.advance(5)
    service.previous()  # at 2:00, Previous restarts the track: a new listening
    clock.advance(35)
    service.close()

    first, second = _rows(database)
    assert first["heard_ms"] == 10_000
    assert first["counted"] == 0
    assert second["heard_ms"] == 35_000
    assert second["counted"] == 1
    database.close()


def test_repeat_one_and_a_natural_end_record_each_pass(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, clock, database, ids = _setup(qapp, tmp_path, {"s": SHORT_US})
    service.cycle_repeat()
    service.cycle_repeat()  # off -> all -> one
    service.play_queue([ids["s"]], 0)
    _playing(qtbot, service, ids["s"])

    clock.advance(20)
    backend.emit("eof", backend.active_session_id)  # the short track reaches its end
    _playing(qtbot, service, ids["s"], session_id=2)
    clock.advance(3)
    service.close()

    first, second = _rows(database)
    assert first["heard_ms"] == 20_000
    assert first["counted"] == 1  # a short track counts when played to its end
    assert second["heard_ms"] == 3_000
    assert second["counted"] == 0
    database.close()


def test_a_failed_load_writes_nothing_and_shutdown_flushes_the_open_listening(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, clock, database, ids = _setup(qapp, tmp_path, {"a": LONG_US, "b": LONG_US})
    backend.fail_load = True
    service.play_queue([ids["a"]], 0)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.ERROR)
    clock.advance(10)

    backend.fail_load = False
    service.play_queue([ids["b"]], 0)
    _playing(qtbot, service, ids["b"])
    clock.advance(12)
    service.close()  # application shutdown flushes the open listening

    rows = _rows(database)
    assert [row["track_id"] for row in rows] == [ids["b"]]
    assert rows[0]["heard_ms"] == 12_000
    assert rows[0]["counted"] == 0
    database.close()


def test_stopping_closes_the_listening_with_the_time_heard(qapp, qtbot, tmp_path: Path) -> None:
    service, _backend, clock, database, ids = _setup(qapp, tmp_path, {"a": LONG_US})
    service.play_queue([ids["a"]], 0)
    _playing(qtbot, service, ids["a"])
    clock.advance(31)
    service.stop_and_release(ids["a"])
    clock.advance(600)  # nothing heard after the stop
    service.close()

    rows = _rows(database)
    assert len(rows) == 1
    assert rows[0]["heard_ms"] == 31_000
    assert rows[0]["counted"] == 1
    database.close()


def test_clear_history_empties_the_panel_and_keeps_the_queue_and_the_log(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, _backend, clock, database, ids = _setup(qapp, tmp_path, {"a": LONG_US, "b": LONG_US})
    service.play_queue([ids["a"], ids["b"]], 0, source="folder:media", source_title="media")
    _playing(qtbot, service, ids["a"])
    clock.advance(40)
    service.next()
    _playing(qtbot, service, ids["b"])
    logged = len(_rows(database))
    assert len(service.history_rows()) == 1

    assert service.clear_history() == 1

    assert service.history_rows() == []
    assert service.state.current_id == ids["b"]
    assert len(_rows(database)) == logged
    assert service.clear_history() == 0
    database.close()
