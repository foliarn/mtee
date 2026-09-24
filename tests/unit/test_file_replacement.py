"""Verified publication preserves the old source and refuses linked files."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mtee.services.file_replacement import FileReplacement, FileReplacementError


def test_publish_keeps_a_recovery_copy_until_the_new_file_is_in_place(
    tmp_path: Path,
) -> None:
    source = tmp_path / "track.wav"
    temporary = tmp_path / ".track-edit.tmp.wav"
    backup = tmp_path / ".track-edit.bak"
    source.write_bytes(b"original audio")
    temporary.write_bytes(b"verified edited audio")

    FileReplacement().publish(temporary, source, backup)

    assert source.read_bytes() == b"verified edited audio"
    assert backup.read_bytes() == b"original audio"
    assert not temporary.exists()


def test_publish_rejects_source_with_multiple_hard_links(tmp_path: Path) -> None:
    source = tmp_path / "track.wav"
    linked = tmp_path / "second-name.wav"
    temporary = tmp_path / ".track-edit.tmp.wav"
    backup = tmp_path / ".track-edit.bak"
    source.write_bytes(b"original audio")
    temporary.write_bytes(b"verified edited audio")
    try:
        os.link(source, linked)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"This filesystem cannot create a hard link: {error}")

    with pytest.raises(FileReplacementError, match="hard links"):
        FileReplacement().publish(temporary, source, backup)

    assert source.read_bytes() == b"original audio"
    assert linked.read_bytes() == b"original audio"
    assert temporary.read_bytes() == b"verified edited audio"
