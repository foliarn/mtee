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
from mtee.services.file_move_service import FileMoveError, FileMoveService
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
                        isrc="USRC17607839" if index == 0 else None,
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
    assert first.isrc == "USRC17607839"
    assert third.isrc is None
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


def test_a_function_queued_with_run_on_gui_runs_on_the_graphical_thread(
    setup: _Setup, qapp, caplog: pytest.LogCaptureFixture
) -> None:
    ran: list[tuple[str, bool]] = []
    main = threading.current_thread()
    run_on_gui = setup.context().run_on_gui

    thread = threading.Thread(
        target=lambda: run_on_gui(
            lambda: ran.append(("from a worker", threading.current_thread() is main))
        )
    )
    thread.start()
    thread.join()
    run_on_gui(lambda: ran.append(("from the gui", threading.current_thread() is main)))
    assert ran == []  # queued also from the graphical thread: nothing runs in place
    for _ in range(50):
        qapp.processEvents()
        if len(ran) == 2:
            break
        time.sleep(0.01)

    assert sorted(ran) == [("from a worker", True), ("from the gui", True)]

    def explodes() -> None:
        raise RuntimeError("plugin bug")

    with caplog.at_level("ERROR", logger="mtee.plugins.sample"):
        run_on_gui(explodes)
        run_on_gui(lambda: ran.append(("after", True)))
        for _ in range(50):
            qapp.processEvents()
            if ("after", True) in ran:
                break
            time.sleep(0.01)

    assert ("after", True) in ran  # a failing function does not stop the next ones
    assert "plugin bug" in caplog.text


def test_a_plugin_opens_its_own_tab_from_any_thread_on_the_graphical_thread(
    setup: _Setup, qapp, caplog: pytest.LogCaptureFixture
) -> None:
    asked: list[tuple[str, str, bool]] = []
    main = threading.current_thread()
    setup.host.tabRequested.connect(
        lambda kind, ref: asked.append((kind, ref, threading.current_thread() is main))
    )
    open_tab = setup.context().open_tab

    thread = threading.Thread(target=lambda: open_tab("sample.review", "pair-7"))
    thread.start()
    thread.join()
    assert asked == []  # queued: nothing happens in the calling thread
    with caplog.at_level("ERROR", logger="mtee.plugins.sample"):
        open_tab("other.review", "x")  # the kind of another plugin
        open_tab("review", "x")
    for _ in range(50):
        qapp.processEvents()
        if asked:
            break
        time.sleep(0.01)
    qapp.processEvents()

    assert asked == [("sample.review", "pair-7", True)]
    assert "only its own tab kinds" in caplog.text


def test_playlists_report_their_name_and_existence(setup: _Setup) -> None:
    playlists = setup.context().playlists
    identity = playlists.create("Synced", [setup.ids[0]])

    assert playlists.name(identity) == "Synced"
    assert playlists.exists(identity) is True
    assert playlists.name("missing") is None
    assert playlists.exists("missing") is False
    setup.playlists.repository.delete(identity)
    assert playlists.name(identity) is None
    assert playlists.exists(identity) is False


def _staged(setup: _Setup, name: str, content: bytes) -> Path:
    staging = setup.base / "staging"
    staging.mkdir(exist_ok=True)
    path = staging / name
    path.write_bytes(content)
    return path


def test_a_file_is_imported_into_a_library_folder_and_never_replaces_one(setup: _Setup) -> None:
    files = setup.context().files
    folder = setup.music / "Downloads"

    first = files.import_file(_staged(setup, "new.wav", b"first"), folder)
    second = files.import_file(_staged(setup, "new.wav", b"second"), folder)
    third = files.import_file(_staged(setup, "new.wav", b"third"), folder)
    taken = (setup.music / "track0.wav").read_bytes()
    clash = files.import_file(_staged(setup, "track0.wav", b"other"), setup.music)

    assert [path.name for path in (first, second, third)] == [
        "new.wav",
        "new (2).wav",
        "new (3).wav",
    ]
    assert [path.read_bytes() for path in (first, second, third)] == [b"first", b"second", b"third"]
    assert clash == setup.music / "track0 (2).wav"
    assert (setup.music / "track0.wav").read_bytes() == taken  # byte-identical after a collision
    assert not (setup.base / "staging" / "new.wav").exists()
    assert setup.library.path_owner(first) is None  # the scanner records it, not the import


def test_an_import_skips_a_name_the_library_still_owns(setup: _Setup) -> None:
    files = setup.context().files
    (setup.music / "track1.wav").unlink()  # gone from disk, still owned until the next scan

    placed = files.import_file(_staged(setup, "track1.wav", b"again"), setup.music)

    assert placed == setup.music / "track1 (2).wav"
    assert not (setup.music / "track1.wav").exists()


def test_an_import_refuses_what_is_not_a_new_file_for_a_library_folder(setup: _Setup) -> None:
    files = setup.context().files
    staged = _staged(setup, "new.wav", b"first")

    with pytest.raises(FileMoveError, match="not in the library"):
        files.import_file(staged, setup.base / "elsewhere")
    with pytest.raises(FileMoveError, match="not in the library"):
        files.import_file(staged, Path(str(setup.music) + "_other"))
    with pytest.raises(FileMoveError, match="already in the library"):
        files.import_file(setup.music / "track0.wav", setup.music / "Downloads")
    with pytest.raises(FileNotFoundError):
        files.import_file(setup.base / "staging" / "none.wav", setup.music)

    assert staged.read_bytes() == b"first"
    assert not (setup.base / "elsewhere").exists()
    assert not (setup.music / "Downloads").exists()
    assert (setup.music / "track0.wav").is_file()


def test_a_file_already_in_the_destination_folder_is_left_where_it_is(setup: _Setup) -> None:
    files = setup.context().files
    loose = setup.music / "loose.wav"
    loose.write_bytes(b"loose")

    assert files.import_file(loose, setup.music) == loose
    assert loose.read_bytes() == b"loose"
    assert sorted(path.name for path in setup.music.iterdir()).count("loose (2).wav") == 0


def test_an_import_can_run_on_a_job_thread(setup: _Setup) -> None:
    files = setup.context().files
    staged = _staged(setup, "worker.wav", b"from a worker")
    done = threading.Event()
    placed: list[Path] = []

    def work(_context: JobContext) -> None:
        placed.append(files.import_file(staged, setup.music))
        done.set()

    setup.context().jobs.submit(work, label="Import", visible=False)

    assert done.wait(10)
    assert placed == [setup.music / "worker.wav"]
    assert placed[0].read_bytes() == b"from a worker"
