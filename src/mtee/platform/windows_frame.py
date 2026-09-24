"""Frameless window chrome drawn by QML, with the native behaviour of Windows.

QML draws the title bar and the window buttons. On Windows this module gives
the borderless window back what a system frame provides: resizing from the
edges, dragging and Aero Snap from the caption, the Snap Layouts flyout over
Maximize, and square corners on Windows 11. QML never calls a system API; it
only declares the geometry of its title bar through ``WindowFrame``.

On another platform, or with the offscreen platform of the tests, the object
stays inert and QML falls back to ``startSystemMove`` and ``startSystemResize``.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import (
    Property,
    QAbstractNativeEventFilter,
    QByteArray,
    QCoreApplication,
    QObject,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication, QWindow

__all__ = ["HitRegions", "WindowFrame", "hit_test"]

# Hit-test results of WM_NCHITTEST.
HTCLIENT = 1
HTCAPTION = 2
HTMAXBUTTON = 9
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

_WM_MOUSEMOVE = 0x0200
_WM_NCCALCSIZE = 0x0083
_WM_NCHITTEST = 0x0084
_WM_NCMOUSEMOVE = 0x00A0
_WM_NCLBUTTONDOWN = 0x00A1
_WM_NCLBUTTONUP = 0x00A2
_WM_NCLBUTTONDBLCLK = 0x00A3
_WM_NCMOUSELEAVE = 0x02A2

_GWL_STYLE = -16
_WS_CAPTION = 0x00C00000
_WS_THICKFRAME = 0x00040000
_WS_MINIMIZEBOX = 0x00020000
_WS_MAXIMIZEBOX = 0x00010000
_WS_SYSMENU = 0x00080000
# SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
_SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020
_SM_CXSIZEFRAME = 32
_SM_CYSIZEFRAME = 33
_SM_CXPADDEDBORDER = 92
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_DONOTROUND = 1

_RESIZE_BORDER = 6  # logical pixels


@dataclass(frozen=True, slots=True)
class HitRegions:
    """Title bar geometry declared by QML, in logical pixels.

    ``caption_left`` is where the draggable caption starts (after the logo and
    the menus). The window buttons occupy ``buttons_width`` at the right; the
    maximize button is the middle one of ``button_width``.
    """

    title_bar_height: int = 32
    caption_left: int = 0
    button_width: int = 46
    buttons_width: int = 138


def hit_test(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    regions: HitRegions,
    maximized: bool,
    border: float = _RESIZE_BORDER,
) -> int:
    """Return the WM_NCHITTEST code of a point in logical window coordinates."""
    if not maximized:
        left = x < border
        right = x >= width - border
        top = y < border
        bottom = y >= height - border
        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
    if y >= regions.title_bar_height:
        return HTCLIENT
    buttons_left = width - regions.buttons_width
    if x >= buttons_left:
        maximize_left = width - 2 * regions.button_width
        maximize_right = width - regions.button_width
        if maximize_left <= x < maximize_right:
            return HTMAXBUTTON
        return HTCLIENT
    if x < regions.caption_left:
        return HTCLIENT
    return HTCAPTION


class _MSG(ctypes.Structure):
    _fields_ = (
        ("hWnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    )


class _NCCALCSIZE_PARAMS(ctypes.Structure):  # noqa: N801 - Windows structure name
    _fields_ = (("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p))


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, frame: WindowFrame) -> None:
        super().__init__()
        self._frame = frame

    def nativeEventFilter(
        self, event_type: QByteArray | bytes | bytearray | memoryview, message: int, /
    ) -> object:
        kind = bytes(event_type.data() if isinstance(event_type, QByteArray) else event_type)
        handled = self._frame._handle_native(kind, int(message))
        return handled if handled is not None else (False, 0)


class WindowFrame(QObject):
    """Native behaviour of the frameless MTEE window."""

    nativeChanged = Signal()
    maximizedChanged = Signal()
    maximizeHoveredChanged = Signal()
    maximizePressedChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._window: QWindow | None = None
        self._hwnd = 0
        self._regions = HitRegions()
        self._native = False
        self._maximize_hovered = False
        self._maximize_pressed = False
        self._filter: _NativeFilter | None = None

    @Property(bool, notify=nativeChanged)
    def native(self) -> bool:
        """Whether Windows handles moving, resizing and snapping itself."""
        return self._native

    @Property(bool, notify=maximizeHoveredChanged)
    def maximizeHovered(self) -> bool:
        return self._maximize_hovered

    @Property(bool, notify=maximizePressedChanged)
    def maximizePressed(self) -> bool:
        return self._maximize_pressed

    @Slot(int, int, int, int)
    def setTitleBar(
        self, title_bar_height: int, caption_left: int, button_width: int, buttons_width: int
    ) -> None:
        """Declare the title bar geometry used for hit testing."""
        self._regions = HitRegions(
            title_bar_height=title_bar_height,
            caption_left=caption_left,
            button_width=button_width,
            buttons_width=buttons_width,
        )

    def attach(self, window: QWindow) -> None:
        """Install the native behaviour on ``window`` when the platform allows it."""
        self._window = window
        window.windowStateChanged.connect(lambda _state: self.maximizedChanged.emit())
        if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
            return
        self._hwnd = int(window.winId())
        user32 = ctypes.windll.user32
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
        style = user32.GetWindowLongPtrW(self._hwnd, _GWL_STYLE)
        style |= _WS_CAPTION | _WS_THICKFRAME | _WS_MINIMIZEBOX | _WS_MAXIMIZEBOX | _WS_SYSMENU
        user32.SetWindowLongPtrW(self._hwnd, _GWL_STYLE, style)
        self._set_square_corners()
        self._filter = _NativeFilter(self)
        app = QCoreApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)
        user32.SetWindowPos(self._hwnd, None, 0, 0, 0, 0, _SWP_FLAGS)
        self._native = True
        self.nativeChanged.emit()

    def _set_square_corners(self) -> None:
        try:
            preference = ctypes.c_int(_DWMWCP_DONOTROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(self._hwnd),
                _DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(preference),
                ctypes.sizeof(preference),
            )
        except (AttributeError, OSError):
            # Before Windows 11 the attribute does not exist and corners are square.
            return

    def _is_zoomed(self) -> bool:
        return bool(ctypes.windll.user32.IsZoomed(wintypes.HWND(self._hwnd)))

    def _is_maximized(self) -> bool:
        # Qt maximizes a frameless window by resizing it to the work area, so
        # Windows may not consider it zoomed.
        window_maximized = (
            self._window is not None and self._window.visibility() == QWindow.Visibility.Maximized
        )
        return window_maximized or self._is_zoomed()

    def _handle_native(self, event_type: bytes, address: int) -> tuple[bool, int] | None:
        if event_type != b"windows_generic_MSG" or not address or self._window is None:
            return None
        msg = _MSG.from_address(address)
        if int(msg.hWnd or 0) != self._hwnd:
            return None
        if msg.message == _WM_NCCALCSIZE and msg.wParam:
            if self._is_zoomed():
                self._inset_maximized(msg.lParam)
            return True, 0
        if msg.message == _WM_NCHITTEST:
            return True, self._hit_test(msg.lParam)
        if msg.message == _WM_NCMOUSEMOVE:
            self._set_maximize_hovered(msg.wParam == HTMAXBUTTON)
            return None
        if msg.message in (_WM_NCMOUSELEAVE, _WM_MOUSEMOVE):
            self._set_maximize_hovered(False)
            if msg.message == _WM_NCMOUSELEAVE:
                self._set_maximize_pressed(False)
            return None
        if msg.message in (_WM_NCLBUTTONDOWN, _WM_NCLBUTTONDBLCLK) and msg.wParam == HTMAXBUTTON:
            self._set_maximize_pressed(True)
            return True, 0
        if msg.message == _WM_NCLBUTTONUP and msg.wParam == HTMAXBUTTON:
            was_pressed = self._maximize_pressed
            self._set_maximize_pressed(False)
            if was_pressed:
                self.toggleMaximized()
            return True, 0
        return None

    def _hit_test(self, l_param: int) -> int:
        assert self._window is not None
        x = ctypes.c_short(l_param & 0xFFFF).value
        y = ctypes.c_short((l_param >> 16) & 0xFFFF).value
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(wintypes.HWND(self._hwnd), ctypes.byref(rect))
        ratio = self._window.devicePixelRatio() or 1.0
        width = (rect.right - rect.left) / ratio
        height = (rect.bottom - rect.top) / ratio
        return hit_test(
            (x - rect.left) / ratio,
            (y - rect.top) / ratio,
            width,
            height,
            regions=self._regions,
            maximized=self._is_maximized(),
        )

    def _inset_maximized(self, l_param: int) -> None:
        """Keep a maximized window inside the work area instead of overflowing it."""
        user32 = ctypes.windll.user32
        padded = user32.GetSystemMetrics(_SM_CXPADDEDBORDER)
        frame_x = user32.GetSystemMetrics(_SM_CXSIZEFRAME) + padded
        frame_y = user32.GetSystemMetrics(_SM_CYSIZEFRAME) + padded
        params = _NCCALCSIZE_PARAMS.from_address(l_param)
        client = params.rgrc[0]
        client.left += frame_x
        client.top += frame_y
        client.right -= frame_x
        client.bottom -= frame_y

    def _set_maximize_hovered(self, hovered: bool) -> None:
        if hovered != self._maximize_hovered:
            self._maximize_hovered = hovered
            self.maximizeHoveredChanged.emit()

    def _set_maximize_pressed(self, pressed: bool) -> None:
        if pressed != self._maximize_pressed:
            self._maximize_pressed = pressed
            self.maximizePressedChanged.emit()

    @Slot()
    def toggleMaximized(self) -> None:
        """Maximize the window, or restore it when it is already maximized."""
        if self._window is None:
            return
        if self._window.visibility() == QWindow.Visibility.Maximized:
            self._window.showNormal()
        else:
            self._window.showMaximized()
