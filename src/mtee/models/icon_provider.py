"""Tinted interface icons for QML.

QML asks for ``image://icon/<name>/<rrggbb>`` or ``<aarrggbb>``. The provider
replaces ``currentColor`` in the SVG template with that colour and renders it at
the requested size, so one file serves every state of a control.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQml import QQmlImageProviderBase
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

from mtee.assets import icons_dir

__all__ = ["ICON_PROVIDER_ID", "IconProvider", "parse_icon_id"]

ICON_PROVIDER_ID = "icon"
_DEFAULT_SIZE = 24
_NAME = re.compile(r"^[a-z0-9-]+$")
_COLOUR = re.compile(r"^(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def parse_icon_id(icon_id: str) -> tuple[str, QColor]:
    """Split ``name/colour`` and reject anything that is not a plain icon name.

    The name never becomes a path component other than ``<name>.svg`` inside the
    icon directory, so a QML typo cannot reach another file.
    """
    name, _, colour = icon_id.partition("/")
    colour = colour.split("?", 1)[0]
    if not _NAME.match(name):
        raise ValueError(f"Invalid icon name: {name!r}")
    if not _COLOUR.match(colour):
        return name, QColor("#FFFFFF")
    if len(colour) == 8:
        alpha, rgb = int(colour[:2], 16), colour[2:]
        result = QColor(f"#{rgb}")
        result.setAlpha(alpha)
        return name, result
    return name, QColor(f"#{colour}")


class IconProvider(QQuickImageProvider):
    """Render the SVG icons of ``resources/icons`` in the requested colour."""

    def __init__(self, directory: Path | None = None) -> None:
        super().__init__(QQmlImageProviderBase.ImageType.Image)
        self._directory = directory or icons_dir()
        self._templates: dict[str, str] = {}

    def requestImage(self, icon_id: str, size: QSize, requested_size: QSize) -> QImage:
        width = requested_size.width() if requested_size.width() > 0 else _DEFAULT_SIZE
        height = requested_size.height() if requested_size.height() > 0 else width
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        try:
            name, colour = parse_icon_id(icon_id)
        except ValueError:
            return image
        template = self._template(name)
        if template is None:
            return image
        svg = template.replace("currentColor", colour.name(QColor.NameFormat.HexRgb))
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(colour.alphaF())
        renderer.render(painter, QRectF(0, 0, width, height))
        painter.end()
        return image

    def _template(self, name: str) -> str | None:
        if name not in self._templates:
            path = self._directory / f"{name}.svg"
            if not path.is_file():
                return None
            self._templates[name] = path.read_text(encoding="utf-8")
        return self._templates[name]
