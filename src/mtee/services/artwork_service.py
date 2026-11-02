"""Extract and decode embedded artwork without blocking the Qt interface."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.flac import Picture
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPen

__all__ = ["MAX_ARTWORK_BYTES", "ArtworkService", "placeholder_image"]

MAX_ARTWORK_BYTES = 20 * 1024 * 1024
MAX_ARTWORK_PIXELS = 100_000_000


class ArtworkService:
    """Read embedded images, reject oversized data and make bounded thumbnails."""

    def image_bytes(self, path: Path | str) -> bytes | None:
        audio = MutagenFile(path, easy=False)
        if audio is None or audio.tags is None:
            return None
        tags = audio.tags
        images: list[bytes] = []
        for tag in tags.values():
            if hasattr(tag, "data") and isinstance(tag.data, bytes):
                images.append(tag.data)
        pictures = getattr(audio, "pictures", ())
        images.extend(picture.data for picture in pictures if getattr(picture, "data", None))
        for key in ("covr", "APIC", "metadata_block_picture", "coverart"):
            try:
                values = tags.get(key, ())
            except (AttributeError, TypeError):
                continue
            for value in values if isinstance(values, (list, tuple)) else (values,):
                data = _image_data(value)
                if data and len(data) <= MAX_ARTWORK_BYTES:
                    return data
        return next((data for data in images if 0 < len(data) <= MAX_ARTWORK_BYTES), None)

    def thumbnail(self, path: Path | str, size: int) -> QImage:
        if size < 1 or size > 1024:
            raise ValueError("thumbnail size must be between 1 and 1024 pixels")
        return self.thumbnail_from_bytes(self.image_bytes(path), size, str(path))

    def thumbnail_from_bytes(self, data: bytes | None, size: int, seed: str) -> QImage:
        """Decode image ``data`` (read from a file, or given by a plugin) to a thumbnail.

        ``seed`` picks the placeholder when there is no usable image.
        """
        if size < 1 or size > 1024:
            raise ValueError("thumbnail size must be between 1 and 1024 pixels")
        if not data or len(data) > MAX_ARTWORK_BYTES:
            return placeholder_image(seed, size)
        # The byte array and the buffer stay referenced until the reader is gone: a reader keeps
        # a raw pointer to its device, and the buffer must outlive the reader's last call.
        payload = QByteArray(data)
        buffer = QBuffer()
        buffer.setData(payload)
        if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
            return placeholder_image(seed, size)
        try:
            image = _decode_scaled(QImageReader(buffer), size)
        finally:
            buffer.close()
        return image if image is not None and not image.isNull() else placeholder_image(seed, size)


def _decode_scaled(reader: QImageReader, size: int) -> QImage | None:
    """Read the image of ``reader`` scaled to fit ``size``; ``None`` when its size is unusable."""
    dimensions = reader.size()
    if (
        not dimensions.isValid()
        or dimensions.width() <= 0
        or dimensions.height() <= 0
        or dimensions.width() * dimensions.height() > MAX_ARTWORK_PIXELS
    ):
        return None
    scale = min(size / dimensions.width(), size / dimensions.height(), 1.0)
    reader.setScaledSize(
        QSize(round(dimensions.width() * scale), round(dimensions.height() * scale))
    )
    return reader.read()


def _image_data(value: object) -> bytes | None:
    data = getattr(value, "data", None)
    if isinstance(data, bytes):
        return data
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        try:
            return base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            return None
    if isinstance(value, Picture):
        return value.data
    return None


def placeholder_image(seed: str, size: int) -> QImage:
    """Draw a consistent neutral cover placeholder from a stable path seed."""
    colors = ((30, 44, 40), (44, 35, 53), (33, 43, 54), (51, 39, 43))
    color = colors[sum(seed.encode("utf-8")) % len(colors)]
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(*color))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(198, 255, 26), max(1, size // 28)))
    margin = size // 4
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    painter.end()
    return image
