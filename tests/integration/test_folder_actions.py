"""Create and rename a folder of a source on disk: the records follow, refusals hold (plan 132.2).

Real folders and small WAV files under ``tmp_path``; the library and the access coordinator are
real, on a temporary database.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_move_service import FileMoveService


class _Library:
    def __init__(self, base: Path) -> None:
        self.music = base / "music"
        (self.music / "sub").mkdir(parents=True)
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.root_id = str(self.library.add_root(self.music)["id"])
        self.access = FileAccessCoordinator()
        self.service = FileMoveService(self.database, self.library, self.access)
        self.track_ids: list[str] = []
        self._scan(["sub/a.wav", "sub/b.wav"])

    def _scan(self, relatives: list[str]) -> None:
        """One complete scan of the given files: a scan marks what it did not see as absent."""
        entries = []
        for relative in relatives:
            path = self.music / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(8000)
                handle.writeframes(b"\x00\x00" * 800)
            entries.append(
                (
                    relative,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(
                        title=(path.stem,),
                        artist=("Test artist",),
                        technical=TechnicalInfo(duration_us=100_000),
                    ),
                )
            )
        generation = self.library.begin_scan(self.root_id)
        self.library.upsert_locations(self.root_id, entries, generation)
        self.library.finish_scan(self.root_id, generation, complete=True)
        self.track_ids = []
        for relative in relatives:
            owner = self.library.path_owner(self.music / relative)
            assert owner is not None
            self.track_ids.append(owner)


@pytest.fixture
def lib(tmp_path: Path):
    library = _Library(tmp_path)
    yield library
    library.database.close()


def test_create_folder_makes_the_directory_and_lists_it_at_once(lib: _Library) -> None:
    result = lib.service.create_folder(lib.root_id, "", "Fresh")
    assert result.status == "created"
    assert (lib.music / "Fresh").is_dir()
    assert "Fresh" in lib.library.folders(lib.root_id)
    nested = lib.service.create_folder(lib.root_id, "sub", "Inner")
    assert nested.status == "created"
    assert nested.relative == "sub/Inner"
    assert (lib.music / "sub" / "Inner").is_dir()
    assert "sub/Inner" in lib.library.folders(lib.root_id)


def test_create_folder_refuses_an_existing_name_and_bad_names(lib: _Library) -> None:
    assert lib.service.create_folder(lib.root_id, "", "sub").status == "conflict"
    assert (lib.music / "sub" / "a.wav").is_file()
    before = sorted(path.name for path in lib.music.iterdir())
    for bad in ("a/b", "x:y", "CON", "end.", "  ", ".."):
        result = lib.service.create_folder(lib.root_id, "", bad)
        assert result.status == "failed", bad
    assert sorted(path.name for path in lib.music.iterdir()) == before


def test_rename_moves_the_folder_and_its_records_follow(lib: _Library) -> None:
    first = lib.track_ids[0]
    with lib.database.transaction() as connection:
        connection.execute(
            "INSERT INTO track_analysis(track_id,bpm,key_tonic,key_minor,algorithm_version,"
            "analyzed_at_utc) VALUES(?,?,?,?,?,?)",
            (first, 121.0, 2, 1, 1, "2026-11-04T00:00:00+00:00"),
        )

    result = lib.service.rename_folder(lib.root_id, "sub", "renamed")

    assert result.status == "renamed"
    assert result.relative == "renamed"
    assert result.previous == "sub"
    assert not (lib.music / "sub").exists()
    assert (lib.music / "renamed" / "a.wav").is_file()
    assert lib.library.track_folder(first) == (lib.root_id, "renamed")
    record = lib.library.source_record(first)
    assert record is not None
    assert record.path == (lib.music / "renamed" / "a.wav").resolve()
    assert lib.library.path_owner(lib.music / "renamed" / "b.wav") == lib.track_ids[1]
    assert lib.library.path_owner(lib.music / "sub" / "a.wav") is None
    assert "renamed" in lib.library.folders(lib.root_id)
    count = (
        lib.database.connection()
        .execute("SELECT COUNT(*) FROM track_analysis WHERE track_id=? AND bpm=121.0", (first,))
        .fetchone()[0]
    )
    assert count == 1


def test_rename_refuses_an_existing_name_and_leaves_everything(lib: _Library) -> None:
    lib.service.create_folder(lib.root_id, "", "other")
    result = lib.service.rename_folder(lib.root_id, "sub", "other")
    assert result.status == "conflict"
    assert (lib.music / "sub" / "a.wav").is_file()
    assert lib.library.track_folder(lib.track_ids[0]) == (lib.root_id, "sub")


def test_rename_refuses_a_source_and_an_invalid_name(lib: _Library) -> None:
    assert lib.service.rename_folder(lib.root_id, "", "anything").status == "failed"
    assert lib.service.rename_folder(lib.root_id, "sub", "bad:name").status == "failed"
    assert (lib.music / "sub").is_dir()


def test_rename_is_busy_while_a_track_of_the_folder_is_in_use(lib: _Library) -> None:
    with lib.access.acquire(TrackId.parse(lib.track_ids[0]), "test playback", timeout_seconds=0):
        result = lib.service.rename_folder(lib.root_id, "sub", "renamed")
    assert result.status == "busy"
    assert (lib.music / "sub" / "a.wav").is_file()
    assert lib.library.track_folder(lib.track_ids[0]) == (lib.root_id, "sub")


def test_unnamed_folder_takes_the_first_free_number_and_never_overwrites(lib: _Library) -> None:
    # Plan 135: a new folder is made at once as "Unnamed folder NN", with no name asked.
    assert lib.service.next_folder_name(lib.root_id, "") == "Unnamed folder 01"
    assert lib.service.create_folder(lib.root_id, "", "Unnamed folder 01").status == "created"
    assert lib.service.next_folder_name(lib.root_id, "") == "Unnamed folder 02"
    (lib.music / "Unnamed folder 02").mkdir()
    assert lib.service.next_folder_name(lib.root_id, "") == "Unnamed folder 03"
    assert lib.service.create_folder(lib.root_id, "", "Unnamed folder 01").status == "conflict"
