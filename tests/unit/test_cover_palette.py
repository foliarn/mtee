from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QImage, QPainter

from mtee.services.cover_palette import accent_from_image, contrast_with_white


def _solid(colour: str, size: int = 200) -> QImage:
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    return image


def _channels(text: str) -> tuple[float, float, float]:
    colour = QColor(text)
    return colour.redF(), colour.greenF(), colour.blueF()


def _value(text: str) -> float:
    return QColor(text).valueF()


def test_a_vivid_cover_gives_its_own_colour_and_a_darker_second_stop() -> None:
    accent = accent_from_image(_solid("#E0245E"))
    assert accent is not None
    base, dark = accent
    assert base == "#E0245E"  # already readable under white: kept as is
    assert contrast_with_white(*_channels(base)) >= 4.5
    assert _value(dark) < _value(base)
    assert _value(dark) == pytest.approx(_value(base) * 0.55, abs=0.02)


def test_a_pale_cover_is_darkened_until_white_text_is_readable() -> None:
    accent = accent_from_image(_solid("#E8D77A"))
    assert accent is not None
    base, dark = accent
    assert contrast_with_white(*_channels("#E8D77A")) < 4.5  # the raw colour was too light
    assert contrast_with_white(*_channels(base)) >= 4.5
    assert QColor(base).hue() == pytest.approx(QColor("#E8D77A").hue(), abs=3)  # same hue
    assert _value(base) < _value("#E8D77A")
    assert _value(dark) < _value(base)


def test_a_grey_cover_has_no_accent() -> None:
    assert accent_from_image(_solid("#808080")) is None
    assert accent_from_image(_solid("#000000")) is None
    assert accent_from_image(_solid("#FFFFFF")) is None


def test_a_null_image_has_no_accent() -> None:
    assert accent_from_image(QImage()) is None


def test_the_most_vivid_of_the_frequent_colours_wins_over_a_dull_majority() -> None:
    image = _solid("#6E6E78")  # a dull grey-blue covering most of the cover
    painter = QPainter(image)
    painter.fillRect(0, 0, 200, 70, QColor("#1FA34A"))  # a vivid green band, 35 %
    painter.end()
    accent = accent_from_image(image)
    assert accent is not None
    assert QColor(accent[0]).hue() == pytest.approx(QColor("#1FA34A").hue(), abs=8)


def test_a_few_stray_vivid_pixels_are_not_enough() -> None:
    image = _solid("#808080")
    painter = QPainter(image)
    painter.fillRect(0, 0, 8, 8, QColor("#FF0000"))  # about 0.2 % of the image
    painter.end()
    assert accent_from_image(image) is None


def test_contrast_with_white_is_the_wcag_ratio() -> None:
    assert contrast_with_white(0, 0, 0) == pytest.approx(21.0)
    assert contrast_with_white(1, 1, 1) == pytest.approx(1.0)
