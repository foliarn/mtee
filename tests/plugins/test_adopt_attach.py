"""Plan 126.5: keeping a track's identity between its file and a plugin source.

``track_sources.adopt`` turns a library track whose file left the library into a source track of
the plugin; ``files.attach_file`` gives a source track of the plugin its local file. Both run on a
temporary library with real FLAC copies (made by the pinned ffmpeg) and the fake Recycle Bin of
the replacement tests. The library, the trash journal and the file access coordinator are real.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from tests.plugins.test_replace_content import _in_thread, _Library

from mtee.domain.play_log import PlayedTrack, PlayEvent
from mtee.domain.source_tracks import SourceTrack
from mtee.domain.tracks import TrackId
from mtee.models.track_list_model import TrackListModel
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.play_log_repository import PlayLogRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.plugins.api import CapabilityUnavailableError, PluginContext, PluginManifest
from mtee.plugins.context import PluginHost
from mtee.services import file_import
from mtee.services.file_move_service import FileMoveService
from mtee.services.playlist_service import PlaylistService
from mtee.services.track_identity import TrackIdentity

_MANIFEST = PluginManifest("sample", "Sample", "", "1.0.0", 1, "mtee.plugins.sample:create")
_OTHER = "other"


class _Roots:
    def addRoot(self, selected: str) -> str:  # noqa: N802
        return "root-new"

    def rescanRoot(self, root_id: str) -> str:  # noqa: N802
        return root_id


@pytest.fixture
def lib(qapp: Any, tmp_path: Path) -> Iterator[_Library]:
    created = _Library(qapp, tmp_path)
    yield created
    created.close()


def _host(
    lib: _Library,
    *,
    identity: bool = True,
    changed: Callable[[Sequence[str]], None] | None = None,
) -> PluginHost:
    return PluginHost(
        data_dir=lib.base / "data",
        database=lib.database,
        settings=SettingsRepository(lib.database),
        library=lib.library,
        playlists=PlaylistService(PlaylistsRepository(lib.database), lib.library),
        jobs=lib.jobs,
        file_moves=FileMoveService(lib.database, lib.library, lib.access),
        recycle=lib.trash,
        roots=_Roots(),
        refresh_playlists=lambda: None,
        source_tracks=SourceTrackRepository(lib.database),
        file_access=lib.access,
        content_replacement=lib.replacement,
        track_identity=TrackIdentity(lib.database, lib.library, lib.access) if identity else None,
        track_files_changed=changed,
    )


def _context(lib: _Library, **kwargs: Any) -> PluginContext:
    return _host(lib, **kwargs).context_for(_MANIFEST)


def _entry(key: str = "k1") -> SourceTrack:
    return SourceTrack(
        source_key=key,
        title="Remote song",
        artists=("Ann",),
        album="Album",
        duration_us=500_000,
    )


def _recycle(lib: _Library, track_id: str) -> None:
    """Send the file of the track to the fake Recycle Bin, as a confirmed delete does."""
    with lib.access.acquire(TrackId.parse(track_id), "test recycle"):
        recycled, message = lib.trash.recycle_held(track_id)
    assert recycled, message


def _adopted_track(lib: _Library, context: PluginContext) -> str:
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    _recycle(lib, track_id)
    assert context.track_sources.adopt(track_id, _entry()) == track_id
    return track_id


def _names(lib: _Library, folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


# ------------------------------------------------------------------ adopt


def test_adopt_keeps_the_track_id_and_everything_that_refers_to_it(lib: _Library) -> None:
    context = _context(lib)
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    playlist_id = PlaylistService(PlaylistsRepository(lib.database), lib.library).create_playlist(
        "Mix", [track_id]
    )
    event = PlayEvent(
        event_id=str(uuid4()),
        track=PlayedTrack(track_id=track_id, path="song.flac", artist="Ann", title="Old"),
        started_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        ended_at=datetime(2026, 1, 1, 10, 3, tzinfo=UTC),
        heard_ms=180_000,
        counted=True,
    )
    PlayLogRepository(lib.database).insert_events([event], str(uuid4()))
    AnalysisRepository(lib.database).save_result(
        track_id, bpm=120.0, key=None, source_duration_us=500_000
    )
    _recycle(lib, track_id)

    adopted = context.track_sources.adopt(track_id, _entry("k1"))

    assert adopted == track_id
    entries = context.track_sources.list()
    assert [(entry.track_id, entry.track.source_key, entry.available) for entry in entries] == [
        (track_id, "k1", True)
    ]
    assert lib.library.source_record(track_id) is None
    assert lib.library.source_origin(track_id) == ("sample", "k1")
    connection = lib.database.connection()
    playlist_rows = connection.execute(
        "SELECT track_id FROM playlist_entries WHERE playlist_id=?", (playlist_id,)
    ).fetchall()
    assert [str(row[0]) for row in playlist_rows] == [track_id]
    play_rows = connection.execute("SELECT track_id FROM play_events").fetchall()
    assert [str(row[0]) for row in play_rows] == [track_id]
    analysis = AnalysisRepository(lib.database).get(track_id)
    assert analysis is not None
    assert analysis.bpm == pytest.approx(120.0, abs=0.01)
    row = lib.library.tracks_by_ids([track_id])[0]
    assert row["sourcePluginId"] == "sample"
    assert row["sourceKey"] == "k1"


def test_adopt_with_the_same_key_again_changes_nothing(lib: _Library) -> None:
    context = _context(lib)
    track_id = _adopted_track(lib, context)
    before = lib.database.connection().execute("SELECT * FROM plugin_source_tracks").fetchall()

    assert context.track_sources.adopt(track_id, _entry("k1")) == track_id

    after = lib.database.connection().execute("SELECT * FROM plugin_source_tracks").fetchall()
    assert [tuple(row) for row in after] == [tuple(row) for row in before]


def test_adopt_refuses_a_track_that_still_has_a_file(lib: _Library) -> None:
    context = _context(lib)
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")

    with pytest.raises(ValueError, match="still has a file"):
        context.track_sources.adopt(track_id, _entry())

    assert lib.library.source_origin(track_id) is None
    assert lib.library.source_record(track_id) is not None


def test_adopt_refuses_a_track_that_a_library_folder_still_lists(lib: _Library) -> None:
    context = _context(lib)
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    # The file is gone from disk, but the library has not seen it yet: still listed.
    (lib.music / "song.flac").unlink()

    with pytest.raises(ValueError, match="still has a file"):
        context.track_sources.adopt(track_id, _entry())


def test_adopt_refuses_another_plugins_track(lib: _Library) -> None:
    context = _context(lib)
    identities, _changed = SourceTrackRepository(lib.database).upsert(_OTHER, [_entry("x")])
    track_id = identities["x"]

    with pytest.raises(ValueError, match="another plugin"):
        context.track_sources.adopt(track_id, _entry("k1"))


def test_adopt_refuses_a_key_that_another_track_holds(lib: _Library) -> None:
    context = _context(lib)
    _adopted_track(lib, context)
    other = lib.add_track("second.flac", seconds=0.5, title="Second", artist="Bea")
    _recycle(lib, other)

    with pytest.raises(ValueError, match="already belongs to another track"):
        context.track_sources.adopt(other, _entry("k1"))


def test_adopt_refuses_an_unknown_track(lib: _Library) -> None:
    context = _context(lib)
    with pytest.raises(ValueError, match="does not exist"):
        context.track_sources.adopt(str(TrackId.new()), _entry())


# ------------------------------------------------------------------ attach


def test_attach_gives_a_downloaded_copy_the_same_track_id(lib: _Library, qapp: Any) -> None:
    context = _context(lib)
    track_id = _adopted_track(lib, context)
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")
    new_bytes = incoming.read_bytes()
    folder = lib.music / "Downloads"

    path = _in_thread(lambda: context.files.attach_file(track_id, incoming, folder))

    assert path == folder / "download.flac"
    assert path.read_bytes() == new_bytes
    assert not incoming.exists()
    record = lib.library.source_record(track_id)
    assert record is not None
    assert record.path.resolve() == path.resolve()
    row = lib.library.track(track_id)
    assert row["title"] == "Downloaded"
    assert row["artist"] == "Bea"
    assert lib.library.track_folder(track_id) == (lib.root_id, "Downloads")
    assert track_id in lib.library.track_ids_in_tree(lib.root_id, "Downloads")
    listed = lib.library.tracks_in_folder(lib.root_id, "Downloads")
    assert [row["id"] for row in listed] == [track_id]
    assert lib.library.source_origin(track_id) is None
    assert context.track_sources.list() == []
    assert lib.library.path_owner(path) == track_id


def test_a_taken_name_gets_the_next_free_name(lib: _Library) -> None:
    context = _context(lib)
    track_id = _adopted_track(lib, context)
    folder = lib.music / "Downloads"
    folder.mkdir()
    (folder / "download.flac").write_bytes(b"not mine")
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")

    path = _in_thread(lambda: context.files.attach_file(track_id, incoming, folder))

    assert path == folder / "download (2).flac"
    assert (folder / "download.flac").read_bytes() == b"not mine"
    assert lib.library.path_owner(path) == track_id


def test_another_volume_goes_through_a_part_file(
    lib: _Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(lib)
    track_id = _adopted_track(lib, context)
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")
    folder = lib.music / "Downloads"
    monkeypatch.setattr(file_import, "_same_volume", lambda _source, _folder: False)
    placed: list[str] = []
    real_place = file_import._place

    def record(source: Path, target: Path) -> None:
        placed.append(Path(source).name)
        real_place(source, target)

    monkeypatch.setattr(file_import, "_place", record)

    path = _in_thread(lambda: context.files.attach_file(track_id, incoming, folder))

    assert placed == [".download.flac.part"]
    assert path == folder / "download.flac"
    assert _names(lib, folder) == ["download.flac"]
    assert not incoming.exists()
    assert lib.library.track(track_id)["title"] == "Downloaded"


def test_a_failed_copy_to_another_volume_changes_nothing(
    lib: _Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(lib)
    track_id = _adopted_track(lib, context)
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")
    original = incoming.read_bytes()
    folder = lib.music / "Downloads"
    monkeypatch.setattr(file_import, "_same_volume", lambda _source, _folder: False)

    def disk_full(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("No space left on device")

    monkeypatch.setattr(file_import.shutil, "copyfileobj", disk_full)

    with pytest.raises(OSError, match="No space left"):
        _in_thread(lambda: context.files.attach_file(track_id, incoming, folder))

    assert incoming.read_bytes() == original
    assert _names(lib, folder) == []
    assert lib.library.source_record(track_id) is None
    assert lib.library.source_origin(track_id) == ("sample", "k1")
    assert [entry.track_id for entry in context.track_sources.list()] == [track_id]


def test_a_failed_library_update_puts_the_file_back(
    lib: _Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(lib)
    track_id = _adopted_track(lib, context)
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")
    original = incoming.read_bytes()
    folder = lib.music / "Downloads"

    def refused(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(LibraryRepository, "attach_location_in_transaction", refused)

    with pytest.raises(RuntimeError, match="database is locked"):
        _in_thread(lambda: context.files.attach_file(track_id, incoming, folder))

    assert incoming.read_bytes() == original
    assert not (folder / "download.flac").exists()
    assert lib.library.source_record(track_id) is None
    assert lib.library.source_origin(track_id) == ("sample", "k1")
    assert [entry.track_id for entry in context.track_sources.list()] == [track_id]


def test_attach_refuses_a_track_that_is_not_a_source_track(lib: _Library) -> None:
    context = _context(lib)
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")

    with pytest.raises(ValueError, match="not a track of a plugin source"):
        _in_thread(lambda: context.files.attach_file(track_id, incoming, lib.music / "Downloads"))

    assert incoming.is_file()


def test_attach_refuses_another_plugins_track(lib: _Library) -> None:
    context = _context(lib)
    identities = SourceTrackRepository(lib.database).upsert(_OTHER, [_entry("x")])[0]
    track_id = identities["x"]
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")

    with pytest.raises(ValueError, match="another plugin"):
        _in_thread(lambda: context.files.attach_file(track_id, incoming, lib.music / "Downloads"))

    assert incoming.is_file()


def test_attach_refuses_a_folder_outside_the_library(lib: _Library) -> None:
    context = _context(lib)
    track_id = _adopted_track(lib, context)
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")
    outside = lib.base / "outside"

    with pytest.raises(ValueError, match="not in the library"):
        _in_thread(lambda: context.files.attach_file(track_id, incoming, outside))

    assert incoming.is_file()
    assert not outside.exists()
    assert lib.library.source_origin(track_id) == ("sample", "k1")


def test_attach_refuses_a_source_that_is_already_in_the_library(lib: _Library) -> None:
    context = _context(lib)
    track_id = _adopted_track(lib, context)
    library_track = lib.add_track("other.flac", seconds=0.5, title="Other", artist="Bea")
    path = lib.music / "other.flac"

    with pytest.raises(ValueError, match="already in the library"):
        _in_thread(lambda: context.files.attach_file(track_id, path, lib.music / "Downloads"))

    assert path.is_file()
    assert lib.library.path_owner(path) == library_track
    assert lib.library.source_origin(track_id) == ("sample", "k1")


def test_attach_refuses_a_missing_source(lib: _Library) -> None:
    context = _context(lib)
    track_id = _adopted_track(lib, context)

    with pytest.raises(FileNotFoundError):
        _in_thread(
            lambda: context.files.attach_file(
                track_id, lib.base / "nowhere.flac", lib.music / "Downloads"
            )
        )


def test_attach_refuses_the_graphical_thread(lib: _Library) -> None:
    context = _context(lib)
    track_id = _adopted_track(lib, context)
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")

    with pytest.raises(RuntimeError, match="graphical thread"):
        context.files.attach_file(track_id, incoming, lib.music / "Downloads")

    assert incoming.is_file()


def test_the_two_capabilities_are_refused_without_an_identity(lib: _Library) -> None:
    context = _context(lib, identity=False)
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")

    with pytest.raises(CapabilityUnavailableError):
        context.track_sources.adopt(track_id, _entry())
    with pytest.raises(CapabilityUnavailableError):
        context.files.attach_file(track_id, incoming, lib.music / "Downloads")


# ------------------------------------------------------------------ the views


def _show(lib: _Library, model: TrackListModel) -> Callable[[Sequence[str]], None]:
    """What the track list does when the host says that the files of these tracks changed."""

    def refresh(track_ids: Sequence[str]) -> None:
        model.replace(lib.library.tracks_by_ids(list(track_ids)))

    return refresh


def test_the_track_list_shows_the_new_file_after_replace_content(lib: _Library, qapp: Any) -> None:
    model = TrackListModel()
    changed: list[tuple[str, ...]] = []

    refresh = _show(lib, model)

    def both(track_ids: Sequence[str]) -> None:
        changed.append(tuple(track_ids))
        refresh(track_ids)

    context = _context(lib, changed=both)
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    model.replace(lib.library.tracks_by_ids([track_id]))
    source = lib.incoming_file("take.flac", seconds=1.0, title="New", artist="Bea")

    _in_thread(lambda: context.files.replace_content(track_id, source))
    qapp.processEvents()

    assert changed == [(track_id,)]
    assert model.rows_snapshot()[0]["title"] == "New"


def test_the_track_list_shows_the_track_as_a_source_track_after_adopt(
    lib: _Library, qapp: Any
) -> None:
    model = TrackListModel()
    context = _context(lib, changed=_show(lib, model))
    track_id = lib.add_track("song.flac", seconds=0.5, title="Old", artist="Ann")
    _recycle(lib, track_id)
    model.replace(lib.library.tracks_by_ids([track_id]))

    context.track_sources.adopt(track_id, _entry())
    qapp.processEvents()

    row = model.rows_snapshot()[0]
    assert row["sourcePluginId"] == "sample"
    assert row["sourceKey"] == "k1"
    assert row["path"] == ""


def test_the_track_list_shows_the_file_after_attach(lib: _Library, qapp: Any) -> None:
    model = TrackListModel()
    context = _context(lib, changed=_show(lib, model))
    track_id = _adopted_track(lib, context)
    model.replace(lib.library.tracks_by_ids([track_id]))
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")
    folder = lib.music / "Downloads"

    _in_thread(lambda: context.files.attach_file(track_id, incoming, folder))
    qapp.processEvents()

    row = model.rows_snapshot()[0]
    assert row["title"] == "Downloaded"
    assert row["path"] == str(folder / "download.flac")
    assert row.get("sourcePluginId", "") == ""


def test_a_key_given_back_by_attach_is_free_once_the_file_is_recycled(lib: _Library) -> None:
    context = _context(lib)
    track_id = _adopted_track(lib, context)
    incoming = lib.incoming_file("download.flac", seconds=1.0, title="Downloaded", artist="Bea")
    _in_thread(lambda: context.files.attach_file(track_id, incoming, lib.music / "Downloads"))

    # attach deleted the source row, so the key is no longer held; the track has a file again,
    # so adopt refuses it for that reason.
    rows = (
        lib.database.connection()
        .execute("SELECT COUNT(*) FROM plugin_source_tracks WHERE track_id=?", (track_id,))
        .fetchone()
    )
    assert rows[0] == 0
    with pytest.raises(ValueError, match="still has a file"):
        context.track_sources.adopt(track_id, _entry("k1"))

    _recycle(lib, track_id)
    assert context.track_sources.adopt(track_id, _entry("k1")) == track_id
    assert [entry.track_id for entry in context.track_sources.list()] == [track_id]


def test_a_removed_track_keeps_its_key_against_another_track(lib: _Library) -> None:
    context = _context(lib)
    repository = SourceTrackRepository(lib.database)
    holder = repository.upsert("sample", [_entry("k1")])[0]["k1"]
    repository.remove("sample", ["k1"])
    other = lib.add_track("second.flac", seconds=0.5, title="Second", artist="Bea")
    _recycle(lib, other)

    with pytest.raises(ValueError, match="already belongs to another track"):
        context.track_sources.adopt(other, _entry("k1"))

    assert repository.upsert("sample", [_entry("k1")])[0]["k1"] == holder
