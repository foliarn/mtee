"""Decode bounded images and save an app-owned cover, independent of the original."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QImageReader


def copy_cover(source: Path | bytes, directory: Path) -> str:
    if isinstance(source, bytes):
        if len(source) > 5 * 1024 * 1024:
            raise ValueError("The imported cover exceeds 5 MB.")
        # A reader keeps a raw pointer to its device: the buffer stays open and alive until
        # the reader has finished, which the try block guarantees.
        buffer = QBuffer()
        buffer.setData(source)
        if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
            raise ValueError("This image cannot be decoded.")
        try:
            image = _read_cover(QImageReader(buffer))
        finally:
            buffer.close()
    else:
        if not source.is_file() or source.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Choose an image smaller than 20 MB.")
        image = _read_cover(QImageReader(str(source)))
    image = image.scaled(
        1024, 1024, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    directory.mkdir(parents=True, exist_ok=True)
    reference = str(uuid4()) + ".png"
    if not image.save(str(directory / reference)):
        raise OSError("The playlist cover could not be saved.")
    return reference


def _read_cover(reader: QImageReader) -> QImage:
    """Read the cover of ``reader`` once its size is within the limits."""
    size = reader.size()
    if (
        size.width() <= 0
        or size.height() <= 0
        or size.width() > 8192
        or size.height() > 8192
        or size.width() * size.height() > 16_777_216
    ):
        raise ValueError("Choose an image up to 8192 pixels per side and 16 megapixels.")
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError("This image cannot be decoded.")
    return image
