"""Remote plan 126.4: replacing the file of a track (``files.replace_content``) on real copies.

The Windows Shell is never reached. The Recycle Bin is a fake that moves each file into a folder
of the test, and the source files are FLAC copies made by the pinned ffmpeg in a temporary folder
(the tests that need it are skipped without it). The library, the trash journal, the trash model
and the file access coordinator are the real ones, on a temporary database.
"""

from __future__ import annotations

import gc
import subprocess
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import shiboken6
from mutagen.flac import FLAC

from mtee.domain.tracks import SourceRevision, TrackId
from mtee.models.trash_model import TrashModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.persistence.trash_repository import TrashRepository
from mtee.plugins.api import (
    CapabilityUnavailableError,
    NonFileTrackError,
    PluginContext,
    PluginManifest,
    SourceTrack,
)
from mtee.plugins.context import PluginHost
from mtee.services import content_replacement
from mtee.services.content_replacement import ContentReplaceError, ContentReplacement
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_move_service import FileMoveService
from mtee.services.jobs import JobService
from mtee.services.metadata_reader import MetadataReader
from mtee.services.playlist_service import PlaylistService
from mtee.services.trash_service import TrashServiceError

_PINNED_FFMPEG = Path(__file__).resolve().parents[2] / "vendor" / "ffmpeg" / "bin" / "ffmpeg.exe"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_MANIFEST = PluginManifest("sample", "Sample", "", "1.0.0", 1, "mtee.plugins.sample:create")
_LEASE_PURPOSE = "replace audio file"


def _make_flac(path: Path, *, seconds: float, title: str, artist: str) -> Path:
    """Write a tagged FLAC sine wave at ``path`` (a new file) and return it."""
    if not _PINNED_FFMPEG.is_file():
        pytest.skip("The pinned ffmpeg is missing from vendor/ffmpeg.")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(_PINNED_FFMPEG),
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:a",
            "flac",
            "-f",
            "flac",
            str(path),
        ],
        check=True,
        capture_output=True,
        creationflags=_NO_WINDOW,
    )
    tags = FLAC(path)
    tags["title"] = [title]
    tags["artist"] = [artist]
    tags.save()
    return path


class _FakeRecycleBin:
    """Stands for the Shell: moves each file into ``folder`` and returns an identity for it."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.folder.mkdir(parents=True)
        self.calls: list[Path] = []
        self.errors: dict[str, Exception] = {}
        self.before_recycle: Callable[[Path], None] | None = None

    def recycle(self, path: Path | str) -> str:
        source = Path(path)
        self.calls.append(source)
        if self.before_recycle is not None:
            self.before_recycle(source)
        error = self.errors.get(source.name)
        if error is not None:
            raise error
        destination = self.folder / f"{len(self.calls):03d}-{source.name}"
        source.rename(destination)
        return f"C:\\$Recycle.Bin\\fake\\{destination.name}"

    def contents(self) -> list[bytes]:
        return [path.read_bytes() for path in sorted(self.folder.iterdir())]


class _Roots:
    def addRoot(self, selected: str) -> str:  # noqa: N802
        return "root-new"

    def rescanRoot(self, root_id: str) -> str:  # noqa: N802
        return root_id


class _Library:
    def __init__(self, qapp: Any, base: Path) -> None:
        self.qapp = qapp
        self.base = base
        self.music = base / "music"
        self.music.mkdir()
        self.incoming = base / "incoming"
        self.incoming.mkdir()
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.root_id = str(self.library.add_root(self.music)["id"])
        self.access = FileAccessCoordinator()
        self.jobs = JobService(max_thread_count=2)
        self.bin = _FakeRecycleBin(base / "recycle-bin")
        self.trash = TrashModel(
            self.library,
            self.jobs,
            cast(Any, self.bin),
            self.access,
            TrashRepository(self.database),
        )
        self.replacement = ContentReplacement(
            self.database,
            self.library,
            self.access,
            self.trash,
            trash=cast(Any, self.bin),
            reader=MetadataReader(),
        )

    def add_track(self, name: str, *, seconds: float, title: str, artist: str) -> str:
        path = _make_flac(self.music / name, seconds=seconds, title=title, artist=artist)
        generation = self.library.begin_scan(self.root_id)
        track_id = self.library.upsert_location(
            self.root_id,
            name,
            path,
            SourceRevision.observe(path),
            MetadataReader().read(path),
            generation,
        )
        self.library.finish_scan(self.root_id, generation, complete=True)
        return track_id

    def incoming_file(self, name: str, *, seconds: float, title: str, artist: str) -> Path:
        return _make_flac(self.incoming / name, seconds=seconds, title=title, artist=artist)

    def host(self, *, with_replacement: bool = True) -> PluginHost:
        return PluginHost(
            data_dir=self.base / "data",
            database=self.database,
            settings=SettingsRepository(self.database),
            library=self.library,
            playlists=PlaylistService(PlaylistsRepository(self.database), self.library),
            jobs=self.jobs,
            file_moves=FileMoveService(self.database, self.library, self.access),
            recycle=self.trash,
            roots=_Roots(),
            refresh_playlists=lambda: None,
            source_tracks=SourceTrackRepository(self.database),
            file_access=self.access,
            content_replacement=self.replacement if with_replacement else None,
        )

    def journal(self) -> list[tuple[str, str]]:
        rows = self.database.connection().execute(
            "SELECT track_id,status FROM trash_operations ORDER BY rowid"
        )
        return [(str(row[0]), str(row[1])) for row in rows]

    def close(self) -> None:
        self.jobs.shutdown(2_000)
        self.qapp.processEvents()
        self.database.close()
        shiboken6.delete(self.trash)
        gc.collect()


@pytest.fixture
def lib(qapp: Any, tmp_path: Path) -> Iterator[_Library]:
    created = _Library(qapp, tmp_path)
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
    thread.join(30)
    ok, value = outcome[0]
    if not ok:
        raise value
    return value


def _replace_through(context: PluginContext, track_id: str, source: Path) -> Path:
    return _in_thread(lambda: context.files.replace_content(track_id, source))


# ------------------------------------------------------------------ the replacement itself


def test_the_new_file_takes_the_path_and_the_track_identity(lib: _Library) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    old_bytes = path.read_bytes()
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    new_bytes = source.read_bytes()
    holders: list[str | None] = []
    track = TrackId.parse(track_id)
    lib.bin.before_recycle = lambda _path: holders.append(lib.access.holder_of(track))

    result = lib.replacement.replace(track_id, source)

    assert result.resolve() == path.resolve()
    assert path.read_bytes() == new_bytes
    assert not source.exists()
    # The old file went to the Recycle Bin while the write lease was held.
    assert holders[0] == _LEASE_PURPOSE
    assert lib.bin.contents()[0] == old_bytes
    assert lib.journal() == [(track_id, "recycled")]
    # The library describes the new file, under the same identifier and the same path.
    assert lib.library.path_owner(path) == track_id
    record = lib.library.source_record(track_id)
    assert record is not None
    assert record.revision.size_bytes == len(new_bytes)
    row = lib.library.track(track_id)
    assert row["title"] == "New"
    assert row["artist"] == "Bea"
    assert lib.library.track_folder(track_id) == (lib.root_id, "")


def test_the_old_file_is_recorded_in_the_trash_history(lib: _Library) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")

    lib.replacement.replace(track_id, source)

    rows = lib.database.connection().execute(
        "SELECT track_id,status,recycle_item_identity FROM trash_operations ORDER BY rowid"
    )
    recorded = [(str(r[0]), str(r[1]), str(r[2])) for r in rows]
    assert len(recorded) == 1
    assert recorded[0][:2] == (track_id, "recycled")
    assert recorded[0][2].startswith("C:\\$Recycle.Bin\\fake\\")


@pytest.mark.parametrize("other_volume", [False, True], ids=["same-volume", "other-volume"])
def test_another_volume_copies_to_a_part_file_first(
    lib: _Library, monkeypatch: pytest.MonkeyPatch, other_volume: bool
) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    new_bytes = source.read_bytes()
    monkeypatch.setattr(content_replacement, "_same_volume", lambda _src, _dst: not other_volume)
    part_seen: list[bytes | None] = []

    def observe(_path: Path) -> None:
        part = lib.music / ".song.flac.part"
        if not part_seen:  # the first recycle is the old file
            part_seen.append(part.read_bytes() if part.is_file() else None)

    lib.bin.before_recycle = observe

    lib.replacement.replace(track_id, source)

    if other_volume:
        assert part_seen == [new_bytes]
    else:
        assert part_seen == [None]
    assert not (lib.music / ".song.flac.part").exists()
    assert path.read_bytes() == new_bytes
    assert not source.exists()


def test_a_failed_copy_to_another_volume_changes_nothing(
    lib: _Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    old_bytes = path.read_bytes()
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    monkeypatch.setattr(content_replacement, "_same_volume", lambda _src, _dst: False)

    def disk_full(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("No space left on device")

    monkeypatch.setattr(content_replacement.shutil, "copyfileobj", disk_full)

    with pytest.raises(OSError, match="No space left"):
        lib.replacement.replace(track_id, source)

    assert path.read_bytes() == old_bytes
    assert source.is_file()
    assert not (lib.music / ".song.flac.part").exists()
    assert lib.bin.calls == []
    assert lib.journal() == []
    assert lib.library.source_record(track_id) is not None
    assert lib.library.track(track_id)["title"] == "Old"


@pytest.mark.parametrize("other_volume", [False, True], ids=["same-volume", "other-volume"])
def test_recycle_bin_unavailable_stops_before_anything_changes(
    lib: _Library, monkeypatch: pytest.MonkeyPatch, other_volume: bool
) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    old_bytes = path.read_bytes()
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    new_bytes = source.read_bytes()
    monkeypatch.setattr(content_replacement, "_same_volume", lambda _src, _dst: not other_volume)
    lib.bin.errors["song.flac"] = TrashServiceError("The Recycle Bin did not confirm the file.")

    with pytest.raises(ContentReplaceError, match="was not replaced") as info:
        lib.replacement.replace(track_id, source)

    assert info.value.readable is True
    assert path.read_bytes() == old_bytes
    assert source.read_bytes() == new_bytes
    assert lib.bin.contents() == []
    assert [status for _track, status in lib.journal()] == ["failed"]
    assert not (lib.music / ".song.flac.part").exists()
    assert lib.library.track(track_id)["title"] == "Old"
    assert not lib.access.is_busy(TrackId.parse(track_id))


@pytest.mark.parametrize("other_volume", [False, True], ids=["same-volume", "other-volume"])
def test_a_failed_placement_says_where_the_old_file_is(
    lib: _Library, monkeypatch: pytest.MonkeyPatch, other_volume: bool
) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    old_bytes = path.read_bytes()
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    new_bytes = source.read_bytes()
    monkeypatch.setattr(content_replacement, "_same_volume", lambda _src, _dst: not other_volume)

    def locked(_origin: Path, _destination: Path) -> None:
        raise OSError("The file is locked by another program.")

    monkeypatch.setattr(content_replacement, "_place", locked)

    with pytest.raises(ContentReplaceError, match="Recycle Bin") as info:
        lib.replacement.replace(track_id, source)

    assert info.value.readable is True
    assert "untouched" in str(info.value)
    # The old file is in the Recycle Bin, not at its path: MTEE cannot restore it from there.
    assert lib.bin.contents() == [old_bytes]
    assert not path.exists()
    assert source.read_bytes() == new_bytes
    assert not (lib.music / ".song.flac.part").exists()
    assert [status for _track, status in lib.journal()] == ["recycled"]
    assert not lib.access.is_busy(TrackId.parse(track_id))


@pytest.mark.parametrize("other_volume", [False, True], ids=["same-volume", "other-volume"])
def test_a_refused_library_update_takes_the_new_file_back(
    lib: _Library, monkeypatch: pytest.MonkeyPatch, other_volume: bool
) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    new_bytes = source.read_bytes()
    monkeypatch.setattr(content_replacement, "_same_volume", lambda _src, _dst: not other_volume)

    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise ValueError("database is locked")

    monkeypatch.setattr(LibraryRepository, "move_location_in_transaction", refuse)

    with pytest.raises(ContentReplaceError, match="could not record the new file") as info:
        lib.replacement.replace(track_id, source)

    assert "database is locked" in str(info.value)
    assert not path.exists()
    assert source.read_bytes() == new_bytes
    assert not (lib.music / ".song.flac.part").exists()
    assert len(lib.bin.contents()) == 1
    assert not lib.access.is_busy(TrackId.parse(track_id))


def test_a_held_read_lease_makes_the_replacement_wait(lib: _Library) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    old_bytes = path.read_bytes()
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    new_bytes = source.read_bytes()
    track = TrackId.parse(track_id)
    entered = threading.Event()
    release = threading.Event()

    def hold_reader() -> None:
        with lib.access.acquire_read(track, "test reader"):
            entered.set()
            release.wait(20)

    def replace() -> None:
        outcome.append(lib.replacement.replace(track_id, source))

    outcome: list[Path] = []
    reader = threading.Thread(target=hold_reader)
    reader.start()
    writer = threading.Thread(target=replace)
    try:
        assert entered.wait(10)
        writer.start()
        writer.join(0.5)
        # Still waiting: no file has moved while the reader holds the track.
        assert writer.is_alive()
        assert path.read_bytes() == old_bytes
        assert lib.bin.calls == []
    finally:
        release.set()
        reader.join(10)
        writer.join(20)

    assert not writer.is_alive()
    assert outcome[0].resolve() == path.resolve()
    assert path.read_bytes() == new_bytes
    assert lib.bin.contents() == [old_bytes]


# ------------------------------------------------------- refusals, through the plugin context


def test_replace_content_is_a_plugin_capability_on_the_job_thread(lib: _Library) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    old_bytes = path.read_bytes()
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    new_bytes = source.read_bytes()
    context = lib.host().context_for(_MANIFEST)

    result = _replace_through(context, track_id, source)

    assert result.resolve() == path.resolve()
    assert path.read_bytes() == new_bytes
    assert lib.bin.contents() == [old_bytes]


def test_replace_content_refuses_the_graphical_thread(lib: _Library) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    old_bytes = path.read_bytes()
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    context = lib.host().context_for(_MANIFEST)

    with pytest.raises(RuntimeError, match="graphical thread"):
        context.files.replace_content(track_id, source)

    assert path.read_bytes() == old_bytes
    assert source.is_file()
    assert lib.bin.calls == []


def test_replace_content_needs_the_capability(lib: _Library) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    context = lib.host(with_replacement=False).context_for(_MANIFEST)

    with pytest.raises(CapabilityUnavailableError):
        _in_thread(lambda: context.files.replace_content(track_id, source))

    assert source.is_file()
    assert lib.bin.calls == []


def test_a_track_without_a_file_is_refused(lib: _Library) -> None:
    context = lib.host().context_for(_MANIFEST)
    stored = context.track_sources.upsert(
        [SourceTrack("remote-1", "Server song", artists=("Ann",), duration_us=2_000_000)]
    )
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")

    with pytest.raises(NonFileTrackError, match="provided by sample"):
        _replace_through(context, stored["remote-1"], source)

    assert source.is_file()
    assert lib.bin.calls == []


def test_a_missing_track_file_is_reported(lib: _Library) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    (lib.music / "song.flac").unlink()
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    context = lib.host().context_for(_MANIFEST)

    with pytest.raises(FileNotFoundError):
        _replace_through(context, track_id, source)

    assert source.is_file()


def test_an_unknown_track_is_reported(lib: _Library) -> None:
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")
    context = lib.host().context_for(_MANIFEST)

    with pytest.raises(LookupError):
        _replace_through(context, "00000000-0000-4000-8000-000000000000", source)

    assert source.is_file()


def test_a_missing_source_is_reported(lib: _Library) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    old_bytes = path.read_bytes()
    context = lib.host().context_for(_MANIFEST)

    with pytest.raises(FileNotFoundError):
        _replace_through(context, track_id, lib.incoming / "absent.flac")

    assert path.read_bytes() == old_bytes
    assert lib.bin.calls == []


def test_a_source_inside_the_library_is_refused(lib: _Library) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    old_bytes = path.read_bytes()
    other = lib.add_track("other.flac", seconds=1.0, title="Other", artist="Cy")
    assert other != track_id
    context = lib.host().context_for(_MANIFEST)

    with pytest.raises(ValueError, match="already in the library"):
        _replace_through(context, track_id, lib.music / "other.flac")

    assert path.read_bytes() == old_bytes
    assert lib.bin.calls == []


def test_a_directory_is_not_a_regular_file(lib: _Library) -> None:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    path = lib.music / "song.flac"
    old_bytes = path.read_bytes()
    folder = lib.base / "folder-as-source"
    folder.mkdir()
    context = lib.host().context_for(_MANIFEST)

    with pytest.raises(ValueError, match="not a regular file"):
        _replace_through(context, track_id, folder)

    assert path.read_bytes() == old_bytes
    assert lib.bin.calls == []
