"""PluginContext: only the listed core services, built over a temporary library."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from mtee.domain.jobs import JobState
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import PluginContext, PluginManifest
from mtee.plugins.context import PluginHost
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_move_service import FileMoveService
from mtee.services.jobs import JobContext, JobService
from mtee.services.playlist_service import PlaylistService

_MANIFEST = PluginManifest("sample", "Sample", "", "1.0.0", 1, "mtee.plugins.sample:create")
_OTHER = PluginManifest("other", "Other", "", "1.0.0", 1, "mtee.plugins.other:create")


@dataclass
class _Roots:
    """Stands for the workspace actions: records what a plugin asked."""

    added: list[str] = field(default_factory=list)
    rescanned: list[str] = field(default_factory=list)

    def addRoot(self, selected: str) -> str:  # noqa: N802
        self.added.append(selected)
        return "root-new"

    def rescanRoot(self, root_id: str) -> str:  # noqa: N802
        self.rescanned.append(root_id)
        return root_id


@dataclass
class _Trash:
    requested: list[list[str]] = field(default_factory=list)

    def request_recycle(self, raw_track_ids: list) -> None:
        self.requested.append(list(raw_track_ids))


class _Setup:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.settings = SettingsRepository(self.database)
        self.library = LibraryRepository(self.database)
        self.music = base / "music"
        self.music.mkdir()
        root = self.library.add_root(self.music)
        self.root_id = str(root["id"])
        generation = self.library.begin_scan(self.root_id)
        self.ids: list[str] = []
        for index, (title, artists) in enumerate(
            [("First", ("Ann", "Bob")), ("Second", ("Ann",)), ("", ())]
        ):
            path = self.music / f"track{index}.wav"
            path.write_bytes(b"audio" + bytes([index]))
            self.ids.append(
                self.library.upsert_location(
                    self.root_id,
                    path.name,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(
                        title=(title,) if title else (),
                        artist=artists,
                        album=("Album",) if index == 0 else (),
                        technical=TechnicalInfo(duration_us=3_000_000 + index),
                    ),
                    generation,
                )
            )
        self.library.finish_scan(self.root_id, generation, complete=True)
        self.playlists = PlaylistService(PlaylistsRepository(self.database), self.library)
        self.jobs = JobService(max_thread_count=2)
        self.roots = _Roots()
        self.trash = _Trash()
        self.refreshes = 0
        self.host = PluginHost(
            data_dir=base / "data",
            database=self.database,
            settings=self.settings,
            library=self.library,
            playlists=self.playlists,
            jobs=self.jobs,
            file_moves=FileMoveService(self.database, self.library, FileAccessCoordinator()),
            recycle=self.trash,
            roots=self.roots,
            refresh_playlists=self._refresh,
        )

    def _refresh(self) -> None:
        self.refreshes += 1

    def context(self, manifest: PluginManifest = _MANIFEST) -> PluginContext:
        return self.host.context_for(manifest)

    def close(self) -> None:
        self.jobs.shutdown(2_000)
        self.database.close()


@pytest.fixture
def setup(qapp, tmp_path: Path) -> Iterator[_Setup]:
    created = _Setup(tmp_path)
    yield created
    created.close()


def _wait_until(condition, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_the_context_names_the_plugin_and_its_folders(setup: _Setup) -> None:
    context = setup.context()

    assert context.plugin_id == "sample"
    assert context.log.name == "mtee.plugins.sample"
    assert context.database is setup.database
    assert context.base_dir == setup.base / "data" / "plugins" / "sample"
    assert not context.base_dir.exists()
    assert context.data_dir.is_dir()


def test_settings_are_scoped_to_the_plugin(setup: _Setup) -> None:
    mine = setup.context().settings
    theirs = setup.context(_OTHER).settings

    mine.set("token", "abc")
    mine.set_json("ids", ["a", "b"])
    theirs.set("token", "xyz")

    assert mine.get("token") == "abc"
    assert theirs.get("token") == "xyz"
    assert mine.get_json("ids") == ["a", "b"]
    assert setup.settings.get("plugins.sample.token") == "abc"
    assert setup.settings.get("token") is None
    mine.delete("token")
    assert mine.get("token", "gone") == "gone"
    assert theirs.get("token") == "xyz"
    with pytest.raises(ValueError, match="key is required"):
        mine.set("", "x")


def test_the_library_is_readable_as_tracks(setup: _Setup) -> None:
    library = setup.context().library

    assert library.track_ids() == setup.ids
    first, third = library.tracks([setup.ids[0], "missing", setup.ids[2]])
    assert first.track_id == setup.ids[0]
    assert first.title == "First"
    assert first.artists == ("Ann", "Bob")
    assert first.album == "Album"
    assert first.duration_us == 3_000_000
    assert first.path == setup.music / "track0.wav"
    assert first.readable
    assert third.title == "track2"
    assert third.artists == ()


def test_a_folder_is_added_and_rescanned_through_the_workspace(setup: _Setup) -> None:
    library = setup.context().library

    assert library.add_watched_folder(setup.base / "more") == "root-new"
    assert setup.roots.added == [str(setup.base / "more")]
    assert library.rescan(setup.music / "deeper" / "folder") is True
    assert library.rescan(setup.music) is True
    assert setup.roots.rescanned == [setup.root_id, setup.root_id]
    assert library.rescan(setup.base / "elsewhere") is False
    assert library.rescan(Path(str(setup.music) + "_other")) is False


def test_adding_a_folder_from_a_worker_thread_is_refused(setup: _Setup) -> None:
    library = setup.context().library
    errors: list[Exception] = []

    def work() -> None:
        try:
            library.add_watched_folder(setup.base)
        except RuntimeError as error:
            errors.append(error)

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()

    assert [str(error) for error in errors] == [
        "add_watched_folder must be called from the graphical thread."
    ]
    assert setup.roots.added == []


def test_playlists_are_created_replaced_and_read(setup: _Setup, qapp) -> None:
    playlists = setup.context().playlists
    first, second, third = setup.ids

    identity = playlists.create("Synced", [second, first, second])
    assert [entry.track_id for entry in playlists.entries(identity)] == [second, first]
    playlists.replace_entries(identity, [third, first])

    entries = playlists.entries(identity)
    assert [entry.track_id for entry in entries] == [third, first]
    assert [entry.title for entry in entries] == ["track2", "First"]
    assert entries[1].artist == "Ann, Bob"
    assert all(entry.available for entry in entries)
    qapp.processEvents()
    assert setup.refreshes == 2
    with pytest.raises(LookupError):
        playlists.replace_entries(identity, ["missing"])
    assert [entry.track_id for entry in playlists.entries(identity)] == [third, first]
    playlists.replace_entries(identity, [])
    assert playlists.entries(identity) == []


def test_jobs_are_submitted_and_cancelled_on_the_core_service(setup: _Setup) -> None:
    jobs = setup.context().jobs
    done = threading.Event()

    def quick(_context: JobContext) -> None:
        done.set()

    quick_id = jobs.submit(quick, label="Sync plugin")
    started = threading.Event()

    def waiting(context: JobContext) -> None:
        started.set()
        context.sleep(30)

    waiting_id = jobs.submit(waiting, label="Wait", visible=False)

    assert done.wait(10)
    assert started.wait(10)
    jobs.cancel(waiting_id)
    assert _wait_until(lambda: setup.jobs.status(waiting_id).state is JobState.CANCELLED)
    assert _wait_until(lambda: setup.jobs.status(quick_id).state is JobState.SUCCEEDED)
    assert setup.jobs.status(quick_id).label == "Sync plugin"
    assert not setup.jobs.is_visible(waiting_id)


def test_a_track_is_moved_through_the_core_move_service(setup: _Setup) -> None:
    (setup.music / "target").mkdir()
    files = setup.context().files

    result = files.move_track(setup.ids[0], setup.root_id, "target")

    assert result.status == "moved"
    assert (setup.music / "target" / "track0.wav").is_file()
    assert not (setup.music / "track0.wav").exists()
    again = files.move_track(setup.ids[0], setup.root_id, "target")
    assert again.status == "unchanged"


def test_recycling_goes_through_the_usual_confirmation(setup: _Setup, qapp) -> None:
    files = setup.context().files

    files.recycle([setup.ids[1], setup.ids[2]])

    assert setup.trash.requested == []  # asked for the graphical thread, not run in place
    qapp.processEvents()
    assert setup.trash.requested == [[setup.ids[1], setup.ids[2]]]


def test_a_notice_from_a_job_thread_reaches_the_graphical_thread(setup: _Setup, qapp) -> None:
    received: list[tuple[str, bool]] = []
    main = threading.current_thread()
    setup.host.noticeRaised.connect(
        lambda text: received.append((text, threading.current_thread() is main))
    )
    notify = setup.context().notify

    thread = threading.Thread(target=lambda: notify("Sync finished"))
    thread.start()
    thread.join()
    assert received == []
    for _ in range(50):
        qapp.processEvents()
        if received:
            break
        time.sleep(0.01)

    assert received == [("Sync finished", True)]
