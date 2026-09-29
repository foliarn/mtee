"""The waveform view must draw a 1,200-point waveform without freezing the interface.

Reading a Python list from QML costs a full copy per element, which made the first
paint of this view take several seconds. The samples now travel as one packed buffer.
"""

from __future__ import annotations

import random
import struct
import time

from PySide6.QtCore import Property, QByteArray, QObject, QUrl, Signal, Slot
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow

from mtee.assets import qml_dir

_POINTS = 1_200
_BUDGET_SECONDS = 1.0  # the list-based view needed about five seconds on the same machine


class _Waveform(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        generator = random.Random(3)
        flat = []
        for _ in range(_POINTS):
            flat.extend((-(0.2 + 0.7 * generator.random()), 0.2 + 0.7 * generator.random()))
        self._packed = QByteArray(struct.pack(f"<{len(flat)}f", *flat))

    @Property(QByteArray, notify=changed)
    def samples(self) -> QByteArray:
        return self._packed

    @Property(str, notify=changed)
    def state(self) -> str:
        return "ready"

    @Property(str, notify=changed)
    def error(self) -> str:
        return ""

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


def test_the_first_paint_of_a_full_waveform_is_immediate(qapp) -> None:
    engine = QQmlEngine()
    engine.addImportPath(str(qml_dir()))
    waveform, playback = _Waveform(), _Playback()
    engine.rootContext().setContextProperty("testWaveform", waveform)
    engine.rootContext().setContextProperty("testPlayback", playback)
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
        QUrl("file:///waveform-speed-probe.qml"),
    )
    started = time.perf_counter()
    window = component.create()
    assert window is not None, component.errors()
    assert isinstance(window, QQuickWindow)
    for _ in range(30):
        qapp.processEvents()
    window.grabWindow()
    elapsed = time.perf_counter() - started
    try:
        view = window.findChild(QObject, "view")
        assert view is not None
        points = view.property("displayPoints")
        assert len(points.toVariant() if hasattr(points, "toVariant") else points) == 700
        assert elapsed < _BUDGET_SECONDS, f"first paint took {elapsed:.2f} s"
    finally:
        window.close()
        window.deleteLater()
