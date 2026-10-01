"""The waveform view must draw a full-width waveform without freezing the interface.

Reading a Python list from QML costs a full copy per element, which once made the first
paint of the waveform take several seconds. The bar heights now travel as one packed
float32 buffer (``WaveformModel.levels``).
"""

from __future__ import annotations

import random
import struct
import time

from PySide6.QtCore import Property, QByteArray, QObject, QUrl, Signal, Slot, qInstallMessageHandler
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow

from mtee.assets import qml_dir

_BUDGET_SECONDS = 1.0  # the list-based view needed about five seconds on the same machine


class _Waveform(QObject):
    changed = Signal()

    def __init__(self, ready: bool = True) -> None:
        super().__init__()
        self._ready = ready
        self._levels = QByteArray()
        self.bar_counts: list[int] = []

    @Property(QByteArray, notify=changed)
    def levels(self) -> QByteArray:
        return self._levels

    @Property(str, notify=changed)
    def state(self) -> str:
        return "ready" if self._ready else "generating"

    @Property(str, notify=changed)
    def error(self) -> str:
        return ""

    @Slot(int)
    def setBarCount(self, count: int) -> None:  # noqa: N802 - called by name from QML
        self.bar_counts.append(count)
        if not self._ready or count < 1:
            return
        generator = random.Random(3)
        values = [0.2 + 0.8 * generator.random() for _ in range(count)]
        self._levels = QByteArray(struct.pack(f"<{count}f", *values))
        self.changed.emit()

    @Slot(float)
    def seekRatio(self, ratio: float) -> None:  # noqa: N802 - called by name from QML
        self.ratio = ratio


class _Playback(QObject):
    changed = Signal()

    @Property(float, notify=changed)
    def playbackDuration(self) -> float:  # noqa: N802 - read by name from QML
        return 300.0

    @Property(float, notify=changed)
    def position(self) -> float:
        return 100.0

    @Property(bool, notify=changed)
    def seekable(self) -> bool:
        return True


def _window(engine: QQmlEngine, name: str) -> QQuickWindow:
    components = (qml_dir() / "components").as_posix()
    component = QQmlComponent(engine)
    component.setData(
        f"""
        import QtQuick
        import QtQuick.Window
        import "file:///{components}"
        Window {{
            width: 1400; height: 200; visible: true
            WaveformView {{
                objectName: "view"
                anchors.fill: parent
                waveform: testWaveform
                playback: testPlayback
            }}
        }}
        """.encode(),
        QUrl(f"file:///{name}.qml"),
    )
    window = component.create()
    assert window is not None, component.errors()
    assert isinstance(window, QQuickWindow)
    window.component = component  # type: ignore[attr-defined]  # keep the component alive
    return window


def test_the_first_paint_of_a_full_waveform_is_immediate(qapp) -> None:
    engine = QQmlEngine()
    engine.addImportPath(str(qml_dir()))
    waveform, playback = _Waveform(), _Playback()
    engine.rootContext().setContextProperty("testWaveform", waveform)
    engine.rootContext().setContextProperty("testPlayback", playback)
    started = time.perf_counter()
    window = _window(engine, "waveform-speed-probe")
    for _ in range(30):
        qapp.processEvents()
        time.sleep(0.005)
    window.grabWindow()
    elapsed = time.perf_counter() - started
    try:
        view = window.findChild(QObject, "view")
        assert view is not None
        assert view.property("barCount") == waveform.bar_counts[-1] > 200
        levels = view.property("levelValues")
        assert len(levels.toVariant() if hasattr(levels, "toVariant") else levels) == view.property(
            "barCount"
        )
        assert elapsed < _BUDGET_SECONDS, f"first paint took {elapsed:.2f} s"
    finally:
        window.close()
        window.deleteLater()


def test_a_waveform_that_is_not_ready_yet_draws_flat_bars_without_errors(qapp) -> None:
    """An empty buffer reaches QML as a zero-length ArrayBuffer, which Float32Array refuses."""
    messages: list[str] = []
    previous = qInstallMessageHandler(lambda _mode, _context, text: messages.append(text))
    try:
        engine = QQmlEngine()
        engine.addImportPath(str(qml_dir()))
        waveform, playback = _Waveform(ready=False), _Playback()
        engine.rootContext().setContextProperty("testWaveform", waveform)
        engine.rootContext().setContextProperty("testPlayback", playback)
        window = _window(engine, "waveform-empty-probe")
        for _ in range(10):
            qapp.processEvents()
        view = window.findChild(QObject, "view")
        assert view is not None
        assert len(view.property("levelValues").toVariant()) == 0
        assert view.property("drawCount") == view.property("barCount")
        window.close()
        window.deleteLater()
    finally:
        qInstallMessageHandler(previous)
    assert [text for text in messages if "WaveformView" in text] == []
