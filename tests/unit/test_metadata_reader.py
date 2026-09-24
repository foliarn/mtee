"""Read-only metadata mapping from Mutagen-supported test audio."""

from __future__ import annotations

import wave
from pathlib import Path

from mutagen.id3 import TALB, TBPM, TCON, TDRC, TIT2, TKEY, TPE1
from mutagen.wave import WAVE

from mtee.services.metadata_reader import MetadataReader


def _tagged_wave(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 80)
    audio = WAVE(path)
    audio.add_tags()
    assert audio.tags is not None
    audio.tags.add(TIT2(encoding=3, text=["Café", "Café reprise"]))
    audio.tags.add(TPE1(encoding=3, text=["Zoë", "Guest"]))
    audio.tags.add(TALB(encoding=3, text="Live"))
    audio.tags.add(TCON(encoding=3, text=["House", "Disco"]))
    audio.tags.add(TBPM(encoding=3, text="124.5"))
    audio.tags.add(TKEY(encoding=3, text="8A"))
    audio.tags.add(TDRC(encoding=3, text="2024"))
    audio.save()


def test_reads_multivalue_tags_and_technical_information_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "Café.wav"
    _tagged_wave(path)
    before = path.read_bytes()

    snapshot = MetadataReader().read(path)

    assert snapshot.status == "readable"
    assert snapshot.title == ("Café", "Café reprise")
    assert snapshot.artist == ("Zoë", "Guest")
    assert snapshot.genre == ("House", "Disco")
    assert snapshot.bpm == ("124.5",)
    assert snapshot.key == ("8A",)
    assert snapshot.date == ("2024",)
    assert snapshot.technical.container == "WAV"
    assert snapshot.technical.duration_us is not None
    assert path.read_bytes() == before


def test_unrecognized_or_damaged_audio_has_an_explicit_status(tmp_path: Path) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"not a wave file")

    snapshot = MetadataReader().read(path)

    assert snapshot.status == "unreadable"
    assert snapshot.error
    assert snapshot.technical.size_bytes == len(b"not a wave file")


def test_missing_tags_stay_missing_instead_of_becoming_a_title(tmp_path: Path) -> None:
    path = tmp_path / "Filename only.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 8)

    snapshot = MetadataReader().read(path)

    assert snapshot.status == "readable"
    assert snapshot.title == ()
