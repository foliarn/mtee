"""Settings alignment and the one-scroll playlist window, in the live QML window (plan 133)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtQuick import QQuickWindow
from tests.ui.test_settings_profile_ui import _demo_runtime, _first, _texts

from mtee.app import _shutdown
from mtee.models.demo_workspace import DemoWorkspace


def test_settings_first_tab_starts_on_the_heading_edge(qapp, tmp_path: Path) -> None:
    _application, runtime = _demo_runtime(qapp, tmp_path)
    try:
        window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
        cast(DemoWorkspace, runtime.workspace).openSettings()
        view = _first(window.contentItem(), "settingsView")
        heading = next(item for item in _all(view) if item.property("text") == "Settings")
        first_tab = _first(view, "settingsTab_general")
        label = next(item for item in _all(first_tab) if item.property("text") == "GENERAL")

        heading_x = heading.mapToScene(heading.boundingRect().topLeft()).x()
        label_x = label.mapToScene(label.boundingRect().topLeft()).x()
        assert abs(label_x - heading_x) <= 1
        assert "PREFERENCES" not in _texts(view)
        assert "Preferences" not in _texts(view)
    finally:
        _shutdown(runtime)


def _all(root):
    pending = [root]
    while pending:
        item = pending.pop()
        yield item
        pending.extend(item.childItems())
