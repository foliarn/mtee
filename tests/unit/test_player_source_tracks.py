"""The player and the tracks that a plugin provides without a file (plan 125.2).

A fake backend stands for libmpv and a fake opener for the plugins. The real libmpv is used by
``tests/integration/test_mpv_track_sources.py``.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from mtee.domain.play_log import ClockReading
from mtee.domain.playback import PlaybackStatus
from mtee.domain.playback_queue import QueueEntry, QueueState
from mtee.domain.source_tracks import PlayableSource
from mtee.domain.tracks import TrackId
from mtee.persistence.database import Database
from mtee.persistence.play_log_repository import PlayLogRepository
from mtee.persistence.playback_repository import PlaybackRepository, PlaybackSession
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.player_backend import BackendEvent, BackendEventHandler
from mtee.services.player_service import PlayerService
from mtee.services.track_sources import SourceOpenError

BASE_WALL = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
DURATION_US = 40_000_000
NEAR_END_US = 30_000_000
DEVICE = str(uuid4())
URL = "http://127.0.0.1:1/track.flac"


class _Clock:
    def __init__(self) -> None:
        self.mono_us = 0

    def __call__(self) -> ClockReading:
        return ClockReading(self.mono_us, BASE_WALL + timedelta(microseconds=self.mono_us))

    def advance(self, seconds: float) -> None:
        self.mono_us += round(seconds * 1_000_000)


class _Backend:
    """A gapless backend that records what it was given and plays it at once."""

    def __init__(self) -> None:
        self.handler: BackendEventHandler | None = None
        self.active_session_id = 0
        self.position = 0
        self.loads: list[tuple[Path | PlayableSource, int]] = []
        self.queued: tuple[Path | PlayableSource, int, float] | None = None
        self.fail_with: str | None = None

    def set_event_handler(self, handler: BackendEventHandler | None) -> None:
        self.handler = handler

    def load(self, source: Path | PlayableSource, session_id: int) -> None:
        self.queued = None
        self.active_session_id = session_id
        self.loads.append((source, session_id))
        self.position = 0
        if self.fail_with is not None:
            self.emit("start-file", session_id)
            self.emit("error", session_id, self.fail_with)
            return
        self.emit("duration", session_id, DURATION_US)
        self.emit("seekable", session_id, True)
        self.emit("loaded", session_id)

    def queue_next(self, source: Path | PlayableSource, session_id: int, gain_db: float) -> None:
        self.queued = (source, session_id, gain_db)

    def clear_next(self) -> None:
        self.queued = None

    def finish_current(self) -> None:
        ended = self.active_session_id
        self.emit("eof", ended)
        if self.queued is None:
            return
        _source, session_id, _gain = self.queued
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
        self.queued = None
        self.emit("stopped", self.active_session_id)

    def close(self) -> None:
        pass

    def emit(self, name: str, session_id: int, value: object = None) -> None:
        if self.handler is not None:
            self.handler(BackendEvent(name, session_id, value))


class _Opener:
    """Stands for the running plugins: it resolves a key to a source, or raises like a plugin."""

    def __init__(self, sources: dict[str, PlayableSource | str]) -> None:
        self.sources = sources
        self.calls: list[tuple[str, str, int]] = []
        self.gate: threading.Event | None = None

    def open(self, plugin_id: str, source_key: str) -> PlayableSource:
        self.calls.append((plugin_id, source_key, threading.get_ident()))
        if self.gate is not None:
            self.gate.wait(5)
        found = self.sources[source_key]
        if isinstance(found, str):
            raise SourceOpenError(f"Remote could not open this track: {found}")
        return found

    def plugin_title(self, plugin_id: str) -> str:
        return "Remote" if plugin_id == "remote" else plugin_id


def _row(index: int, **extra: object) -> dict[str, object]:
    track_id = str(TrackId.new())
    row: dict[str, object] = {
        "id": track_id,
        "title": f"Title {index}",
        "artist": "Artist",
        "album": "Album",
        "path": "",
        "durationUs": DURATION_US,
        "status": "readable",
        "sourcePluginId": "remote",
        "sourceKey": f"key-{index}",
    }
    row.update(extra)
    return row


def _setup(qapp, tmp_path: Path, rows: list[dict[str, object]], opener: _Opener | None):
    by_id = {str(row["id"]): row for row in rows}
    backend = _Backend()
    access = FileAccessCoordinator()
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    clock = _Clock()
    service = PlayerService(
        lambda track_id: dict(by_id.get(track_id, {})),
        access,
        backend,
        parent=qapp,
        clock=clock,
    )
    service.attach_play_log(PlayLogRepository(database), DEVICE)
    if opener is not None:
        service.attach_track_sources(opener)
    notices: list[str] = []
    service.sourceFailed.connect(notices.append)
    return service, backend, access, database, [str(row["id"]) for row in rows], notices, clock


def _plays(database: Database) -> list[dict[str, object]]:
    cursor = database.connection().execute("SELECT * FROM play_events ORDER BY started_at_utc")
    return [dict(row) for row in cursor.fetchall()]


def test_a_url_source_is_resolved_off_the_graphical_thread_and_loaded_with_its_headers(
    qapp, qtbot, tmp_path: Path
) -> None:
    rows = [_row(0)]
    source = PlayableSource(url=URL, headers={"Authorization": "Bearer abc"})
    opener = _Opener({"key-0": source})
    service, backend, access, database, ids, _notices, _clock = _setup(qapp, tmp_path, rows, opener)

    service.play_queue(ids)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING, timeout=5000)

    assert backend.loads == [(source, service.state.session_id)]
    assert opener.calls[0][:2] == ("remote", "key-0")
    assert opener.calls[0][2] != threading.get_ident()  # a worker thread, not the GUI thread
    # A URL source is never locked by the file-access coordinator.
    assert not access.is_busy(TrackId.parse(ids[0]))
    service.close()
    database.close()


def test_a_local_path_source_holds_a_read_lease_like_a_library_file(
    qapp, qtbot, tmp_path: Path
) -> None:
    downloaded = tmp_path / "downloaded.flac"
    downloaded.write_bytes(b"audio")
    rows = [_row(0)]
    opener = _Opener({"key-0": PlayableSource(path=downloaded)})
    service, backend, access, database, ids, _notices, _clock = _setup(qapp, tmp_path, rows, opener)

    service.play_queue(ids)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING, timeout=5000)
    assert backend.loads[0][0] == PlayableSource(path=downloaded)
    assert access.is_busy(TrackId.parse(ids[0]))
    service.close()
    database.close()


def test_a_listening_to_a_plugin_track_is_logged(qapp, qtbot, tmp_path: Path) -> None:
    rows = [_row(0)]
    opener = _Opener({"key-0": PlayableSource(url=URL)})
    service, backend, _access, database, ids, _notices, clock = _setup(qapp, tmp_path, rows, opener)
    service.play_queue(ids)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING, timeout=5000)
    clock.advance(45)
    backend.finish_current()
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.ENDED, timeout=5000)
    service.flush_session()

    (event,) = _plays(database)
    assert event["track_id"] == ids[0]
    assert event["title"] == "Title 0"
    assert event["path_at_play"] == ""  # no file
    assert event["counted"] == 1
    service.close()
    database.close()


def test_a_source_that_fails_to_resolve_names_the_plugin_and_skips_to_the_next_track(
    qapp, qtbot, tmp_path: Path
) -> None:
    rows = [_row(0), _row(1)]
    opener = _Opener({"key-0": "the server said 403", "key-1": PlayableSource(url=URL)})
    service, backend, _access, database, ids, notices, _clock = _setup(qapp, tmp_path, rows, opener)

    service.play_queue(ids)
    qtbot.waitUntil(lambda: service.state.current_id == ids[1], timeout=5000)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING, timeout=5000)

    assert notices == ["Remote could not open this track: the server said 403"]
    assert [load[0] for load in backend.loads] == [PlayableSource(url=URL)]  # first never loaded
    service.flush_session()
    assert _plays(database) == []  # the track that could not be opened leaves no listening
    service.close()
    database.close()


def test_a_failing_last_track_stays_in_the_error_state_with_the_message(
    qapp, qtbot, tmp_path: Path
) -> None:
    rows = [_row(0)]
    opener = _Opener({"key-0": "offline"})
    service, backend, _access, database, ids, notices, _clock = _setup(qapp, tmp_path, rows, opener)

    service.play_queue(ids)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.ERROR, timeout=5000)

    assert "Remote" in service.state.error_message
    assert notices == [service.state.error_message]
    assert backend.loads == []
    service.close()
    database.close()


def test_a_plugin_that_raises_a_plain_error_is_reported_with_the_exception_text(
    qapp, qtbot, tmp_path: Path
) -> None:
    class Raising(_Opener):
        def open(self, plugin_id: str, source_key: str) -> PlayableSource:
            raise ConnectionError("no route to host")

    rows = [_row(0), _row(1)]
    service, backend, _access, database, ids, notices, _clock = _setup(
        qapp, tmp_path, rows, Raising({})
    )
    service.play_queue(ids)
    qtbot.waitUntil(lambda: len(notices) == 2, timeout=5000)  # both fail, one after the other
    assert notices == ["no route to host", "no route to host"]
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.ERROR, timeout=5000)
    assert backend.loads == []
    service.close()
    database.close()


def test_a_track_the_plugin_no_longer_provides_is_not_opened_and_is_skipped(
    qapp, qtbot, tmp_path: Path
) -> None:
    rows = [_row(0, status="unreadable"), _row(1)]
    opener = _Opener({"key-0": PlayableSource(url=URL), "key-1": PlayableSource(url=URL)})
    service, _backend, _access, database, ids, notices, _clock = _setup(
        qapp, tmp_path, rows, opener
    )

    service.play_queue(ids)
    qtbot.waitUntil(lambda: service.state.current_id == ids[1], timeout=5000)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING, timeout=5000)

    assert notices == ["Remote no longer provides this track."]
    assert [call[1] for call in opener.calls] == ["key-1"]
    service.close()
    database.close()


def test_an_error_of_the_player_on_a_plugin_track_names_the_plugin_and_skips(
    qapp, qtbot, tmp_path: Path
) -> None:
    rows = [_row(0), _row(1)]
    opener = _Opener({"key-0": PlayableSource(url=URL), "key-1": PlayableSource(url=URL)})
    service, backend, _access, database, ids, notices, _clock = _setup(qapp, tmp_path, rows, opener)
    backend.fail_with = "HTTP error 401 Unauthorized"

    service.play_queue(ids)
    qtbot.waitUntil(lambda: len(notices) >= 1, timeout=5000)
    backend.fail_with = None
    qtbot.waitUntil(lambda: service.state.current_id == ids[1], timeout=5000)

    assert notices[0] == "Remote could not play this track: HTTP error 401 Unauthorized"
    service.close()
    database.close()


def test_a_choice_of_another_track_drops_a_source_still_being_resolved(
    qapp, qtbot, tmp_path: Path
) -> None:
    rows = [_row(0), _row(1)]
    opener = _Opener({"key-0": PlayableSource(url=URL), "key-1": PlayableSource(url=URL + "?b")})
    opener.gate = threading.Event()
    service, backend, _access, database, ids, _notices, _clock = _setup(
        qapp, tmp_path, rows, opener
    )

    service.play_queue(ids, 0)  # key-0 blocks in the plugin
    qtbot.waitUntil(lambda: len(opener.calls) == 1, timeout=5000)
    service.play_queue(ids, 1)  # the user chooses the second track meanwhile
    qtbot.waitUntil(lambda: len(opener.calls) == 2, timeout=5000)
    opener.gate.set()
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING, timeout=5000)
    qtbot.wait(200)

    assert service.state.current_id == ids[1]
    assert [load[0] for load in backend.loads] == [PlayableSource(url=URL + "?b")]
    service.close()
    database.close()


def test_the_next_plugin_track_is_prepared_early_and_switched_to_without_loading(
    qapp, qtbot, tmp_path: Path
) -> None:
    local = tmp_path / "local.wav"
    local.write_bytes(b"audio")
    rows = [_row(0, path=str(local), sourcePluginId="", sourceKey=""), _row(1)]
    rows[0].pop("sourcePluginId")
    rows[0].pop("sourceKey")
    source = PlayableSource(url=URL, headers={"Authorization": "Bearer t"})
    opener = _Opener({"key-1": source})
    service, backend, access, database, ids, _notices, _clock = _setup(qapp, tmp_path, rows, opener)

    service.play_queue(ids)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING, timeout=5000)
    qtbot.wait(300)
    assert backend.queued is None  # 40 s left: too early
    backend.position = NEAR_END_US
    qtbot.waitUntil(lambda: backend.queued is not None, timeout=5000)

    queued_source, session_id, _gain = backend.queued or (None, 0, 0.0)
    assert queued_source == source  # the URL and the header go to the queued entry
    assert opener.calls[0][2] != threading.get_ident()
    assert not access.is_busy(TrackId.parse(ids[1]))  # a URL entry is never locked

    loads = len(backend.loads)
    backend.finish_current()
    qtbot.waitUntil(lambda: service.state.current_id == ids[1], timeout=5000)
    assert service.state.session_id == session_id
    assert len(backend.loads) == loads  # switched to, not loaded
    service.close()
    database.close()


def test_a_queue_change_while_the_next_source_resolves_queues_nothing_stale(
    qapp, qtbot, tmp_path: Path
) -> None:
    rows = [_row(0), _row(1), _row(2)]
    opener = _Opener(
        {
            "key-0": PlayableSource(url=URL),
            "key-1": PlayableSource(url=URL + "?1"),
            "key-2": PlayableSource(url=URL + "?2"),
        }
    )
    service, backend, _access, database, ids, _notices, _clock = _setup(
        qapp, tmp_path, rows, opener
    )
    service.play_queue(ids)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING, timeout=5000)
    opener.calls.clear()
    opener.gate = threading.Event()
    backend.position = NEAR_END_US
    qtbot.waitUntil(lambda: len(opener.calls) == 1, timeout=5000)  # key-1 is being resolved

    service.enqueue_tracks([ids[2]])  # "play next": the following track is now another one
    opener.gate.set()
    qtbot.waitUntil(lambda: backend.queued is not None, timeout=5000)
    qtbot.wait(200)

    assert backend.queued is not None
    assert backend.queued[0] == PlayableSource(url=URL + "?2")  # never the stale key-1
    service.close()
    database.close()


def test_a_restored_plugin_track_waits_in_pause_until_the_plugins_are_loaded(
    qapp, qtbot, tmp_path: Path
) -> None:
    rows = [_row(0)]
    opener = _Opener({"key-0": PlayableSource(url=URL)})
    service, backend, _access, database, ids, notices, _clock = _setup(qapp, tmp_path, rows, None)
    queue = QueueState().start_context([QueueEntry.create(ids[0], "context", snapshot=rows[0])], 0)

    service.attach_session(PlaybackRepository(database), PlaybackSession(queue, 5_000_000, 1))
    qtbot.wait(200)
    assert backend.loads == []  # no plugin yet: nothing is opened, nothing fails
    assert service.state.status is PlaybackStatus.LOADING
    assert notices == []

    service.attach_track_sources(opener)
    qtbot.waitUntil(lambda: bool(backend.loads), timeout=5000)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PAUSED, timeout=5000)
    assert service.state.current_id == ids[0]
    service.close()
    database.close()


def test_a_plugin_track_without_any_plugin_fails_with_a_sentence(
    qapp, qtbot, tmp_path: Path
) -> None:
    rows = [_row(0)]
    service, backend, _access, database, ids, _notices, _clock = _setup(qapp, tmp_path, rows, None)
    service.play_queue(ids)
    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.ERROR, timeout=5000)
    assert service.state.error_message == "No plugin provides the audio of this track."
    assert backend.loads == []
    service.close()
    database.close()
