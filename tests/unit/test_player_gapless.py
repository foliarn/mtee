"""Prefetch of the next track and the gapless switch, with a fake backend that queues one entry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from mtee.domain.loudness import NormalizationSettings
from mtee.domain.play_log import ClockReading
from mtee.domain.playback import PlaybackStatus
from mtee.domain.tracks import TrackId
from mtee.persistence.database import Database
from mtee.persistence.play_log_repository import PlayLogRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.player_backend import BackendEvent, BackendEventHandler, GaplessPlayerBackend
from mtee.services.player_service import PlayerService

BASE_WALL = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
DURATION_US = 40_000_000
NEAR_END_US = 30_000_000  # 10 s left: inside the prefetch window
DEVICE = str(uuid4())


class FakeClock:
    def __init__(self) -> None:
        self.mono_us = 0

    def __call__(self) -> ClockReading:
        return ClockReading(self.mono_us, BASE_WALL + timedelta(microseconds=self.mono_us))

    def advance(self, seconds: float) -> None:
        self.mono_us += round(seconds * 1_000_000)


class GaplessBackend:
    """Plays one entry and holds at most one queued entry, like the mpv playlist."""

    def __init__(self) -> None:
        self.handler: BackendEventHandler | None = None
        self.active_session_id = 0
        self.position = 0
        self.loads: list[tuple[Path, int]] = []
        self.queued: tuple[Path, int, float] | None = None
        self.queue_history: list[tuple[Path, int, float]] = []
        self.clears = 0
        self.stops = 0
        self.refuse_queue = False

    def set_event_handler(self, handler: BackendEventHandler | None) -> None:
        self.handler = handler

    def load(self, path: Any, session_id: int) -> None:
        self.queued = None
        self.active_session_id = session_id
        self.loads.append((path, session_id))
        self.position = 0
        self.emit("duration", session_id, DURATION_US)
        self.emit("seekable", session_id, True)
        self.emit("loaded", session_id)

    def queue_next(self, path: Any, session_id: int, gain_db: float) -> None:
        if self.refuse_queue:
            raise OSError("fake refusal")
        self.queued = (path, session_id, gain_db)
        self.queue_history.append(self.queued)

    def clear_next(self) -> None:
        self.clears += 1
        self.queued = None

    def finish_current(self) -> None:
        """The playing entry reaches its end; mpv moves on to the queued one if there is one."""
        ended = self.active_session_id
        self.emit("eof", ended)
        if self.queued is None:
            return
        _path, session_id, _gain = self.queued
        self.queued = None
        self.active_session_id = session_id
        self.position = 0
        self.emit("start-file", session_id)
        self.emit("duration", session_id, DURATION_US)
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
        self.stops += 1
        self.queued = None
        self.emit("stopped", self.active_session_id)

    def close(self) -> None:
        pass

    def emit(self, name: str, session_id: int, value: object = None) -> None:
        if self.handler is not None:
            self.handler(BackendEvent(name, session_id, value))


def _setup(qapp, tmp_path: Path, count: int = 3, *, loudness: dict[int, float] | None = None):
    rows: dict[str, dict[str, object]] = {}
    ids: list[str] = []
    for index in range(count):
        track_id = str(TrackId.new())
        path = tmp_path / "media" / f"t{index}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic audio fixture")
        ids.append(track_id)
        rows[track_id] = {
            "id": track_id,
            "title": f"Title {index}",
            "artist": "Artist",
            "album": "Album",
            "path": str(path),
            "durationUs": DURATION_US,
            "status": "readable",
            "loudnessLufs": (loudness or {}).get(index),
            "samplePeakDbfs": -6.0,
        }
    backend = GaplessBackend()
    assert isinstance(backend, GaplessPlayerBackend)
    clock = FakeClock()
    access = FileAccessCoordinator()
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    service = PlayerService(
        lambda track_id: dict(rows.get(track_id, {})),
        access,
        backend,
        parent=qapp,
        clock=clock,
    )
    service.attach_play_log(PlayLogRepository(database), DEVICE)
    return service, backend, clock, database, ids, access


def _play(qtbot, service: PlayerService, backend: GaplessBackend, ids: list[str], start: int = 0):
    service.play_queue(ids, start)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING)


def _near_end(qtbot, backend: GaplessBackend) -> None:
    backend.position = NEAR_END_US
    qtbot.waitUntil(lambda: backend.queued is not None, timeout=3000)


def _plays(database: Database) -> list[dict[str, object]]:
    cursor = database.connection().execute(
        "SELECT * FROM play_events ORDER BY started_at_utc, event_id"
    )
    return [dict(row) for row in cursor.fetchall()]


def test_the_next_track_is_queued_only_near_the_end(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _clock, database, ids, access = _setup(qapp, tmp_path)
    _play(qtbot, service, backend, ids)

    qtbot.wait(300)
    assert backend.queued is None  # 40 s left: the next file is not opened yet
    assert not access.is_busy(TrackId.parse(ids[1]))

    _near_end(qtbot, backend)
    path, session_id, gain = backend.queued or (Path(), 0, 0.0)
    assert path.name == "t1.wav"
    assert session_id > service.state.session_id
    assert gain == 0.0
    assert access.is_busy(TrackId.parse(ids[1]))  # the opened file is read-locked
    service.close()
    database.close()


def test_the_queued_entry_carries_its_own_normalization_gain(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _clock, database, ids, _access = _setup(
        qapp, tmp_path, loudness={0: -14.0, 1: -20.0}
    )
    service.set_normalization(NormalizationSettings(enabled=True))
    _play(qtbot, service, backend, ids)
    _near_end(qtbot, backend)
    first_gain = backend.queued[2] if backend.queued else None
    assert first_gain is not None and first_gain > 0  # -20 LUFS track is raised

    service.set_normalization(NormalizationSettings(enabled=False))
    qtbot.waitUntil(lambda: backend.queued is not None and backend.queued[2] == 0.0)
    service.close()
    database.close()


def test_the_switch_advances_the_queue_and_queues_the_following_track(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, _clock, database, ids, access = _setup(qapp, tmp_path)
    _play(qtbot, service, backend, ids)
    _near_end(qtbot, backend)
    loads_before = len(backend.loads)
    stops_before = backend.stops
    queued_session = backend.queued[1] if backend.queued else 0

    backend.finish_current()
    qtbot.waitUntil(lambda: service.state.current_id == ids[1])

    assert service.state.session_id == queued_session
    assert service.state.current_index == 1
    assert service.state.status is PlaybackStatus.PLAYING
    assert service.queue_state.current is not None
    assert service.queue_state.current.track_id == ids[1]
    assert [e.track_id for e in service.queue_state.past] == [ids[0]]
    qtbot.waitUntil(lambda: service.state.seekable)
    assert len(backend.loads) == loads_before  # nothing was loaded again
    assert backend.stops == stops_before  # and nothing was stopped
    assert not access.is_busy(TrackId.parse(ids[0]))  # the finished track is released

    _near_end(qtbot, backend)
    assert backend.queued is not None and backend.queued[0].name == "t2.wav"
    service.close()
    database.close()


def test_the_last_track_queues_nothing_and_ends_normally(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _clock, database, ids, _access = _setup(qapp, tmp_path, count=2)
    _play(qtbot, service, backend, ids, start=1)
    backend.position = NEAR_END_US
    qtbot.wait(400)
    assert backend.queued is None

    backend.finish_current()
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.ENDED)
    service.close()
    database.close()


def test_repeat_modes_decide_what_is_queued(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _clock, database, ids, _access = _setup(qapp, tmp_path, count=2)
    _play(qtbot, service, backend, ids, start=1)
    service.cycle_repeat()  # off -> all
    _near_end(qtbot, backend)
    assert backend.queued is not None and backend.queued[0].name == "t0.wav"

    service.cycle_repeat()  # all -> one: the same track again
    qtbot.waitUntil(lambda: backend.queued is not None and backend.queued[0].name == "t1.wav")
    backend.finish_current()
    qtbot.waitUntil(lambda: service.state.session_id == backend.active_session_id)
    assert service.state.current_id == ids[1]
    assert service.state.status is PlaybackStatus.PLAYING
    service.close()
    database.close()


def test_queue_edits_replace_the_queued_entry(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _clock, database, ids, access = _setup(qapp, tmp_path, count=4)
    _play(qtbot, service, backend, ids[:3])
    _near_end(qtbot, backend)
    assert backend.queued and backend.queued[0].name == "t1.wav"

    # Play next: a manual track goes in front of the context tracks.
    service.enqueue_tracks([ids[3]])
    qtbot.waitUntil(lambda: backend.queued is not None and backend.queued[0].name == "t3.wav")
    assert backend.clears >= 1
    assert not access.is_busy(TrackId.parse(ids[1]))  # the cancelled file is released
    assert access.is_busy(TrackId.parse(ids[3]))

    entry = service.queue_state.upcoming[0]
    service.remove_queue_entry(entry.entry_id)
    qtbot.waitUntil(lambda: backend.queued is not None and backend.queued[0].name == "t1.wav")
    service.close()
    database.close()


def test_shuffle_and_repeat_changes_cancel_a_stale_entry(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _clock, database, ids, _access = _setup(qapp, tmp_path, count=2)
    _play(qtbot, service, backend, ids)
    _near_end(qtbot, backend)
    history_before = len(backend.queue_history)

    service.toggle_shuffle()
    qtbot.waitUntil(lambda: len(backend.queue_history) > history_before)
    assert backend.clears >= 1
    assert backend.queued is not None  # re-prepared for the new queue

    # Repeat all on the last track would wrap; at the end of the list with repeat off, nothing.
    service.close()
    database.close()


def test_a_manual_skip_drops_the_queued_entry_and_loads_as_before(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, _clock, database, ids, access = _setup(qapp, tmp_path)
    _play(qtbot, service, backend, ids)
    _near_end(qtbot, backend)

    service.next()
    qtbot.waitUntil(lambda: service.state.current_id == ids[1])
    assert backend.stops >= 1
    assert backend.loads[-1][0].name == "t1.wav"
    assert backend.loads[-1][1] == service.state.session_id
    # The skipped entry's session number is never reused by the new load.
    assert all(entry[1] != service.state.session_id for entry in backend.queue_history)
    service.close()
    database.close()
    assert not access.is_busy(TrackId.parse(ids[2]))


def test_a_busy_or_missing_next_file_falls_back_to_loading_it_at_the_end(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, _clock, database, ids, access = _setup(qapp, tmp_path)
    _play(qtbot, service, backend, ids)
    with access.acquire(TrackId.parse(ids[1]), "tag edit"):
        backend.position = NEAR_END_US
        qtbot.wait(400)
        assert backend.queued is None
    service.close()
    database.close()


def test_a_refusing_backend_does_not_break_playback(qapp, qtbot, tmp_path: Path) -> None:
    service, backend, _clock, database, ids, access = _setup(qapp, tmp_path)
    backend.refuse_queue = True
    _play(qtbot, service, backend, ids)
    backend.position = NEAR_END_US
    qtbot.wait(400)
    assert backend.queued is None
    assert not access.is_busy(TrackId.parse(ids[1]))

    backend.finish_current()  # no queued entry: the end of the file loads the next track
    qtbot.waitUntil(lambda: service.state.current_id == ids[1])
    assert backend.loads[-1][0].name == "t1.wav"
    service.close()
    database.close()


def test_the_play_log_has_one_row_per_track_across_a_gapless_switch(
    qapp, qtbot, tmp_path: Path
) -> None:
    service, backend, clock, database, ids, _access = _setup(qapp, tmp_path)
    _play(qtbot, service, backend, ids)
    clock.advance(40)
    _near_end(qtbot, backend)

    backend.finish_current()  # a ends after 40 s, b starts at the same instant
    qtbot.waitUntil(lambda: service.state.current_id == ids[1])
    qtbot.waitUntil(lambda: service.state.seekable)
    clock.advance(7)
    service.close()

    rows = _plays(database)
    assert [row["track_id"] for row in rows] == [ids[0], ids[1]]
    first, second = rows
    assert first["heard_ms"] == 40_000
    assert first["counted"] == 1
    assert second["heard_ms"] == 7_000
    assert second["counted"] == 0
    # The second listening starts where the first one ended.
    assert first["ended_at_utc"] == second["started_at_utc"]
    database.close()
