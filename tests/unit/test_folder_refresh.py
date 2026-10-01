"""Folder refresh: a flat diff of one folder against the library, without a rescan."""

from __future__ import annotations

import wave
from pathlib import Path

from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.folder_refresh import refresh_folder
from mtee.services.library_scanner import LibraryScanner
from mtee.services.metadata_reader import MetadataReader


def _write_wav(path: Path, frames: int = 8) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * frames)


class _Library:
    def __init__(self, tmp_path: Path) -> None:
        self.root_path = tmp_path / "music"
        self.root_path.mkdir()
        self.database = Database(tmp_path / "library.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.scanner = LibraryScanner()
        self.reader = MetadataReader()
        self.root_id = self.library.add_root(self.root_path)["id"]

    def full_scan(self) -> int:
        generation = self.library.begin_scan(self.root_id)
        for batch in self.scanner.scan(self.root_path):
            self.library.upsert_folders(self.root_id, batch.folders, generation)
            self.library.upsert_locations(
                self.root_id,
                [
                    (e.relative_path, e.path, e.revision, self.reader.read(e.path))
                    for e in batch.entries
                ],
                generation,
            )
        self.library.finish_scan(self.root_id, generation, complete=True)
        return generation

    def refresh(self, relative: str = ""):
        return refresh_folder(
            self.library,
            self.scanner,
            self.reader,
            self.root_id,
            self.root_path,
            relative,
            wait=lambda _seconds: None,
        )

    def names(self, relative: str = "") -> list[str]:
        return sorted(
            row["filename"] for row in self.library.tracks_in_folder(self.root_id, relative)
        )


def test_added_removed_and_renamed_files_follow_the_disk(tmp_path: Path) -> None:
    lib = _Library(tmp_path)
    _write_wav(lib.root_path / "one.wav")
    _write_wav(lib.root_path / "other" / "keep.wav")
    generation = lib.full_scan()
    assert lib.names() == ["one.wav"]

    _write_wav(lib.root_path / "two.wav")
    assert lib.refresh().folders == ("",)
    assert lib.names() == ["one.wav", "two.wav"]

    (lib.root_path / "one.wav").unlink()
    lib.refresh()
    assert lib.names() == ["two.wav"]

    (lib.root_path / "two.wav").rename(lib.root_path / "renamed.wav")
    lib.refresh()
    assert lib.names() == ["renamed.wav"]
    assert lib.names("other") == ["keep.wav"]
    assert lib.library.current_generation(lib.root_id) == generation


def test_nothing_changed_reports_no_folder(tmp_path: Path) -> None:
    lib = _Library(tmp_path)
    _write_wav(lib.root_path / "one.wav")
    lib.full_scan()

    result = lib.refresh()

    assert result.folders == ()
    assert not result.unstable


def test_subfolders_appear_and_disappear_with_their_content(tmp_path: Path) -> None:
    lib = _Library(tmp_path)
    _write_wav(lib.root_path / "one.wav")
    lib.full_scan()

    _write_wav(lib.root_path / "new" / "inside.wav")
    lib.refresh()
    assert "new" in lib.library.folders(lib.root_id)
    lib.refresh("new")
    assert lib.names("new") == ["inside.wav"]

    (lib.root_path / "new" / "inside.wav").unlink()
    (lib.root_path / "new").rmdir()
    lib.refresh()
    assert "new" not in lib.library.folders(lib.root_id)
    assert lib.names("new") == []


def test_growing_file_is_left_for_the_next_pass(tmp_path: Path) -> None:
    lib = _Library(tmp_path)
    _write_wav(lib.root_path / "one.wav")
    lib.full_scan()
    growing = lib.root_path / "copy.wav"
    _write_wav(growing)

    def wait(_seconds: float) -> None:
        _write_wav(growing, frames=4_000)

    result = refresh_folder(
        lib.library, lib.scanner, lib.reader, lib.root_id, lib.root_path, "", wait=wait
    )

    assert result.unstable
    assert lib.names() == ["one.wav"]
    assert lib.refresh().folders == ("",)
    assert lib.names() == ["copy.wav", "one.wav"]


def test_reconcile_does_nothing_after_a_rescan_started(tmp_path: Path) -> None:
    lib = _Library(tmp_path)
    _write_wav(lib.root_path / "one.wav")
    generation = lib.full_scan()
    lib.library.begin_scan(lib.root_id)

    changed = lib.library.reconcile_folder(
        lib.root_id, "", present_files=[], present_folders=[], generation=generation
    )

    assert changed == []
    assert lib.names() == ["one.wav"]
