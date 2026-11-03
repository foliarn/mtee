"""The QML of the records (plan 126.7) compiles in the real application.

The Settings page (the group Settings that travel) and the conflict tab (the two track lists of a
playlist changed on both sides) are only drawn when opened, so each file is compiled here with the
engine of the running application, and a syntax or type error fails the test.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent
from tests.helpers.ui_plugin import start_app, window_of
from tests.plugins.remote.conftest import PLUGIN_DIR

from mtee.app import _shutdown

UI_DIR = PLUGIN_DIR / "remote" / "ui"


def test_the_settings_and_conflict_qml_compile_in_the_application(
    qapp: object, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (PLUGIN_DIR,), ("remote",))
    try:
        window_of(runtime)
        errors: dict[str, list[str]] = {}
        for name in ("settings.qml", "conflict.qml"):
            component = QQmlComponent(runtime.engine, QUrl.fromLocalFile(str(UI_DIR / name)))
            errors[name] = [error.toString() for error in component.errors()]
            component.deleteLater()
        assert errors == {"settings.qml": [], "conflict.qml": []}
    finally:
        _shutdown(runtime)
