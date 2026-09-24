"""Explicit metadata edits reject malformed or ambiguous operations."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest
from mutagen.id3 import TIT2
from mutagen.wave import WAVE

from mtee.domain.metadata_edit import MetadataPatch
from mtee.services.metadata_adapters.id3 import Id3WaveAdapter


def test_patch_distinguishes_unchanged_values_from_explicit_removal() -> None:
    patch = MetadataPatch.from_mapping({"title": "New title", "comment": None})

    assert patch.as_dict() == {"title": "New title", "comment": None}
    with pytest.raises(ValueError, match="at least one"):
        MetadataPatch(())
    with pytest.raises(ValueError, match="more than once"):
        MetadataPatch((("title", "One"), ("title", "Two")))
    with pytest.raises(ValueError, match="Invalid value"):
        MetadataPatch.one("title", "bad\x00title")


def test_id3_wave_capabilities_disable_multivalue_and_old_id3_versions(tmp_path: Path) -> None:
    path = tmp_path / "multiple.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 80)
    audio = WAVE(path)
    audio.add_tags()
    assert audio.tags is not None
    audio.tags.add(TIT2(encoding=3, text=["One", "Two"]))
    audio.save(v2_version=4)

    capabilities = Id3WaveAdapter().capabilities(path)

    assert not capabilities["title"][0]
    assert capabilities["album"][0]

    path2 = tmp_path / "old-version.wav"
    with wave.open(str(path2), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 80)
    old = WAVE(path2)
    old.add_tags()
    assert old.tags is not None
    old.tags.add(TIT2(encoding=3, text=["Old version"]))
    old.save(v2_version=3)

    version_capabilities = Id3WaveAdapter().capabilities(path2)

    assert all(not editable for editable, _reason in version_capabilities.values())

    path3 = tmp_path / "non-pcm.wav"
    path3.write_bytes(path.read_bytes())
    data = bytearray(path3.read_bytes())
    data[20:22] = struct.pack("<H", 3)  # IEEE float WAVE format, not the PCM fixture.
    path3.write_bytes(data)
    encoding_capabilities = Id3WaveAdapter().capabilities(path3)
    assert all(not editable for editable, _reason in encoding_capabilities.values())
