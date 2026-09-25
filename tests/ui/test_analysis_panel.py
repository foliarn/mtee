"""The real analysis panel is available in the library inspector."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtQuick import QQuickItem, QQuickWindow

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.models.workspace_model import WorkspaceModel
from mtee.services.player_backend import PlayerBackendError


def _find(root: QQuickWindow, name: str) -> QQuickItem | None:
    pending = [root.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def test_analysis_panel_opens_in_the_library_inspector(qapp, tmp_path: Path, monkeypatch) -> None:
    def no_native_player():
        raise PlayerBackendError("Disabled for the offscreen QML test.")

    monkeypatch.setattr("mtee.app.MpvBackend", no_native_player)
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application,
        AppOptions(data_dir=tmp_path / "analysis-ui", diagnostic_no_native_frame=True),
    )
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    workspace = cast(WorkspaceModel, runtime.workspace)
    workspace.setRightPanelVisible(True)
    workspace.showRightPanel("analysis")
    root.show()
    QCoreApplication.processEvents()

    try:
        assert workspace.analysisModel is not None
        assert _find(root, "analysisPanel") is not None
    finally:
        _shutdown(runtime)
        for item in runtime.engine.rootObjects():
            item.deleteLater()
        runtime.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        application.quit()
