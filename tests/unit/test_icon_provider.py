"""Tinted icons served to QML."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor

from mtee.assets import icons_dir
from mtee.models.icon_provider import IconProvider, parse_icon_id


def test_icon_ids_carry_a_name_and_a_colour() -> None:
    name, colour = parse_icon_id("play/c6ff1a")
    assert name == "play"
    assert colour == QColor("#C6FF1A")

    _, translucent = parse_icon_id("play/80ffffff")
    assert translucent.alpha() == 0x80


def test_a_path_is_never_accepted_as_an_icon_name() -> None:
    with pytest.raises(ValueError):
        parse_icon_id("../secret/ffffff")


def test_every_icon_renders_in_the_requested_colour(qapp) -> None:
    provider = IconProvider()
    names = sorted(path.stem for path in icons_dir().glob("*.svg"))
    assert "play" in names and "settings" in names

    for name in names:
        image = provider.requestImage(f"{name}/c6ff1a", QSize(), QSize(48, 48))
        assert image.size() == QSize(48, 48)
        painted = [
            image.pixelColor(x, y)
            for x in range(0, 48, 2)
            for y in range(0, 48, 2)
            if image.pixelColor(x, y).alpha() == 255
        ]
        assert painted, name
        assert all(abs(c.green() - 0xFF) < 8 and c.blue() < 60 for c in painted), name


def test_an_unknown_icon_is_transparent(qapp) -> None:
    image = IconProvider().requestImage("missing/ffffff", QSize(), QSize(16, 16))
    assert image.pixelColor(8, 8).alpha() == 0
