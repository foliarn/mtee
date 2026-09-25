from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QCoreApplication, QObject
from PySide6.QtQuick import QQuickItem, QQuickWindow

from mtee.app import _build_runtime, create_application
from mtee.cli import AppOptions
from mtee.models.workspace_model import WorkspaceModel


def _find_item(root: QQuickItem, object_name: str) -> QQuickItem | None:
    pending = list(root.childItems())
    while pending:
        item = pending.pop()
        if item.objectName() == object_name:
            return item
        pending.extend(item.childItems())
    return None


def test_local_convert_view_loads_runtime_capabilities_and_settings(qapp, tmp_path: Path) -> None:
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application,
        AppOptions(data_dir=tmp_path / "convert-view", demo=False),
    )
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    workspace = runtime.workspace
    assert isinstance(workspace, WorkspaceModel)
    try:
        workspace.openConvert()
        QCoreApplication.processEvents()
        view = _find_item(root.contentItem(), "convertView")
        assert view is not None
        model = cast(QObject, workspace.conversionModel)
        formats = cast(list[dict[str, Any]], model.property("formats"))
        assert {item["id"] for item in formats} >= {
            "mp3",
            "flac",
            "wav",
            "aiff",
            "vorbis",
            "opus",
            "m4a-aac",
            "m4a-alac",
        }
    finally:
        runtime.jobs.shutdown()
        for item in runtime.engine.rootObjects():
            item.deleteLater()
        runtime.engine.deleteLater()
        QCoreApplication.processEvents()
        runtime.database.close()
        application.quit()
