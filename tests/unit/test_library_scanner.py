"""Directory traversal behavior for selected library roots."""

from __future__ import annotations

import os
import wave
from pathlib import Path

import pytest

from mtee.services.library_scanner import LibraryScanner


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 8)


def test_scans_accented_nested_files_and_empty_folders(tmp_path: Path) -> None:
    root = tmp_path / "Ma collection épurée"
    _write_wav(root / "Été" / "Live" / "titre.wav")
    (root / "vide").mkdir(parents=True)
    (root / "notes.txt").write_text("not audio", encoding="utf-8")

    batches = list(LibraryScanner(batch_size=1).scan(root))

    entries = [entry for batch in batches for entry in batch.entries]
    folders = {folder for batch in batches for folder in batch.folders}
    assert [entry.relative_path for entry in entries] == ["Été/Live/titre.wav"]
    assert {"Été", "Été/Live", "vide"} <= folders
    assert batches[-1].complete
    assert not any(batch.issues for batch in batches)


def test_skips_symbolic_directory_links_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "root"
    target = tmp_path / "outside"
    _write_wav(target / "outside.wav")
    root.mkdir()
    link = root / "shortcut"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable")

    batches = list(LibraryScanner().scan(root))

    assert not [entry for batch in batches for entry in batch.entries]
    assert batches[-1].complete


def test_cancellation_keeps_the_partial_batch_marked_incomplete(tmp_path: Path) -> None:
    root = tmp_path / "root"
    for index in range(5):
        _write_wav(root / f"{index}.wav")
    checked = 0

    def cancel_after_one_check() -> bool:
        nonlocal checked
        checked += 1
        return checked > 2

    batches = list(LibraryScanner(batch_size=2).scan(root, is_cancelled=cancel_after_one_check))

    assert any(batch.cancelled for batch in batches)
    assert not batches[-1].complete
    assert len([entry for batch in batches for entry in batch.entries]) < 5


def test_root_access_failure_is_reported_without_claiming_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "denied"
    root.mkdir()
    original_scandir = os.scandir

    def denied(path):
        if Path(path) == root:
            raise PermissionError("blocked for test")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", denied)

    batches = list(LibraryScanner().scan(root))

    assert not batches[-1].complete
    assert batches[-1].issues[0].path == str(root.resolve())
    assert "blocked for test" in batches[-1].issues[0].message


def test_a_root_symlink_is_not_followed(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "root-link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable")

    batches = list(LibraryScanner().scan(link))

    assert not batches[-1].complete
    assert batches[-1].issues


def test_list_directory_is_flat_and_filtered(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _write_wav(root / "a.wav")
    _write_wav(root / "sub" / "deep.wav")
    (root / "notes.txt").write_text("not audio", encoding="utf-8")
    _write_wav(root / "song.mtee-0b9d8b3e-1c5f-4d21-9a53-3f6f5a7c2e10.tmp.wav")

    listing = LibraryScanner().list_directory(root, "")

    assert listing.complete
    assert [entry.relative_path for entry in listing.entries] == ["a.wav"]
    assert listing.folders == ("sub",)
    nested = LibraryScanner().list_directory(root, "sub")
    assert [entry.relative_path for entry in nested.entries] == ["sub/deep.wav"]


def test_list_directory_reports_a_missing_folder(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    listing = LibraryScanner().list_directory(root, "gone")

    assert not listing.complete
    assert listing.entries == ()
    assert listing.issues
    assert not LibraryScanner().list_directory(root, "../x").complete
