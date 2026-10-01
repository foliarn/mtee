"""Accent colour of a cover, for the card of the fullscreen player (plans 100 and 101).

A pure function on a ``QImage``: it returns the colour that really covers the cover. White,
grey and black covers give a white, grey or black card; nothing is darkened or excluded.
The card text turns dark when the card is light.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

__all__ = ["CoverAccent", "accent_from_image", "contrast_ratio"]

_SIZE = 64
_L_STEP = 0.08
_AB_STEP = 0.03
_MERGE_DISTANCE = 0.09
_CHROMA_BONUS = 0.35
_CHROMA_FULL = 0.12
_DARK_FACTOR = 0.78
_LIGHT_TEXT = "#FFFFFF"
_DARK_TEXT = "#0A0A0A"


@dataclass(frozen=True, slots=True)
class CoverAccent:
    """Card colours: ``base`` on top, ``dark`` at the bottom, and the colour of the text.

    ``light`` is true when the card is light and so its text, ``foreground``, is dark.
    """

    base: str
    dark: str
    foreground: str
    light: bool


def contrast_ratio(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    """Return the WCAG contrast ratio of two sRGB colours (channels in ``0..1``)."""
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def accent_from_image(image: QImage) -> CoverAccent | None:
    """Return the dominant colour of ``image``, or ``None`` for a null image.

    1. The image is reduced to 64x64 and every pixel goes from sRGB to OKLab (L in
    ``[0, 1]``). 2. A 3D histogram counts the pixels: L in steps of 0.08, a and b in steps
    of 0.03. 3. The bins, most populated first, are merged greedily: a bin joins the first
    group whose weighted mean is closer than 0.09 (OKLab distance), else it opens a group.
    This gathers the shades of one large area. 4. A group scores ``share x (1 + 0.35 x
    min(1, chroma / 0.12))``: size dominates and a vivid colour only wins between areas of
    comparable size. 5. ``base`` is the mean of the best group, ``dark`` the same colour
    with ``L x 0.78``. 6. The text is white or near-black, whichever keeps the better
    worst-case contrast with ``base`` and ``dark``.
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
    lab = _srgb_to_oklab(pixels)

    cells = np.stack(
        [
            np.floor(lab[:, 0] / _L_STEP),
            np.floor(lab[:, 1] / _AB_STEP),
            np.floor(lab[:, 2] / _AB_STEP),
        ],
        axis=1,
    ).astype(np.int64)
    unique, inverse, counts = np.unique(cells, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    sums = np.zeros((len(unique), 3))
    np.add.at(sums, inverse, lab)
    means = sums / counts[:, None]
    order = np.lexsort((np.arange(len(unique)), -counts))

    group_sum: list[np.ndarray] = []
    group_count: list[int] = []
    for cell in order:
        weight = int(counts[cell])
        for index, total in enumerate(group_sum):
            centre = total / group_count[index]
            if float(np.linalg.norm(means[cell] - centre)) < _MERGE_DISTANCE:
                group_sum[index] = total + means[cell] * weight
                group_count[index] += weight
                break
        else:
            group_sum.append(means[cell] * weight)
            group_count.append(weight)

    best, best_score = 0, -1.0
    for index, total in enumerate(group_sum):
        centre = total / group_count[index]
        chroma = float(np.hypot(centre[1], centre[2]))
        score = (
            group_count[index]
            / pixels.shape[0]
            * (1.0 + _CHROMA_BONUS * min(1.0, chroma / _CHROMA_FULL))
        )
        if score > best_score:
            best, best_score = index, score
    centre = group_sum[best] / group_count[best]
    base = _oklab_to_srgb(centre)
    dark = _oklab_to_srgb(np.array([centre[0] * _DARK_FACTOR, centre[1], centre[2]]))
    light_text = _channels(_LIGHT_TEXT)
    dark_text = _channels(_DARK_TEXT)
    on_light = min(contrast_ratio(light_text, base), contrast_ratio(light_text, dark))
    on_dark = min(contrast_ratio(dark_text, base), contrast_ratio(dark_text, dark))
    card_is_light = on_dark > on_light
    return CoverAccent(
        base=_hex(base),
        dark=_hex(dark),
        foreground=_DARK_TEXT if card_is_light else _LIGHT_TEXT,
        light=card_is_light,
    )


def _luminance(colour: tuple[float, float, float]) -> float:
    red, green, blue = (
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in colour
    )
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _to_linear(values: np.ndarray) -> np.ndarray:
    return np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)


def _from_linear(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, 0.0, 1.0)
    return np.where(clipped <= 0.0031308, clipped * 12.92, 1.055 * clipped ** (1 / 2.4) - 0.055)


def _srgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    linear = _to_linear(rgb)
    red, green, blue = linear[:, 0], linear[:, 1], linear[:, 2]
    long = np.cbrt(0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue)
    medium = np.cbrt(0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue)
    short = np.cbrt(0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue)
    return np.stack(
        [
            0.2104542553 * long + 0.7936177850 * medium - 0.0040720468 * short,
            1.9779984951 * long - 2.4285922050 * medium + 0.4505937099 * short,
            0.0259040371 * long + 0.7827717662 * medium - 0.8086757660 * short,
        ],
        axis=1,
    )


def _oklab_to_srgb(lab: np.ndarray) -> tuple[float, float, float]:
    lightness, a, b = (float(value) for value in lab)
    long = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    medium = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    short = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    linear = np.array(
        [
            4.0767416621 * long - 3.3077115913 * medium + 0.2309699292 * short,
            -1.2684380046 * long + 2.6097574011 * medium - 0.3413193965 * short,
            -0.0041960863 * long - 0.7034186147 * medium + 1.7076147010 * short,
        ]
    )
    red, green, blue = (float(value) for value in _from_linear(linear))
    return red, green, blue


def _channels(text: str) -> tuple[float, float, float]:
    return tuple(int(text[index : index + 2], 16) / 255 for index in (1, 3, 5))  # type: ignore[return-value]


def _hex(colour: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, channel)) * 255):02X}" for channel in colour)
