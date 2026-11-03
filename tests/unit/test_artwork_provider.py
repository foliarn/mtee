"""Artwork requests use requested dimensions while respecting source bounds."""

from __future__ import annotations

import struct
import threading
import time
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


class _SlowLibrary:
    """A library whose read of a track stays in progress until the test lets it end."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.finished = False

    def artwork_source(self, track_id: str) -> None:
        self.entered.set()
        self.release.wait(5)
        self.finished = True
        return None


class _ClosedLibrary:
    """A library that must not be read: the database behind it is closed."""

    def artwork_source(self, track_id: str) -> None:
        raise AssertionError("the library was read after the provider was closed")


def test_close_waits_for_a_library_read_in_progress() -> None:
    track_id = "01234567-89ab-cdef-0123-456789abcdef"
    library = _SlowLibrary()
    provider = ArtworkProvider(library)  # type: ignore[arg-type]
    reader = threading.Thread(
        target=provider.requestImage, args=(f"{track_id}/0", QSize(), QSize())
    )
    reader.start()
    assert library.entered.wait(5)

    closer = threading.Thread(target=provider.close)
    closer.start()
    time.sleep(0.2)
    # The read still runs, so close must still wait for it.
    assert closer.is_alive()
    library.release.set()
    closer.join(5)
    reader.join(5)

    assert not closer.is_alive()
    assert library.finished


def test_a_request_after_close_gives_a_placeholder_without_the_library() -> None:
    track_id = "01234567-89ab-cdef-0123-456789abcdef"
    provider = ArtworkProvider(_ClosedLibrary())  # type: ignore[arg-type]
    provider.close()

    requested = QSize()
    image = provider.requestImage(f"{track_id}/0/64", requested, QSize())

    assert not image.isNull()
    assert (requested.width(), requested.height()) == (image.width(), image.height())
