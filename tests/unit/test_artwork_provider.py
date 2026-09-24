"""Artwork requests use requested dimensions while respecting source bounds."""

from __future__ import annotations

import struct
import wave
import zlib
from pathlib import Path

from mutagen.id3 import APIC
from mutagen.wave import WAVE
from PySide6.QtCore import QSize

from mtee.domain.tracks import SourceRevision
from mtee.models.artwork_provider import ArtworkProvider


def _png_bytes(width: int = 300, height: int = 120) -> bytes:
    pixels = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(name: bytes, payload: bytes) -> bytes:
        contents = name + payload
        return (
            struct.pack(">I", len(payload))
            + contents
            + struct.pack(">I", zlib.crc32(contents) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )


class _ArtworkLibrary:
    def __init__(self, path: Path, track_id: str) -> None:
        self.path = path
        self.track_id = track_id
        self.revision = SourceRevision.observe(path)

    def artwork_source(self, track_id: str):
        return (self.path, self.revision) if track_id == self.track_id else None


def test_provider_returns_requested_size_and_does_not_upscale_source(tmp_path: Path) -> None:
    path = tmp_path / "cover.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 80)
    audio = WAVE(path)
    audio.add_tags()
    assert audio.tags is not None
    audio.tags.add(APIC(encoding=3, mime="image/png", type=3, desc="front", data=_png_bytes()))
    audio.save()
    track_id = "01234567-89ab-cdef-0123-456789abcdef"
    provider = ArtworkProvider(_ArtworkLibrary(path, track_id))  # type: ignore[arg-type]

    requested = QSize()
    image = provider.requestImage(f"{track_id}/0/256", requested, QSize(256, 256))

    assert (image.width(), image.height()) == (256, 102)
    assert (requested.width(), requested.height()) == (256, 102)
