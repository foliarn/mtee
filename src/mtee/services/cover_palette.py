"""Accent colour of a cover, for the card of the fullscreen player (plan 100).

A pure function on a ``QImage``: it keeps the most vivid of the frequent colours, so that
a mostly dark or grey cover with one strong colour still gives that colour, and darkens it
until white text on it reads well.
"""

from __future__ import annotations

import colorsys

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

__all__ = ["accent_from_image", "contrast_with_white"]

_SIZE = 64
_HUE_BINS = 36
_LEVEL_BINS = 4
_MIN_SATURATION = 0.25
_MIN_VALUE = 0.20
_MAX_VALUE = 0.95
_MIN_COVERAGE = 0.05
_MIN_CONTRAST = 4.5
_VALUE_STEP = 0.05
_DARK_VALUE_FACTOR = 0.55


def contrast_with_white(red: float, green: float, blue: float) -> float:
    """Return the WCAG contrast ratio of an sRGB colour (channels in ``0..1``) with white."""

    def linear(channel: float) -> float:
        if channel <= 0.03928:
            return channel / 12.92
        return float(((channel + 0.055) / 1.055) ** 2.4)

    luminance = 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
    return 1.05 / (luminance + 0.05)


def accent_from_image(image: QImage) -> tuple[str, str] | None:
    """Return ``(base, dark)`` as ``#RRGGBB``, or ``None`` when no colour stands out.

    1. The image is reduced to 64x64. 2. Each pixel is quantised in HSV: 36 hues, 4
    saturations, 4 values. 3. Grey pixels (saturation below 0.25) and extreme ones
    (value outside ``[0.20, 0.95]``) are ignored. 4. The bin maximising ``pixel count x
    mean saturation`` wins; when the kept pixels are fewer than 5 % of the image there is
    no accent. 5. ``base`` is the mean colour of that bin, darkened by steps of 5 % of
    value until its contrast with white is at least 4.5:1. 6. ``dark`` is ``base`` with its
    value multiplied by 0.55.
    """
    if image.isNull():
        return None
    reduced = image.scaled(
        _SIZE,
        _SIZE,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    ).convertToFormat(QImage.Format.Format_RGB888)
    stride = reduced.bytesPerLine()
    raw = np.frombuffer(reduced.constBits(), dtype=np.uint8, count=stride * _SIZE)
    pixels = raw.reshape(_SIZE, stride)[:, : _SIZE * 3].reshape(-1, 3).astype(np.float64) / 255.0
    high = pixels.max(axis=1)
    spread = high - pixels.min(axis=1)
    saturation = np.divide(spread, high, out=np.zeros_like(high), where=high > 0)
    keep = (saturation >= _MIN_SATURATION) & (high >= _MIN_VALUE) & (high <= _MAX_VALUE)
    if keep.sum() < _MIN_COVERAGE * pixels.shape[0]:
        return None
    colours, spread = pixels[keep], spread[keep]
    high, saturation = high[keep], saturation[keep]
    red, green, blue = colours[:, 0], colours[:, 1], colours[:, 2]
    safe = np.where(spread == 0, 1.0, spread)
    hue = np.where(
        high == red,
        ((green - blue) / safe) % 6,
        np.where(high == green, (blue - red) / safe + 2, (red - green) / safe + 4),
    )
    hue_bin = np.floor(hue / 6 * _HUE_BINS).astype(int) % _HUE_BINS
    saturation_bin = np.minimum(np.floor(saturation * _LEVEL_BINS), _LEVEL_BINS - 1).astype(int)
    value_bin = np.minimum(np.floor(high * _LEVEL_BINS), _LEVEL_BINS - 1).astype(int)
    key = (hue_bin * _LEVEL_BINS + saturation_bin) * _LEVEL_BINS + value_bin
    best, best_score = -1, 0.0
    for candidate in np.unique(key):
        members = key == candidate
        score = float(members.sum() * saturation[members].mean())
        if score > best_score:
            best, best_score = int(candidate), score
    mean = colours[key == best].mean(axis=0)
    hue_value, saturation_value, value = colorsys.rgb_to_hsv(*(float(c) for c in mean))
    colour = (float(mean[0]), float(mean[1]), float(mean[2]))
    while contrast_with_white(*colour) < _MIN_CONTRAST and value > _VALUE_STEP:
        value -= _VALUE_STEP
        colour = colorsys.hsv_to_rgb(hue_value, saturation_value, max(0.0, value))
    dark = colorsys.hsv_to_rgb(hue_value, saturation_value, value * _DARK_VALUE_FACTOR)
    return _hex(colour), _hex(dark)


def _hex(colour: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, channel)) * 255):02X}" for channel in colour)
