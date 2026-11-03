"""Remote plan 126.1: the optional core capabilities a plugin asks for.

``library.roots()``, ``files.read_lease(track_id)`` and ``ffmpeg_path()`` run through ``PluginHost``
over a temporary library, as a plugin would use them. Only temporary folders and copies are used.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.plugins.api import (
    CapabilityUnavailableError,
    LibraryRoot,
    NonFileTrackError,
    PluginContext,
    PluginManifest,
    SourceTrack,
)
from mtee.plugins.context import PluginHost
from mtee.services.ffmpeg_runtime import FfmpegRuntime
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError
from mtee.services.file_move_service import FileMoveService
from mtee.services.jobs import JobService
from mtee.services.playlist_service import PlaylistService

_MANIFEST = PluginManifest("sample", "Sample", "", "1.0.0", 1, "mtee.plugins.sample:create")


class _Roots:
    def addRoot(self, selected: str) -> str:  # noqa: N802
        return "root-new"

    def rescanRoot(self, root_id: str) -> str:  # noqa: N802
        return root_id


class _Trash:
    def request_recycle(self, raw_track_ids: list) -> None:
        del raw_track_ids


class _Setup:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.settings = SettingsRepository(self.database)
        self.library = LibraryRepository(self.database)
        self.jobs = JobService(max_thread_count=2)
        self.coordinator = FileAccessCoordinator()
        self.music = base / "music"
        self.music.mkdir()
        self.second = base / "second"
        self.second.mkdir()
        self.root_id = str(self.library.add_root(self.music)["id"])
        self.second_root_id = str(self.library.add_root(self.second)["id"])
        generation = self.library.begin_scan(self.root_id)
        path = self.music / "track0.wav"
        path.write_bytes(b"audio")
        self.track_id = self.library.upsert_location(
            self.root_id,
            path.name,
            path,
            SourceRevision.observe(path),
            MetadataSnapshot(
                title=("First",),
                artist=("Ann",),
                technical=TechnicalInfo(duration_us=3_000_000),
            ),
            generation,
        )
        self.library.finish_scan(self.root_id, generation, complete=True)
        self.host = self.build_host()

    def build_host(
        self, *, with_access: bool = True, ffmpeg: FfmpegRuntime | None = None
    ) -> PluginHost:
        return PluginHost(
            data_dir=self.base / "data",
            database=self.database,
            settings=self.settings,
            library=self.library,
            playlists=PlaylistService(PlaylistsRepository(self.database), self.library),
            jobs=self.jobs,
            file_moves=FileMoveService(self.database, self.library, self.coordinator),
            recycle=_Trash(),
            roots=_Roots(),
            refresh_playlists=lambda: None,
            source_tracks=SourceTrackRepository(self.database),
            file_access=self.coordinator if with_access else None,
            ffmpeg=ffmpeg,
        )

    def context(self) -> PluginContext:
        return self.host.context_for(_MANIFEST)

    def close(self) -> None:
        self.jobs.shutdown(2_000)
        self.database.close()


@pytest.fixture
def setup(qapp, tmp_path: Path) -> Iterator[_Setup]:
    created = _Setup(tmp_path)
    yield created
    created.close()


def _in_thread[T](call: Callable[[], T]) -> T:
    """Run ``call`` on a job-like thread (not the graphical one) and return its result."""
    outcome: list[tuple[bool, Any]] = []

    def work() -> None:
        try:
            outcome.append((True, call()))
        except BaseException as error:  # handed back to the test thread
            outcome.append((False, error))

    thread = threading.Thread(target=work)
    thread.start()
    thread.join(20)
    ok, value = outcome[0]
    if not ok:
        raise value
    return value


def _enter(context: PluginContext, track_id: str) -> str:
    with context.files.read_lease(track_id) as path:
        return str(path)


# ------------------------------------------------------------------------------ library.roots


def test_roots_lists_the_watched_folders(setup: _Setup) -> None:
    context = setup.context()

    roots = context.library.roots()
    listed = {(root.root_id, root.path.resolve()) for root in roots}

    assert all(isinstance(root, LibraryRoot) for root in roots)
    assert listed == {
        (setup.root_id, setup.music.resolve()),
        (setup.second_root_id, setup.second.resolve()),
    }


def test_roots_can_be_read_from_a_job_thread(setup: _Setup) -> None:
    context = setup.context()

    roots = _in_thread(context.library.roots)

    assert {root.root_id for root in roots} == {setup.root_id, setup.second_root_id}


# ---------------------------------------------------------------------------- files.read_lease


def test_read_lease_yields_the_file_and_holds_the_coordinator_read_lease(setup: _Setup) -> None:
    context = setup.context()
    track = TrackId.parse(setup.track_id)
    entered = threading.Event()
    release = threading.Event()
    yielded: list[Path] = []

    def hold() -> None:
        with context.files.read_lease(setup.track_id) as path:
            yielded.append(path)
            entered.set()
            release.wait(20)

    worker = threading.Thread(target=hold)
    worker.start()
    try:
        assert entered.wait(10)
        assert setup.coordinator.is_busy(track)
        assert setup.coordinator.holder_of(track) == "plugin sample"
        # A write on the same track is refused while the lease is held ...
        with (
            pytest.raises(FileAccessTimeoutError),
            setup.coordinator.acquire(track, "tag write", timeout_seconds=0),
        ):
            pass
        # ... and another reader still shares it, as with the player.
        with setup.coordinator.acquire_read(track, "other reader", timeout_seconds=0):
            pass
    finally:
        release.set()
        worker.join(10)

    assert [path.resolve() for path in yielded] == [(setup.music / "track0.wav").resolve()]
    assert not setup.coordinator.is_busy(track)
    with setup.coordinator.acquire(track, "tag write", timeout_seconds=0):
        pass


def test_a_write_waits_for_a_held_read_lease_to_end(setup: _Setup) -> None:
    context = setup.context()
    track = TrackId.parse(setup.track_id)
    entered = threading.Event()
    release = threading.Event()
    written = threading.Event()

    def hold() -> None:
        with context.files.read_lease(setup.track_id):
            entered.set()
            release.wait(20)

    def write() -> None:
        with setup.coordinator.acquire(track, "tag write", timeout_seconds=10):
            written.set()

    reader = threading.Thread(target=hold)
    reader.start()
    try:
        assert entered.wait(10)
        writer = threading.Thread(target=write)
        writer.start()
        assert not written.wait(0.3)
    finally:
        release.set()
        reader.join(10)
    assert written.wait(10)
    writer.join(10)


def test_read_lease_is_released_when_the_block_fails(setup: _Setup) -> None:
    context = setup.context()
    track = TrackId.parse(setup.track_id)

    def fail_inside() -> None:
        with context.files.read_lease(setup.track_id):
            raise ValueError("the hash failed")

    with pytest.raises(ValueError, match="the hash failed"):
        _in_thread(fail_inside)

    assert not setup.coordinator.is_busy(track)


def test_read_lease_refuses_the_graphical_thread(setup: _Setup) -> None:
    context = setup.context()

    with pytest.raises(RuntimeError, match="graphical thread"):
        context.files.read_lease(setup.track_id)


def test_read_lease_refuses_a_track_without_a_file(setup: _Setup) -> None:
    context = setup.context()
    stored = context.track_sources.upsert(
        [SourceTrack("remote-1", "Server song", artists=("Ann",), duration_us=2_000_000)]
    )

    with pytest.raises(NonFileTrackError, match="provided by sample"):
        _in_thread(lambda: _enter(context, stored["remote-1"]))


def test_read_lease_reports_a_missing_file(setup: _Setup) -> None:
    context = setup.context()
    (setup.music / "track0.wav").unlink()

    with pytest.raises(FileNotFoundError):
        _in_thread(lambda: _enter(context, setup.track_id))


def test_read_lease_reports_an_unknown_track(setup: _Setup) -> None:
    context = setup.context()

    with pytest.raises(LookupError):
        _in_thread(lambda: _enter(context, str(uuid4())))


def test_read_lease_needs_the_coordinator(setup: _Setup) -> None:
    host = setup.build_host(with_access=False)
    context = host.context_for(_MANIFEST)

    with pytest.raises(CapabilityUnavailableError):
        _in_thread(lambda: context.files.read_lease(setup.track_id))


# ---------------------------------------------------------------------------- ffmpeg_path()


def test_ffmpeg_path_is_the_vendored_runtime(setup: _Setup) -> None:
    context = setup.context()

    path = context.ffmpeg_path()

    assert path.is_file()
    assert path.stem == "ffmpeg"
    assert path == FfmpegRuntime().executable("ffmpeg")
    assert _in_thread(context.ffmpeg_path) == path


def test_ffmpeg_path_reports_a_missing_runtime(setup: _Setup, tmp_path: Path) -> None:
    host = setup.build_host(ffmpeg=FfmpegRuntime(tmp_path / "absent"))

    with pytest.raises(FileNotFoundError):
        host.context_for(_MANIFEST).ffmpeg_path()


def test_a_context_built_without_the_ffmpeg_runtime_raises(setup: _Setup, tmp_path: Path) -> None:
    bare = PluginContext(
        plugin_id="bare",
        database=setup.database,
        library=cast(Any, None),
        playlists=cast(Any, None),
        jobs=cast(Any, None),
        files=cast(Any, None),
        settings=cast(Any, None),
        base_dir=tmp_path,
        notify=lambda text: None,
        log=logging.getLogger("mtee.plugins.bare"),
    )

    with pytest.raises(CapabilityUnavailableError):
        bare.ffmpeg_path()
