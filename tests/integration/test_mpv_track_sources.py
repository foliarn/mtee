"""A plugin track plays through the real libmpv from an HTTP URL that requires a header.

The sample plugin serves a short FLAC on 127.0.0.1 and answers 401 to any request without
``Authorization``, so a track that plays has proved that the player sent the header. The PCM
audio output (``ao=pcm``) captures the exact stream for the gapless check (plan 125.2). Only
temporary files are used.
"""

from __future__ import annotations

import array
import importlib.util
import math
import os
import queue
import shutil
import struct
import sys
import time
import wave
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

from mtee.domain.playback import PlaybackStatus
from mtee.domain.source_tracks import PlayableSource
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.play_log_repository import PlayLogRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.plugins.context import PluginHost
from mtee.plugins.loader import PluginManager, PluginPreferences
from mtee.plugins.source_registry import TrackSourceRegistry
from mtee.services.ffmpeg_runtime import FfmpegRuntime, FfmpegRuntimeError
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_move_service import FileMoveService
from mtee.services.jobs import JobService
from mtee.services.mpv_backend import MpvBackend
from mtee.services.player_backend import BackendEvent
from mtee.services.player_service import PlayerService
from mtee.services.playlist_service import PlaylistService

RATE = 44_100
HALF = RATE * 3 // 2
AMPLITUDE = 12_000
_SAMPLE = Path(__file__).resolve().parents[1] / "plugins" / "sample"
DEVICE = "22222222-2222-2222-2222-222222222222"


class _NoTrash:
    def request_recycle(self, raw_track_ids: list) -> None:
        del raw_track_ids


class _NoRoots:
    def addRoot(self, selected: str) -> str:  # noqa: N802
        return ""

    def rescanRoot(self, root_id: str) -> str:  # noqa: N802
        return root_id


def _sine(count: int, start: int) -> list[int]:
    return [
        round(AMPLITUDE * math.sin(2 * math.pi * 1000 * (start + n) / RATE)) for n in range(count)
    ]


def _write_stereo(path: Path, samples: list[int]) -> None:
    frames = b"".join(struct.pack("<hh", value, value) for value in samples)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(frames)


def _flac_of(samples: list[int], directory: Path) -> bytes:
    """Encode ``samples`` (lossless) with the bundled FFmpeg and return the FLAC bytes."""
    try:
        runtime = FfmpegRuntime()
        runtime.executable("ffmpeg")
    except FfmpegRuntimeError:
        pytest.skip("The bundled FFmpeg runtime is unavailable.")
    source, target = directory / "source.wav", directory / "served.flac"
    _write_stereo(source, samples)
    done = runtime.run("ffmpeg", ["-y", "-loglevel", "error", "-i", str(source), str(target)])
    assert done.returncode == 0, done.stderr
    return target.read_bytes()


def _server_module() -> ModuleType:
    """Load the sample plugin's server module by path (the sample is not an importable package)."""
    spec = importlib.util.spec_from_file_location(
        "sample_track_source", _SAMPLE / "track_source.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass looks its module up by name
    spec.loader.exec_module(module)
    return module


def _runtime_path() -> Path | None:
    packaged = os.environ.get("MTEE_TEST_MPV_LIBRARY")
    return Path(packaged) if packaged else None


def _zero_runs(samples: array.array) -> list[int]:
    runs: list[int] = []
    length = 0
    for value in samples:
        if value == 0:
            length += 1
        else:
            if length:
                runs.append(length)
            length = 0
    if length:
        runs.append(length)
    return runs


def _until_loaded(events: queue.Queue[BackendEvent], seen: list[BackendEvent]) -> None:
    """Wait until the entry that was loaded is open, as the player does before queueing the next."""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            event = events.get(timeout=0.1)
        except queue.Empty:
            continue
        seen.append(event)
        if event.name in {"loaded", "error"}:
            return


def _wait_for(
    events: queue.Queue[BackendEvent],
    names: set[str],
    seen: list[BackendEvent],
    needed: int = 1,
) -> int:
    """Read events until ``needed`` of the kinds in ``names`` came, or 20 s passed."""
    ended = 0
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and ended < needed:
        try:
            event = events.get(timeout=0.1)
        except queue.Empty:
            continue
        seen.append(event)
        ended += event.name in names
    return ended


@pytest.mark.native_audio
def test_a_header_less_request_is_refused_by_the_server_and_reported_by_the_player(
    tmp_path: Path,
) -> None:
    module = _server_module()
    flac = _flac_of(_sine(HALF, 0), tmp_path)
    server = module.AudioServer(flac)
    server.start()
    backend = MpvBackend(_runtime_path(), audio_output="null")
    events: queue.Queue[BackendEvent] = queue.Queue()
    backend.set_event_handler(events.put)
    seen: list[BackendEvent] = []
    try:
        backend.load(PlayableSource(url=server.url), 1)  # no Authorization header
        _wait_for(events, {"error", "eof"}, seen)
    finally:
        backend.close()
        server.stop()
    assert any(e.name == "error" for e in seen), [e.name for e in seen]
    assert server.requests and all(request.authorization is None for request in server.requests)


@pytest.mark.native_audio
def test_the_sample_url_track_plays_logs_a_listening_and_skips_a_broken_neighbour(
    qapp, qtbot, tmp_path: Path
) -> None:
    flac = _flac_of(_sine(RATE * 2, 0), tmp_path)
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    settings = SettingsRepository(database)
    library = LibraryRepository(database)
    jobs = JobService(max_thread_count=2)
    host = PluginHost(
        data_dir=tmp_path / "data",
        database=database,
        settings=settings,
        library=library,
        playlists=PlaylistService(PlaylistsRepository(database), library),
        jobs=jobs,
        file_moves=FileMoveService(database, library, FileAccessCoordinator()),
        recycle=cast(Any, _NoTrash()),
        roots=cast(Any, _NoRoots()),
        refresh_playlists=lambda: None,
        source_tracks=SourceTrackRepository(database),
    )
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    shutil.copytree(_SAMPLE, plugins / "sample", ignore=shutil.ignore_patterns("__pycache__"))
    preferences = PluginPreferences(settings)
    preferences.set_enabled("sample", True)
    manager = PluginManager(preferences, notify=lambda text: None)
    service: PlayerService | None = None
    try:
        record = manager.load_enabled(host.context_for, [plugins])[0]
        assert record.error == "", record.error
        assert record.service is not None
        identities = record.service.provide_tracks(flac, 2_000_000)  # type: ignore[attr-defined]
        server = record.service.audio_server  # type: ignore[attr-defined]
        playable, broken = identities["sample-url-track"], identities["sample-broken-track"]

        registry = TrackSourceRegistry()
        registry.register(manager.plugins)
        library.set_running_source_plugins(registry.running_plugin_ids, {"sample": "Sample plugin"})
        service = PlayerService(
            library.track,
            FileAccessCoordinator(),
            MpvBackend(_runtime_path(), audio_output="null"),
            parent=qapp,
        )
        service.attach_play_log(PlayLogRepository(database), DEVICE)
        service.attach_track_sources(registry)
        notices: list[str] = []
        service.sourceFailed.connect(notices.append)

        # The broken track comes first: it fails with the plugin's name, then the next one plays.
        service.play_queue([broken, playable])
        qtbot.waitUntil(lambda: service.state.current_id == playable, timeout=15_000)
        qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING, timeout=15_000)
        assert service.state.duration_us is not None and service.state.duration_us > 1_900_000
        qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.ENDED, timeout=15_000)

        assert notices == [
            "Sample plugin could not open this track: the sample server cannot be reached"
        ]
        assert server.requests, "the server saw no request"
        assert all(request.authorization == "Bearer sample-token" for request in server.requests)

        service.flush_session()
        rows = database.connection().execute("SELECT * FROM play_events").fetchall()
        assert [(r["track_id"], r["title"], r["path_at_play"]) for r in rows] == [
            (playable, "Served over HTTP", "")
        ]
        assert rows[0]["heard_ms"] > 1_000
    finally:
        if service is not None:
            service.close()
        manager.unload_all()
        jobs.shutdown(2_000)
        database.close()


@pytest.mark.native_audio
def test_a_local_file_joins_a_url_track_with_no_gap(tmp_path: Path) -> None:
    module = _server_module()
    flac = _flac_of(_sine(HALF, HALF), tmp_path)
    first = tmp_path / "a.wav"
    _write_stereo(first, _sine(HALF, 0))
    server = module.AudioServer(flac)
    server.start()
    output = tmp_path / "out.pcm"
    backend = MpvBackend(
        _runtime_path(),
        audio_output="pcm",
        extra_options={"ao-pcm-file": str(output), "ao-pcm-waveheader": "no"},
    )
    events: queue.Queue[BackendEvent] = queue.Queue()
    backend.set_event_handler(events.put)
    seen: list[BackendEvent] = []
    try:
        backend.set_paused(True)
        backend.load(first, 1)
        _until_loaded(events, seen)
        backend.queue_next(
            PlayableSource(url=server.url, headers={"Authorization": f"Bearer {module.TOKEN}"}),
            2,
            0.0,
        )
        backend.set_paused(False)
        _wait_for(events, {"eof", "error"}, seen, 2)
        time.sleep(0.3)
    finally:
        backend.close()
        server.stop()

    names = [(event.name, event.session_id) for event in seen]
    assert ("eof", 1) in names and ("eof", 2) in names, names
    assert names.index(("eof", 1)) < names.index(("start-file", 2)) < names.index(("loaded", 2))
    assert not any(e.name == "error" for e in seen)
    assert server.requests
    assert all(request.authorization == f"Bearer {module.TOKEN}" for request in server.requests)

    raw = array.array("h")
    raw.frombytes(output.read_bytes())
    left = array.array("h", raw[0::2])
    assert len(left) == 2 * HALF
    # A sine sampled at 44.1 kHz has at most one exact zero in a row; a gap would have more.
    assert max(_zero_runs(left), default=0) <= 1
    expected = _sine(2 * HALF, 0)
    assert max(abs(left[n] - expected[n]) for n in range(2 * HALF)) <= 2  # the join is exact


@pytest.mark.native_audio
def test_each_entry_carries_only_its_own_headers(tmp_path: Path) -> None:
    """libmpv opens the queued entry ahead of time: it must get its headers, and only those."""
    module = _server_module()
    flac = _flac_of(_sine(RATE, 0), tmp_path)
    server = module.AudioServer(flac)
    server.start()
    token = f"Bearer {module.TOKEN}"
    backend = MpvBackend(_runtime_path(), audio_output="null")
    events: queue.Queue[BackendEvent] = queue.Queue()
    backend.set_event_handler(events.put)
    seen: list[BackendEvent] = []
    try:
        backend.set_paused(True)
        backend.load(
            PlayableSource(
                url=server.url + "?first",
                headers={"Authorization": token, "X-Odd": "a, b; c=d"},
            ),
            1,
        )
        _until_loaded(events, seen)
        backend.queue_next(
            PlayableSource(
                url=server.url + "?second", headers={"Authorization": token, "X-Second": "two"}
            ),
            2,
            0.0,
        )
        backend.set_paused(False)
        _wait_for(events, {"eof", "error"}, seen, 2)
    finally:
        backend.close()
        server.stop()

    assert [(e.name, e.session_id) for e in seen if e.name in {"eof", "error"}] == [
        ("eof", 1),
        ("eof", 2),
    ]
    first = [r for r in server.requests if r.path.endswith("?first")]
    second = [r for r in server.requests if r.path.endswith("?second")]
    assert first and second
    for request in first:
        assert request.authorization == token
        assert request.headers.get("X-Odd") == "a, b; c=d"  # the comma survived
        assert "X-Second" not in request.headers
    for request in second:
        assert request.authorization == token
        assert request.headers.get("X-Second") == "two"
        assert "X-Odd" not in request.headers  # nothing leaks from the playing entry


@pytest.mark.native_audio
def test_a_cancelled_entry_gives_the_playing_entry_its_headers_back(tmp_path: Path) -> None:
    module = _server_module()
    flac = _flac_of(_sine(RATE * 4, 0), tmp_path)
    server = module.AudioServer(flac)
    server.start()
    token = f"Bearer {module.TOKEN}"
    backend = MpvBackend(_runtime_path(), audio_output="null")
    events: queue.Queue[BackendEvent] = queue.Queue()
    backend.set_event_handler(events.put)
    try:
        backend.set_paused(True)
        backend.load(
            PlayableSource(url=server.url + "?one", headers={"Authorization": token, "X-One": "1"}),
            1,
        )
        _until_loaded(events, [])
        backend.queue_next(
            PlayableSource(url=server.url + "?two", headers={"Authorization": token, "X-Two": "2"}),
            2,
            0.0,
        )
        assert backend._live_headers.endswith("X-Two: 2")
        backend.clear_next()
        assert backend._live_headers.endswith("X-One: 1")  # the playing entry's again
        backend.set_paused(False)
        _wait_for(events, {"eof", "error"}, [])
    finally:
        backend.close()
        server.stop()
