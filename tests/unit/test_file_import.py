"""Placing a file that is not in the library into a folder, never replacing a file (plan 122)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtee.services import file_import
from mtee.services.file_import import numbered_name, place_without_overwrite


def _file(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_numbered_names_follow_the_name_stem_number_rule() -> None:
    assert numbered_name("song.mp3", 1) == "song.mp3"
    assert numbered_name("song.mp3", 2) == "song (2).mp3"
    assert numbered_name("song.tar.gz", 3) == "song.tar (3).gz"
    assert numbered_name("noext", 2) == "noext (2)"


def test_a_free_name_is_kept(tmp_path: Path) -> None:
    source = _file(tmp_path / "staging" / "song.mp3", b"new")
    folder = tmp_path / "music"
    folder.mkdir()

    placed = place_without_overwrite(source, folder)

    assert placed == folder / "song.mp3"
    assert placed.read_bytes() == b"new"
    assert not source.exists()


def test_a_taken_name_gets_the_next_number_and_the_old_file_is_byte_identical(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "music"
    existing = _file(folder / "song.mp3", b"\x00original\xff" * 100)
    second = _file(folder / "song (2).mp3", b"second")
    before = (existing.read_bytes(), second.read_bytes())
    source = _file(tmp_path / "staging" / "song.mp3", b"incoming")

    placed = place_without_overwrite(source, folder)

    assert placed == folder / "song (3).mp3"
    assert placed.read_bytes() == b"incoming"
    assert (existing.read_bytes(), second.read_bytes()) == before
    assert not source.exists()


def test_a_reserved_name_is_skipped_although_no_file_is_there(tmp_path: Path) -> None:
    folder = tmp_path / "music"
    folder.mkdir()
    source = _file(tmp_path / "staging" / "song.mp3", b"x")

    placed = place_without_overwrite(source, folder, lambda target: target.name == "song.mp3")

    assert placed.name == "song (2).mp3"


def test_a_name_taken_while_the_file_is_moved_is_tried_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "music"
    folder.mkdir()
    source = _file(tmp_path / "staging" / "song.mp3", b"incoming")
    real_place = file_import._place
    raced: list[bool] = []

    def place_after_a_rival(current: Path, target: Path) -> None:
        if not raced:  # another program creates the file between the check and the move
            raced.append(True)
            target.write_bytes(b"rival")
        real_place(current, target)

    monkeypatch.setattr(file_import, "_place", place_after_a_rival)

    placed = place_without_overwrite(source, folder)

    assert placed == folder / "song (2).mp3"
    assert (folder / "song.mp3").read_bytes() == b"rival"
    assert placed.read_bytes() == b"incoming"


def test_another_volume_goes_through_a_part_file_and_leaves_no_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "music"
    existing = _file(folder / "song.mp3", b"original")
    source = _file(tmp_path / "staging" / "song.mp3", b"incoming" * 1000)
    monkeypatch.setattr(file_import, "_same_volume", lambda *_: False)
    seen: list[list[str]] = []
    real_place = file_import._place

    def watch(current: Path, target: Path) -> None:
        seen.append(sorted(path.name for path in folder.iterdir()))
        real_place(current, target)

    monkeypatch.setattr(file_import, "_place", watch)

    placed = place_without_overwrite(source, folder)

    assert placed == folder / "song (2).mp3"
    assert placed.read_bytes() == b"incoming" * 1000
    assert existing.read_bytes() == b"original"
    assert not source.exists()
    # While the file was put in place the final name did not exist yet, only the part file.
    assert seen == [[".song.mp3.part", "song.mp3"]]
    assert sorted(path.name for path in folder.iterdir()) == ["song (2).mp3", "song.mp3"]


def test_a_part_file_that_exists_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "music"
    stale = _file(folder / ".song.mp3.part", b"someone else's")
    source = _file(tmp_path / "staging" / "song.mp3", b"incoming")
    monkeypatch.setattr(file_import, "_same_volume", lambda *_: False)

    placed = place_without_overwrite(source, folder)

    assert placed == folder / "song.mp3"
    assert placed.read_bytes() == b"incoming"
    assert stale.read_bytes() == b"someone else's"


def test_a_failed_copy_leaves_the_source_and_no_part_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "music"
    folder.mkdir()
    source = _file(tmp_path / "staging" / "song.mp3", b"incoming")
    monkeypatch.setattr(file_import, "_same_volume", lambda *_: False)

    def broken(*_arguments: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(file_import.shutil, "copyfileobj", broken)

    with pytest.raises(OSError, match="disk full"):
        place_without_overwrite(source, folder)

    assert source.read_bytes() == b"incoming"
    assert list(folder.iterdir()) == []


def test_a_failed_move_leaves_the_source_and_the_folder_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "music"
    folder.mkdir()
    source = _file(tmp_path / "staging" / "song.mp3", b"incoming")

    def locked(_current: Path, _target: Path) -> None:
        raise PermissionError("in use")

    monkeypatch.setattr(file_import, "_place", locked)

    with pytest.raises(PermissionError):
        place_without_overwrite(source, folder)

    assert source.read_bytes() == b"incoming"
    assert list(folder.iterdir()) == []
