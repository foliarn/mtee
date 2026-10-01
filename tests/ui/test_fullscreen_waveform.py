from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QObject
from PySide6.QtQuick import QQuickItem, QQuickWindow

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.models.demo_workspace import DemoWorkspace


def _find(root: QQuickWindow, name: str) -> QQuickItem | None:
    return cast(QQuickItem | None, root.findChild(QObject, name))


def test_fullscreen_renders_monochrome_waveform_without_zoom_or_loop_controls(
    qapp, tmp_path: Path
) -> None:
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application,
        AppOptions(data_dir=tmp_path / "waveform-view", demo=True, scenario="explorer-info"),
    )
    assert runtime is not None
    root = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    root.resize(1440, 900)
    workspace = cast(DemoWorkspace, runtime.workspace)
    workspace.togglePlay()
    workspace.setFullscreen(True)
    QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)

    try:
        waveform = _find(root, "waveformView")
        assert waveform is not None
        assert waveform.isVisible()
        player = cast(QObject, workspace.property("playerModel"))
        waveform_model = cast(QObject, player.property("waveformModel"))
        assert waveform_model.property("state") == "ready"
        assert waveform_model.property("levels") is not None
        workspace.setFullscreen(False)
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
        assert _find(root, "waveformView") is None or not waveform.isVisible()
    finally:
        _shutdown(runtime)
        for item in runtime.engine.rootObjects():
            item.deleteLater()
        runtime.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        application.quit()
