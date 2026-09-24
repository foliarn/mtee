"""Artwork decoding is bounded and returns a neutral image for broken data."""

from __future__ import annotations

import struct
import wave
import zlib
from pathlib import Path

from mutagen.id3 import APIC
from mutagen.wave import WAVE

from mtee.services.artwork_service import ArtworkService


def _png_bytes() -> bytes:
    width, height = 300, 120
    pixels = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(name: bytes, payload: bytes) -> bytes:
        contents = name + payload
        checksum = zlib.crc32(contents) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + contents + struct.pack(">I", checksum)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )


def _tagged_wave(path: Path, image_data: bytes) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 80)
    audio = WAVE(path)
    audio.add_tags()
    assert audio.tags is not None
    audio.tags.add(
        APIC(
            encoding=3,
            mime="image/png",
            type=3,
            desc="cover",
            data=image_data,
        )
    )
    audio.save()


def test_embedded_artwork_is_resized_with_its_aspect_ratio(tmp_path: Path) -> None:
    path = tmp_path / "cover.wav"
    _tagged_wave(path, _png_bytes())

    image = ArtworkService().thumbnail(path, 64)

    assert not image.isNull()
    assert image.width() == 64
    assert image.height() == 26


def test_corrupt_embedded_artwork_returns_a_neutral_placeholder(tmp_path: Path) -> None:
    path = tmp_path / "broken-cover.wav"
    _tagged_wave(path, b"not an image")

    image = ArtworkService().thumbnail(path, 64)

    assert not image.isNull()
    assert (image.width(), image.height()) == (64, 64)
