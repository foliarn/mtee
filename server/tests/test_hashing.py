"""File hashes, the audio-stream hash and the tag reader."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from mutagen import File as MutagenFile  # pyright: ignore[reportMissingTypeStubs]

from helpers import make_audio
from mtee_remote.library import hashing


def test_file_sha256_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    payload = b"abc" * 1_000_000  # more than one 1 MiB chunk
    path.write_bytes(payload)
    assert hashing.file_sha256(path) == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a", "wav", "ogg", "opus", "aiff"])
def test_audio_hash_exists_for_every_format(tmp_path: Path, fmt: str) -> None:
    value = hashing.audio_hash(make_audio(tmp_path / f"a.{fmt}", fmt))
    assert value is not None
    assert len(value) == 64
    assert value == value.lower()


@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a"])
def test_audio_hash_survives_a_tag_edit(tmp_path: Path, fmt: str) -> None:
    original = make_audio(tmp_path / f"a.{fmt}", fmt, title="Before")
    copy = tmp_path / f"copy.{fmt}"
    shutil.copyfile(original, copy)
    before = hashing.audio_hash(copy)
    audio = MutagenFile(copy, easy=True)
    assert audio is not None
    audio["title"] = ["After the edit, a longer title"]
    audio.save()
    assert hashing.file_sha256(copy) != hashing.file_sha256(original)
    assert hashing.audio_hash(copy) == before == hashing.audio_hash(original)


def test_audio_hash_is_none_for_a_non_audio_file(tmp_path: Path) -> None:
    path = tmp_path / "notes.flac"
    path.write_text("this is not audio")
    assert hashing.audio_hash(path) is None
    assert hashing.audio_hash(tmp_path / "missing.flac") is None


def test_audio_hash_is_none_without_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = make_audio(tmp_path / "a.flac", "flac")
    monkeypatch.setenv("MTEE_REMOTE_FFMPEG", str(tmp_path / "no-such-ffmpeg"))
    assert hashing.audio_hash(path) is None


def test_read_metadata_gives_the_title_and_a_duration(tmp_path: Path) -> None:
    path = make_audio(tmp_path / "a.flac", "flac", seconds=1.0, title="Hello")
    text, duration = hashing.read_metadata(path)
    assert text is not None
    data = json.loads(text)
    assert data["title"] == ["Hello"]
    assert duration == pytest.approx(1_000_000, abs=100_000)
    assert data["technical"]["duration_us"] == duration


def test_read_metadata_never_raises(tmp_path: Path) -> None:
    junk = tmp_path / "junk.mp3"
    junk.write_text("not audio")
    text, duration = hashing.read_metadata(junk)
    assert duration is None
    assert text is None or json.loads(text)["status"] == "unreadable"
    assert hashing.read_metadata(tmp_path / "missing.mp3")[1] is None
