"""Hit testing of the frameless window, independent of the platform."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QGuiApplication

from mtee.platform.windows_frame import (
    HTBOTTOMRIGHT,
    HTCAPTION,
    HTCLIENT,
    HTLEFT,
    HTMAXBUTTON,
    HTTOP,
    HTTOPLEFT,
    HitRegions,
    hit_test,
)

REGIONS = HitRegions(title_bar_height=32, caption_left=240, button_width=46, buttons_width=138)
WIDTH, HEIGHT = 1440.0, 900.0


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        (2, 2, HTTOPLEFT),
        (1438, 898, HTBOTTOMRIGHT),
        (2, 400, HTLEFT),
        (700, 2, HTTOP),
        (100, 16, HTCLIENT),  # logo and menus
        (700, 16, HTCAPTION),
        (1440 - 46 - 20, 16, HTMAXBUTTON),
        (1440 - 20, 16, HTCLIENT),  # close
        (1440 - 138 + 10, 16, HTCLIENT),  # minimize
        (700, 400, HTCLIENT),
    ],
)
def test_hit_test_of_a_normal_window(x: float, y: float, expected: int) -> None:
    assert hit_test(x, y, WIDTH, HEIGHT, regions=REGIONS, maximized=False) == expected


def test_a_maximized_window_has_no_resize_edges() -> None:
    assert hit_test(2, 16, WIDTH, HEIGHT, regions=REGIONS, maximized=True) == HTCLIENT
    assert hit_test(700, 1, WIDTH, HEIGHT, regions=REGIONS, maximized=True) == HTCAPTION


def test_detach_is_safe_when_no_native_filter_was_installed(qapp: QGuiApplication) -> None:
    from mtee.platform.windows_frame import WindowFrame

    frame = WindowFrame()
    frame.detach()
    frame.detach()

    assert not frame.native
