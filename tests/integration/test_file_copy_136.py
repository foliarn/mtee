"""Copy the file of a track into a library folder: nothing is ever overwritten (batch 136)."""

from __future__ import annotations

from pathlib import Path

from tests.integration.test_folder_actions import _Library, lib  # noqa: F401  (fixture)


def test_copy_makes_a_new_file_and_keeps_the_original_and_its_record(lib: _Library) -> None:  # noqa: F811
    first = lib.track_ids[0]
    target = lib.music / "copies"
    target.mkdir()
    before = (lib.music / "sub" / "a.wav").read_bytes()
    result = lib.service.copy(first, target)
    assert result.status == "copied"
    assert (target / "a.wav").read_bytes() == before
    assert (lib.music / "sub" / "a.wav").read_bytes() == before
    assert lib.library.path_owner(lib.music / "sub" / "a.wav") == first
    assert not [path for path in target.iterdir() if path.suffix == ".part"]


def test_copy_refuses_a_name_already_there_and_leaves_both_files(lib: _Library) -> None:  # noqa: F811
    first = lib.track_ids[0]
    target = lib.music / "copies"
    target.mkdir()
    (target / "a.wav").write_bytes(b"other content")
    result = lib.service.copy(first, target)
    assert result.status == "conflict"
    assert (target / "a.wav").read_bytes() == b"other content"
    assert (lib.music / "sub" / "a.wav").is_file()
    # The folder of the track itself is a conflict too: the name is taken.
    assert lib.service.copy(first, lib.music / "sub").status == "conflict"


def test_copy_never_touches_a_part_file_it_did_not_make(lib: _Library) -> None:  # noqa: F811
    first = lib.track_ids[0]
    target = lib.music / "copies"
    target.mkdir()
    foreign = Path(target / ".a.wav.part")
    foreign.write_bytes(b"someone else")
    assert lib.service.copy(first, target).status in {"failed", "busy", "conflict"}
    assert foreign.read_bytes() == b"someone else"
    assert not (target / "a.wav").exists()
