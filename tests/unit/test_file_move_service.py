"""Moving a library file into another folder: disk, library and refusals, on real copies."""

from __future__ import annotations

import threading
import wave
from pathlib import Path

import pytest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_move_service import FileMoveError, FileMoveService


class _Library:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.music = base / "music"
        (self.music / "sub").mkdir(parents=True)
        (self.music / "other").mkdir()
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.root_id = self.library.add_root(self.music)["id"]
        self.access = FileAccessCoordinator()
        self.service = FileMoveService(self.database, self.library, self.access)

    def add_track(self, relative: str) -> str:
        path = self.music / relative
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 800)
        generation = self.library.begin_scan(self.root_id)
        self.library.upsert_locations(
            self.root_id,
            [
                (
                    relative,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(title=(path.stem,), technical=TechnicalInfo(duration_us=100)),
                )
            ],
            generation,
        )
        owner = self.library.path_owner(path)
        assert owner is not None
        return owner


@pytest.fixture
def lib(tmp_path: Path):
    library = _Library(tmp_path)
    yield library
    library.database.close()


def test_move_keeps_the_track_identity_and_updates_the_library(lib: _Library) -> None:
    track_id = lib.add_track("a.wav")
    result = lib.service.move(track_id, lib.service.resolve_folder(lib.root_id, "sub"))
    assert result.status == "moved"
    assert not (lib.music / "a.wav").exists()
    assert (lib.music / "sub" / "a.wav").is_file()
    assert lib.library.source_record(track_id).path == (lib.music / "sub" / "a.wav").resolve()
    assert lib.library.track_folder(track_id) == (lib.root_id, "sub")
    assert lib.library.path_owner(lib.music / "sub" / "a.wav") == track_id


def test_move_to_the_root_folder(lib: _Library) -> None:
    track_id = lib.add_track("sub/a.wav")
    result = lib.service.move(track_id, lib.service.resolve_folder(lib.root_id, ""))
    assert result.status == "moved"
    assert lib.library.track_folder(track_id) == (lib.root_id, "")


def test_same_folder_is_unchanged(lib: _Library) -> None:
    track_id = lib.add_track("a.wav")
    result = lib.service.move(track_id, lib.service.resolve_folder(lib.root_id, ""))
    assert result.status == "unchanged"
    assert (lib.music / "a.wav").is_file()


def test_existing_name_is_never_overwritten(lib: _Library) -> None:
    track_id = lib.add_track("a.wav")
    other_id = lib.add_track("sub/a.wav")
    before = (lib.music / "sub" / "a.wav").read_bytes()
    result = lib.service.move(track_id, lib.service.resolve_folder(lib.root_id, "sub"))
    assert result.status == "conflict"
    assert (lib.music / "a.wav").is_file()
    assert (lib.music / "sub" / "a.wav").read_bytes() == before
    assert lib.library.path_owner(lib.music / "sub" / "a.wav") == other_id


def test_a_file_changed_on_disk_is_refused(lib: _Library) -> None:
    track_id = lib.add_track("a.wav")
    with (lib.music / "a.wav").open("ab") as handle:
        handle.write(b"tail")
    result = lib.service.move(track_id, lib.service.resolve_folder(lib.root_id, "sub"))
    assert result.status == "conflict"
    assert (lib.music / "a.wav").is_file()


def test_a_busy_file_stays_where_it_is(lib: _Library) -> None:
    track_id = lib.add_track("a.wav")
    folder = lib.service.resolve_folder(lib.root_id, "sub")
    outcome: list[str] = []
    held = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with lib.access.acquire(TrackId.parse(track_id), "test"):
            held.set()
            release.wait(5)

    thread = threading.Thread(target=hold)
    thread.start()
    assert held.wait(5)
    try:
        outcome.append(lib.service.move(track_id, folder).status)
    finally:
        release.set()
        thread.join()
    assert outcome == ["busy"]
    assert (lib.music / "a.wav").is_file()


def test_a_database_failure_puts_the_file_back(lib: _Library, monkeypatch) -> None:
    track_id = lib.add_track("a.wav")

    def refuse(*_args, **_kwargs) -> None:
        raise ValueError("database is locked")

    monkeypatch.setattr(lib.service, "_record", refuse)
    result = lib.service.move(track_id, lib.service.resolve_folder(lib.root_id, "sub"))
    assert result.status == "failed"
    assert (lib.music / "a.wav").is_file()
    assert not (lib.music / "sub" / "a.wav").exists()
    assert lib.library.track_folder(track_id) == (lib.root_id, "")


def test_unknown_or_escaping_folders_are_refused(lib: _Library) -> None:
    with pytest.raises(FileMoveError):
        lib.service.resolve_folder("00000000-0000-0000-0000-000000000000", "")
    with pytest.raises(FileMoveError):
        lib.service.resolve_folder(lib.root_id, "missing")
