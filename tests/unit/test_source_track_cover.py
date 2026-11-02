"""The cover of a track without a file: image bytes from a plugin become a thumbnail."""

from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage

from mtee.services.artwork_service import MAX_ARTWORK_BYTES, ArtworkService


def _png() -> bytes:
    picture = QImage(8, 8, QImage.Format.Format_RGB32)
    picture.fill(QColor(200, 30, 30))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert cast(Any, picture).save(buffer, "PNG")  # the stubs ask for bytes, Qt takes text
    return bytes(cast(Any, buffer.data()))


def test_image_bytes_are_decoded_to_a_thumbnail(qapp) -> None:
    image = ArtworkService().thumbnail_from_bytes(_png(), 64, "seed")
    assert (image.width(), image.height()) == (8, 8)


def test_missing_oversized_or_broken_bytes_give_the_placeholder(qapp) -> None:
    service = ArtworkService()
    for data in (None, b"", b"not an image", b"x" * (MAX_ARTWORK_BYTES + 1)):
        image = service.thumbnail_from_bytes(data, 64, "seed")
        assert image.width() == 64
