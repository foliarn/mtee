"""Qt smoke checks for the prototype's three spaces and transitions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject

from mtee.app import _build_runtime, create_application
from mtee.cli import AppOptions


def _runtime(qapp, tmp_path: Path, scenario: str):
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application,
        AppOptions(data_dir=tmp_path / scenario, demo=True, scenario=scenario),
    )
    assert runtime is not None
    return application, runtime


def test_convert_error_scenario_loads_the_convert_view(qapp, tmp_path: Path) -> None:
    application, runtime = _runtime(qapp, tmp_path, "convert-error")
    try:
        QCoreApplication.processEvents()
        root = runtime.engine.rootObjects()[0]
        assert root.objectName() == "mteeWindow"
        assert runtime.workspace.screen == "convert"
        assert runtime.workspace.conversionError is True
        assert root.findChild(QObject, "convertView") is not None
    finally:
        runtime.jobs.shutdown()
        runtime.database.close()
        application.quit()


def test_navigation_preserves_the_same_demo_workspace(qapp, tmp_path: Path) -> None:
    application, runtime = _runtime(qapp, tmp_path, "browser-split")
    try:
        root = runtime.engine.rootObjects()[0]
        assert runtime.workspace.selectedRows == [0]
        runtime.workspace.setScreen("listening")
        QCoreApplication.processEvents()
        assert runtime.workspace.screen == "listening"
        assert root.findChild(QObject, "listeningView") is not None

        runtime.workspace.setScreen("convert")
        QCoreApplication.processEvents()
        assert runtime.workspace.screen == "convert"
        assert root.findChild(QObject, "convertView") is not None
        assert runtime.workspace.selectedRows == [0]
    finally:
        runtime.jobs.shutdown()
        runtime.database.close()
        application.quit()
