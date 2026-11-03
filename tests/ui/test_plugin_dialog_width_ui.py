"""The width of a plugin's dialog (PluginDialog.width), in the live window.

A plugin that asks for 640 px gets a 640 px popup in a wide window. A width outside 320 to 640
refuses the plugin, with the reason in its record. The default stays 480 px.
"""

from __future__ import annotations

import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from PySide6.QtCore import QObject
from PySide6.QtQuick import QQuickItem, QQuickWindow
from tests.helpers.ui_plugin import (
    find_child,
    plugin_ui_of,
    settle,
    start_app,
    window_of,
    workspace_of,
)

import mtee.plugins
from mtee.app import _shutdown
from mtee.plugins.loader import PluginStatus

PLUGIN_ID = "dialog_width"
_HERE = Path(__file__).parent

_MANIFEST = """
from mtee.plugins.api import PluginManifest

MANIFEST = PluginManifest(
    plugin_id="dialog_width",
    title="Dialog width",
    description="Opens one dialog of a given width.",
    version="1.0.0",
    api_version=1,
    factory="mtee.plugins.dialog_width:create",
)
"""

_DIALOG_QML = """
import QtQuick
import Mtee

Text {
    objectName: "widthProbeText"
    property var workspace
    property var backend
    property var dialog
    property string ref: ""
    text: "Probe " + ref
    color: Theme.textPrimary
}
"""


@pytest.fixture(autouse=True)
def restore_plugin_path() -> Iterator[None]:
    """A test that loads the plugin leaves the import path and modules as it found them."""
    before = list(mtee.plugins.__path__)
    yield
    mtee.plugins.__path__[:] = before
    for name in [key for key in sys.modules if key.startswith(f"mtee.plugins.{PLUGIN_ID}")]:
        del sys.modules[name]


def _write_plugin(folder: Path, width: str) -> None:
    """Write the plugin package; ``width`` is the Python text of the argument, or empty."""
    package = folder / PLUGIN_ID
    package.mkdir(parents=True)
    argument = f", width={width}" if width else ""
    body = f"""
from pathlib import Path

from mtee.plugins.api import PluginDialog

HERE = Path(__file__).parent


class Service:
    def contributions(self):
        return [PluginDialog("note", HERE / "dialog.qml"{argument})]

    def unload(self):
        pass


def create(context):
    return Service()
"""
    (package / "manifest.py").write_text(textwrap.dedent(_MANIFEST), encoding="utf-8")
    (package / "__init__.py").write_text(textwrap.dedent(body), encoding="utf-8")
    (package / "dialog.qml").write_text(textwrap.dedent(_DIALOG_QML), encoding="utf-8")


def _popup(window: QQuickWindow) -> QObject:
    popup = window.findChild(QObject, "pluginDialog")
    assert popup is not None, "the plugin dialog popup is not in the window"
    return popup


def test_a_dialog_of_640_px_opens_640_px_wide_in_a_wide_window(qapp, tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _write_plugin(plugins, "640")
    runtime = start_app(tmp_path / "data", (plugins,), (PLUGIN_ID,))
    try:
        window = window_of(runtime)
        assert window.width() >= 672  # wide enough for 640 px and the 16 px margins
        records = cast(Any, runtime.plugins).plugins
        record = next(item for item in records if item.plugin_id == PLUGIN_ID)
        assert record.status is PluginStatus.RUNNING

        plugin_ui_of(workspace_of(runtime)).open_dialog(f"{PLUGIN_ID}.note", "one")
        settle(runtime)

        popup = _popup(window)
        assert popup.property("opened") is True
        assert popup.property("width") == 640
        content = cast(QQuickItem, popup.property("contentItem"))
        probe = find_child(content, "widthProbeText")
        assert probe is not None and probe.property("text") == "Probe one"
    finally:
        _shutdown(runtime)


def test_a_dialog_without_a_width_opens_480_px_wide(qapp, tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _write_plugin(plugins, "")
    runtime = start_app(tmp_path / "data", (plugins,), (PLUGIN_ID,))
    try:
        window = window_of(runtime)
        plugin_ui_of(workspace_of(runtime)).open_dialog(f"{PLUGIN_ID}.note", "")
        settle(runtime)

        assert _popup(window).property("width") == 480
    finally:
        _shutdown(runtime)


def test_a_dialog_wider_than_640_px_refuses_the_plugin_with_a_reason(qapp, tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _write_plugin(plugins, "700")
    runtime = start_app(tmp_path / "data", (plugins,), (PLUGIN_ID,))
    try:
        records = cast(Any, runtime.plugins).plugins
        record = next(item for item in records if item.plugin_id == PLUGIN_ID)
        assert record.status is PluginStatus.FAILED
        assert "must be a whole number of pixels from 320 to 640, not 700" in record.error
        assert record.contributions == ()
    finally:
        _shutdown(runtime)
