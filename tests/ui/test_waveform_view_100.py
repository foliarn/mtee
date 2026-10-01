"""The fullscreen waveform view: bar colours, hover, times and bar count (plan 100)."""

from __future__ import annotations

import struct
import time
from typing import cast

import pytest
from PySide6.QtCore import Property, QByteArray, QObject, QPoint, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.assets import qml_dir


class _Waveform(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._levels = QByteArray()
        self.bar_counts: list[int] = []
        self.seeks: list[float] = []

    @Property(QByteArray, notify=changed)
    def levels(self) -> QByteArray:
        return self._levels

    @Property(str, notify=changed)
    def state(self) -> str:
        return "ready"

    @Slot(int)
    def setBarCount(self, count: int) -> None:  # noqa: N802 - called by name from QML
        self.bar_counts.append(count)
        values = [0.2 + 0.8 * ((index * 37) % 100) / 100 for index in range(count)]
        self._levels = QByteArray(struct.pack(f"<{count}f", *values))
        self.changed.emit()

    @Slot(float)
    def seekRatio(self, ratio: float) -> None:  # noqa: N802 - called by name from QML
        self.seeks.append(ratio)


class _Playback(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._position = 60.0
        self.events: list[tuple[str, float]] = []

    @Property(float, notify=changed)
    def playbackDuration(self) -> float:  # noqa: N802 - read by name from QML
        return 240.0

    @Property(float, notify=changed)
    def position(self) -> float:
        return self._position

    @Property(bool, notify=changed)
    def seekable(self) -> bool:
        return True

    @Slot(float, float)
    def scrubPress(self, ratio: float, width_px: float) -> None:  # noqa: N802 - called from QML
        self.events.append(("press", ratio))
        self.width_px = width_px

    @Slot(float)
    def scrubMove(self, ratio: float) -> None:  # noqa: N802 - called from QML
        self.events.append(("move", ratio))

    @Slot(float)
    def scrubRelease(self, ratio: float) -> None:  # noqa: N802 - called from QML
        self.events.append(("release", ratio))

    def move(self, position: float) -> None:
        self._position = position
        self.changed.emit()


_SOURCE = """
import QtQuick
import QtQuick.Window
import Mtee
import "file:///{components}"
Window {{
    width: 1440; height: 300; visible: true
    property var aheadBehind: view.barColor(10, 100, 200)
    property var aheadBetween: view.barColor(150, 100, 200)
    property var aheadBeyond: view.barColor(250, 100, 200)
    property var behindWhite: view.barColor(40, 100, 60)
    property var behindGrey: view.barColor(80, 100, 60)
    property var idleWhite: view.barColor(90, 100, -1)
    property var idleGrey: view.barColor(110, 100, -1)
    property color played: Theme.wavePlayed
    property color unplayed: Theme.waveUnplayed
    property color tint: Theme.waveHoverAhead
    WaveformView {{
        id: view
        objectName: "view"
        x: 20; y: 20
        width: 1400
        waveform: testWaveform
        playback: testPlayback
    }}
}}
"""


def _settle(qapp, seconds: float = 0.1) -> None:
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        qapp.processEvents()
        time.sleep(0.005)


@pytest.fixture
def probe(qapp):
    engine = QQmlEngine()
    engine.addImportPath(str(qml_dir()))
    waveform, playback = _Waveform(), _Playback()
    engine.rootContext().setContextProperty("testWaveform", waveform)
    engine.rootContext().setContextProperty("testPlayback", playback)
    component = QQmlComponent(engine)
    component.setData(
        _SOURCE.format(components=(qml_dir() / "components").as_posix()).encode(),
        QUrl("file:///waveform-view-100.qml"),
    )
    window = component.create()
    assert isinstance(window, QQuickWindow), component.errors()
    _settle(qapp, 0.3)
    yield qapp, window, waveform, playback
    window.close()
    window.deleteLater()


def _view(window: QQuickWindow) -> QQuickItem:
    return cast(QQuickItem, window.findChild(QObject, "view"))


def _texts(window: QQuickWindow) -> dict[str, str]:
    found: dict[str, str] = {}
    pending = [window.contentItem()]
    while pending:
        item = pending.pop()
        pending.extend(item.childItems())
        if item.objectName().startswith("waveformTime"):
            found[item.objectName()] = str(item.property("text"))
    return found


def _every_label(window: QQuickWindow) -> list[str]:
    labels: list[str] = []
    pending = [window.contentItem()]
    while pending:
        item = pending.pop()
        pending.extend(item.childItems())
        text = item.property("text")
        if isinstance(text, str):
            labels.append(text)
        labels.append(item.objectName())
    return labels


def _hover(qapp, window: QQuickWindow, view: QQuickItem, x: float) -> None:
    area = cast(QQuickItem, window.findChild(QObject, "waveformArea"))
    point = area.mapToScene(area.position()).toPoint()
    QTest.mouseMove(window, QPoint(point.x() + round(x), point.y() + 40))
    _settle(qapp, 0.05)


def _colour(window: QQuickWindow, name: str) -> str:
    value = window.property(name)
    return (value.name() if isinstance(value, QColor) else str(value)).lower()


def test_bar_colours_follow_the_three_rows_of_the_contract(probe) -> None:
    _qapp, window, _waveform, _playback = probe
    played, unplayed, tint = (_colour(window, name) for name in ("played", "unplayed", "tint"))
    assert len({played, unplayed, tint}) == 3
    # Hover to the right of the playhead (p=100, h=200): white, intermediate tint, grey.
    assert _colour(window, "aheadBehind") == played
    assert _colour(window, "aheadBetween") == tint
    assert _colour(window, "aheadBeyond") == unplayed
    # Hover to the left (p=100, h=60): white up to the mouse, grey beyond, even before p.
    assert _colour(window, "behindWhite") == played
    assert _colour(window, "behindGrey") == unplayed
    # No hover: white up to the playhead, grey after.
    assert _colour(window, "idleWhite") == played
    assert _colour(window, "idleGrey") == unplayed


def test_there_is_no_floating_time_badge_nor_help_text(probe) -> None:
    _qapp, window, _waveform, _playback = probe
    labels = _every_label(window)
    assert "timeTag" not in labels
    assert not any("Click waveform" in label for label in labels)


def test_times_show_the_position_then_the_hovered_time(probe) -> None:
    qapp, window, _waveform, _playback = probe
    texts = _texts(window)
    assert texts["waveformTimeTop"] == "1:00"  # 60 s of 240 s
    assert texts["waveformTimeBottom"] == "4:00"
    view = _view(window)
    span = float(view.property("span"))
    _hover(qapp, window, view, span / 2)
    assert view.property("hoverRatio") == pytest.approx(0.5, abs=0.02)
    assert _texts(window)["waveformTimeTop"] in {"1:59", "2:00"}  # the middle, to the pixel
    QTest.mouseMove(window, QPoint(2, 2))
    _settle(qapp, 0.05)
    assert view.property("hoverRatio") == -1
    assert _texts(window)["waveformTimeTop"] == "1:00"


def test_hovering_never_seeks(probe) -> None:
    qapp, window, waveform, _playback = probe
    view = _view(window)
    span = float(view.property("span"))
    for fraction in (0.1, 0.5, 0.9):
        _hover(qapp, window, view, span * fraction)
    assert waveform.seeks == []


def test_the_bar_count_follows_the_width_with_a_debounce(probe) -> None:
    qapp, window, waveform, _playback = probe
    view = _view(window)
    expected = (1400 - 48 - 16 + 2) // (3 + 2)
    assert view.property("barCount") == expected
    assert waveform.bar_counts[-1] == expected
    before = len(waveform.bar_counts)
    view.setWidth(900)
    _settle(qapp, 0.02)
    assert len(waveform.bar_counts) == before  # not yet: the request is debounced
    _settle(qapp, 0.15)
    assert waveform.bar_counts[-1] == (900 - 48 - 16 + 2) // 5


def test_the_playhead_ratio_follows_the_playback_position(probe) -> None:
    qapp, window, _waveform, playback = probe
    view = _view(window)
    assert view.property("playheadRatio") == pytest.approx(0.25)
    playback.move(120.0)
    _settle(qapp, 0.02)
    assert view.property("playheadRatio") == pytest.approx(0.5)


def test_a_repaint_at_full_width_is_fast(probe, capsys) -> None:
    qapp, window, _waveform, playback = probe
    window.grabWindow()
    samples: list[float] = []
    for step in range(20):
        playback.move(60.0 + step)
        started = time.perf_counter()
        qapp.processEvents()
        window.grabWindow()
        samples.append(time.perf_counter() - started)
    median = sorted(samples)[len(samples) // 2]
    with capsys.disabled():
        print(f"\nwaveform repaint + grab at 1440 px: median {median * 1000:.1f} ms")
    assert median < 0.25  # generous: offscreen software rendering; measured for the report


def _area_point(window: QQuickWindow, x: float) -> QPoint:
    area = cast(QQuickItem, window.findChild(QObject, "waveformArea"))
    point = area.mapToScene(area.position()).toPoint()
    return QPoint(point.x() + round(x), point.y() + 40)


def test_a_press_move_release_reaches_the_player_with_unbounded_ratios(probe) -> None:
    qapp, window, _waveform, playback = probe
    span = float(_view(window).property("span"))
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=_area_point(window, span * 0.25))
    _settle(qapp, 0.02)
    assert playback.events[0][0] == "press"
    assert playback.events[0][1] == pytest.approx(0.25, abs=0.01)
    assert playback.width_px == pytest.approx(span)

    QTest.mouseMove(window, _area_point(window, span * 0.5))
    _settle(qapp, 0.02)
    QTest.mouseMove(window, _area_point(window, span + 120))  # held outside, to the right
    _settle(qapp, 0.02)
    QTest.mouseMove(window, _area_point(window, -80))  # then outside, to the left
    _settle(qapp, 0.02)
    moves = [ratio for kind, ratio in playback.events if kind == "move"]
    assert any(0.45 < ratio < 0.55 for ratio in moves)
    assert any(ratio > 1.0 for ratio in moves)
    assert any(ratio < 0.0 for ratio in moves)

    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=_area_point(window, span + 200))
    _settle(qapp, 0.02)
    assert playback.events[-1][0] == "release"
    assert playback.events[-1][1] > 1.0


def test_moving_without_the_button_and_other_buttons_do_not_scrub(probe) -> None:
    qapp, window, _waveform, playback = probe
    span = float(_view(window).property("span"))
    QTest.mouseMove(window, _area_point(window, span * 0.4))
    _settle(qapp, 0.02)
    QTest.mouseClick(window, Qt.MouseButton.RightButton, pos=_area_point(window, span * 0.4))
    _settle(qapp, 0.02)
    assert playback.events == []
