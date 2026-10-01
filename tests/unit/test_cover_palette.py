from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtGui import QColor, QImage, QPainter

from mtee.services.cover_palette import (
    CoverAccent,
    _srgb_to_oklab,
    accent_from_image,
    contrast_ratio,
)


def _solid(colour: str, size: int = 200) -> QImage:
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    return image


def _channels(text: str) -> tuple[float, float, float]:
    colour = QColor(text)
    return colour.redF(), colour.greenF(), colour.blueF()


def _accent(image: QImage) -> CoverAccent:
    accent = accent_from_image(image)
    assert accent is not None
    return accent


def _lab(text: str) -> np.ndarray:
    return _srgb_to_oklab(np.array([_channels(text)]))[0]


def _paint(image: QImage, rectangles: list[tuple[int, int, int, int, str]]) -> QImage:
    painter = QPainter(image)
    for x, y, width, height, colour in rectangles:
        painter.fillRect(x, y, width, height, QColor(colour))
    painter.end()
    return image


def _close(first: str, second: str, tolerance: float = 0.02) -> bool:
    return float(np.linalg.norm(_lab(first) - _lab(second))) < tolerance


def test_a_vivid_cover_gives_its_own_colour_and_a_darker_second_stop() -> None:
    accent = _accent(_solid("#E0245E"))
    assert _close(accent.base, "#E0245E")
    assert QColor(accent.dark).lightnessF() < QColor(accent.base).lightnessF()
    assert not accent.light and accent.foreground == "#FFFFFF"
    assert contrast_ratio(_channels(accent.foreground), _channels(accent.base)) >= 4.5


def test_a_white_cover_gives_a_white_card_with_dark_text() -> None:
    accent = _accent(_solid("#FFFFFF"))
    assert _close(accent.base, "#FFFFFF")
    assert accent.light and accent.foreground == "#0A0A0A"
    assert contrast_ratio(_channels(accent.foreground), _channels(accent.base)) >= 4.5
    assert contrast_ratio(_channels(accent.foreground), _channels(accent.dark)) >= 4.5


def test_a_black_cover_gives_a_near_black_card_with_white_text() -> None:
    accent = _accent(_solid("#000000"))
    assert QColor(accent.base).lightnessF() < 0.05
    assert not accent.light and accent.foreground == "#FFFFFF"


def test_a_grey_cover_gives_a_grey_card() -> None:
    accent = _accent(_solid("#808080"))
    assert _close(accent.base, "#808080")
    channels = QColor(accent.base)
    assert (
        abs(channels.red() - channels.green()) <= 1 and abs(channels.green() - channels.blue()) <= 1
    )


def test_a_pale_cover_keeps_its_colour_and_turns_the_text_dark() -> None:
    accent = _accent(_solid("#E8D77A"))
    assert _close(accent.base, "#E8D77A")
    assert accent.light and accent.foreground == "#0A0A0A"


def test_a_null_image_has_no_accent() -> None:
    assert accent_from_image(QImage()) is None


def test_mostly_white_with_a_little_red_stays_light() -> None:
    image = _solid("#FFFFFF")
    _paint(image, [(0, 0, 200, 40, "#E6E6E6"), (0, 160, 200, 20, "#E0102A")])  # 70 / 20 / 10 %
    accent = _accent(image)
    assert accent.light
    assert QColor(accent.base).lightnessF() > 0.85


def test_a_vivid_colour_beats_a_grey_of_similar_size() -> None:
    image = _solid("#8A8A8A")  # 45 % grey once the other bands are painted
    _paint(
        image, [(0, 0, 200, 80, "#D01030"), (0, 170, 200, 30, "#F4F4F4")]
    )  # 40 % red, 15 % white
    accent = _accent(image)
    assert _close(accent.base, "#D01030", 0.05)


def test_a_small_vivid_detail_does_not_beat_the_large_area_it_sits_on() -> None:
    image = _solid("#1E4FA8")
    ramp = [(0, y, 200, 1, QColor.fromHsv(218, 200, 140 + (y % 30)).name()) for y in range(200)]
    _paint(image, ramp)  # the large area is a ramp of blue shades
    _paint(image, [(0, 0, 40, 32, "#FFD400")])  # 3.2 % of saturated yellow
    accent = _accent(image)
    assert abs(QColor(accent.base).hue() - 218) <= 12  # still blue


def test_the_same_image_gives_the_same_result() -> None:
    image = _paint(_solid("#3A6B35"), [(0, 0, 120, 90, "#B84A1C"), (80, 100, 90, 90, "#EFE3C2")])
    assert _accent(image) == _accent(image)


def test_light_noise_barely_moves_the_colour() -> None:
    rng = np.random.default_rng(7)
    base = _paint(_solid("#3A6B35"), [(0, 0, 150, 120, "#B84A1C")])
    noisy = base.copy()
    for _ in range(2500):
        x, y = int(rng.integers(0, 200)), int(rng.integers(0, 200))
        colour = QColor(noisy.pixelColor(x, y))
        shift = int(rng.integers(-3, 4))
        colour.setRgb(
            max(0, min(255, colour.red() + shift)),
            max(0, min(255, colour.green() + shift)),
            max(0, min(255, colour.blue() + shift)),
        )
        noisy.setPixelColor(x, y, colour)
    assert float(np.linalg.norm(_lab(_accent(base).base) - _lab(_accent(noisy).base))) < 0.05


def test_contrast_ratio_is_the_wcag_ratio() -> None:
    assert contrast_ratio((0, 0, 0), (1, 1, 1)) == pytest.approx(21.0)
    assert contrast_ratio((1, 1, 1), (1, 1, 1)) == pytest.approx(1.0)
