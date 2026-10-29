"""Helpers for the tests of plugins in the live window (plans 121.5 to 121.7).

``write_ui_plugin`` writes a tiny plugin, ``ui_probe``, that makes one of each UI
contribution into a plugin folder. The plugin keeps its calls in
``mtee.plugins.ui_probe.EVENTS`` (a list of strings) so a test can see which function the
core ran. The first row of its track list plays the first library track; the second and third
rows have no local file.

The other helpers start the real application with plugin folders (``start_app``), find QML
items by object name and click them. The sample plugin tests of ``tests/plugins`` use them too.
"""

from __future__ import annotations

import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.app import _build_runtime, _Runtime, create_application
from mtee.cli import AppOptions
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.loader import PluginPreferences
from mtee.services.app_paths import resolve_app_paths

PLUGIN_ID = "ui_probe"
LIST_KIND = "ui_probe.list"
PAGE_KIND = "ui_probe.page"

_MANIFEST = """
from mtee.plugins.api import PluginManifest

MANIFEST = PluginManifest(
    plugin_id="ui_probe",
    title="UI probe",
    description="Makes one of each contribution.",
    version="1.2.3",
    api_version=1,
    factory="mtee.plugins.ui_probe:create",
    uses_network=True,
)
"""

_PAGE_QML = """
import QtQuick
import Mtee

Rectangle {
    id: page
    property var workspace
    property var tab
    property int groupIndex: 0
    property int bottomInset: 0
    property var backend
    objectName: "probePage"
    color: Theme.editor
    FilterChip { objectName: "probeChip"; text: "from import Mtee" }
}
"""

_SETTINGS_QML = """
import QtQuick
import Mtee

Column {
    property var workspace
    property var backend
    objectName: "probeSettingsPage"
    Text {
        objectName: "probeSettingsText"
        text: backend ? backend.greeting : "no backend"
        color: Theme.textPrimary
    }
}
"""

_PLUGIN = """
from pathlib import Path

from PySide6.QtCore import Property, QObject

from mtee.plugins.api import (
    CellValue, LibraryScanned, PaneAction, PluginActivity, PluginRowsModel, SettingsPage,
    SidebarSection, StartupTask, TabAction, TabHeader, TabKind, TabRequest, TrackAction,
    TrackColumn, TrackListRow,
)

EVENTS = []
HERE = Path(__file__).parent


class Backend(QObject):
    @Property(str, constant=True)
    def greeting(self):
        return "hello from the backend"


class Service:
    def __init__(self, context):
        self.context = context
        self.rows = PluginRowsModel([
            {"id": "alpha", "name": "Alpha list", "badge": 2, "count": "3"},
            {"id": "group", "name": "A group", "kind": "group"},
            {"id": "beta", "name": "Beta list", "depth": 1},
        ])
        self.local_rows = PluginRowsModel([{"id": "gamma", "name": "Gamma"}])
        self.foot = PluginRowsModel([{"text": "Connected as probe", "tone": "secondary"}])
        self.watching = False
        self.backend = Backend()

    def _rows(self, ref):
        ids = self.context.library.track_ids()
        playable = ids[0] if ids else ""
        return [
            TrackListRow("r1", "Local one", "Example", "Album", 180, playable, {"state": "local"}),
            TrackListRow("r2", "Missing two", "Example", "Album", 200, "", {"state": "missing"}),
            TrackListRow("r3", "Missing three", "Other", "Album", 210, "", {"state": "missing"}),
        ]

    def _cell(self, row):
        state = (row.get("data") or {}).get("state")
        if state == "missing":
            return CellValue("Missing", "secondary", "Download")
        if state == "local":
            return CellValue("Local")
        return CellValue("Check", "warning")

    def _toggle_watch(self, ref):
        self.watching = not self.watching
        EVENTS.append("watch")

    def _start(self, job):
        EVENTS.append("startup")
        self.context.run_on_gui(lambda: EVENTS.append("startup on the gui"))

    def contributions(self):
        return [
            PluginActivity(
                "main", "Probe", "music",
                actions=(PaneAction("refresh", "Refresh the probe", "repeat",
                                    lambda: EVENTS.append("refresh")),),
                foot=self.foot,
            ),
            SidebarSection("lists", "Probe lists", "main", self.rows,
                           actions=(PaneAction("link", "From link", "arrow-down",
                                               lambda: EVENTS.append("link")),),
                           activate=lambda row_id: TabRequest(
                               "ui_probe.list", row_id) if row_id != "group" else None),
            SidebarSection("side", "Probe side", "playlists", self.local_rows,
                           activate=lambda row_id: TabRequest("ui_probe.page", row_id)),
            TabKind("ui_probe.list", lambda ref: "Probe " + ref, self._rows,
                    header=lambda ref: TabHeader("Probe " + ref, "Probe playlist", "About it",
                                                 "Probe", "3 tracks, 2 missing")),
            TabKind("ui_probe.page", lambda ref: "Page " + ref, HERE / "page.qml",
                    backend=self.backend),
            TabAction("download", "ui_probe.list", lambda ref: "Download missing (2)",
                      lambda ref: EVENTS.append("download " + ref), icon="arrow-down"),
            TabAction("watch", "ui_probe.list", "Watch", self._toggle_watch, kind="toggle",
                      checked=lambda ref: self.watching),
            TabAction("push", "playlist", "Push to probe",
                      lambda ref: EVENTS.append("push " + ref), kind="ghost"),
            TrackColumn("status", "Probe status", self._cell,
                        default_visible_for=("ui_probe.list",),
                        run_action=lambda row: EVENTS.append("row action " + row["id"])),
            TrackAction("link", "Link to a local track", "Probe",
                        lambda rows: EVENTS.append("link " + ",".join(r["id"] for r in rows)),
                        enabled_fn=lambda rows: all((r.get("data") or {}).get("state") == "missing"
                                                    for r in rows) and bool(rows)),
            TrackAction("better", "Get a better copy", "Probe",
                        lambda rows: EVENTS.append("better")),
            SettingsPage("accounts", "Accounts", HERE / "settings.qml", backend=self.backend),
            StartupTask("hello", self._start),
            LibraryScanned(lambda root: EVENTS.append("scanned " + root.name)),
        ]

    def unload(self):
        EVENTS.append("unload")


def create(context):
    EVENTS.append("create")
    return Service(context)
"""


def write_ui_plugin(folder: Path) -> Path:
    """Write the ``ui_probe`` package into ``folder`` and return its directory."""
    package = folder / PLUGIN_ID
    package.mkdir(parents=True)
    (package / "manifest.py").write_text(textwrap.dedent(_MANIFEST), encoding="utf-8")
    (package / "__init__.py").write_text(textwrap.dedent(_PLUGIN), encoding="utf-8")
    (package / "page.qml").write_text(textwrap.dedent(_PAGE_QML), encoding="utf-8")
    (package / "settings.qml").write_text(textwrap.dedent(_SETTINGS_QML), encoding="utf-8")
    return package


def start_app(
    data_dir: Path, plugin_dirs: Sequence[Path] = (), enabled: Sequence[str] = ()
) -> _Runtime:
    """Start the real application on ``data_dir`` with ``plugin_dirs`` and ``enabled`` switched on.

    The plugin switches are saved first, as Settings > Plugins would save them. The window is
    1440 x 900, offscreen. Call ``_shutdown(runtime)`` when done; ``start_app`` may be called
    again on the same ``data_dir`` to restart.
    """
    if enabled:
        paths = resolve_app_paths(data_dir).ensure()
        database = Database(paths.database_path)
        database.migrate()
        preferences = PluginPreferences(SettingsRepository(database))
        for plugin_id in enabled:
            preferences.set_enabled(plugin_id, True)
        database.close()
    application = create_application(["mtee"])
    options = AppOptions(
        data_dir=data_dir, demo=False, scenario="explorer", plugin_dirs=tuple(plugin_dirs)
    )
    runtime = _build_runtime(application, options)
    assert runtime is not None
    window_of(runtime).resize(1440, 900)
    return runtime


def window_of(runtime: _Runtime) -> QQuickWindow:
    return cast(QQuickWindow, runtime.engine.rootObjects()[0])


def workspace_of(runtime: _Runtime) -> WorkspaceModel:
    return cast(WorkspaceModel, runtime.workspace)


def plugin_ui_of(workspace: WorkspaceModel) -> Any:
    """The plugin contributions model; QML-facing members are untyped for pyright."""
    return cast(Any, workspace).pluginUi


def plugin_module(plugin_id: str) -> Any:
    """Return the imported package of a plugin, or ``None`` while it is not imported."""
    return sys.modules.get(f"mtee.plugins.{plugin_id}")


def find_child(root: QQuickItem, name: str) -> QQuickItem | None:
    """Return the first item named ``name`` at or below ``root``."""
    pending = [root]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def find_item(window: QQuickWindow, name: str) -> QQuickItem | None:
    """Return the first item named ``name`` in the window."""
    return find_child(window.contentItem(), name)


def need_item(window: QQuickWindow, name: str) -> QQuickItem:
    """Return the item named ``name``, failing the test when it is missing."""
    item = find_item(window, name)
    assert item is not None, f"no QML item named {name}"
    return item


def visible_texts(window: QQuickWindow) -> list[str]:
    """Return the ``text`` of every visible item of the window."""
    found: list[str] = []
    pending = [window.contentItem()]
    while pending:
        item = pending.pop()
        text = item.property("text")
        if isinstance(text, str) and item.isVisible():
            found.append(text)
        pending.extend(item.childItems())
    return found


def click(window: QQuickWindow, item: QQuickItem) -> None:
    """Click the centre of ``item`` with the left mouse button."""
    centre = item.mapToScene(item.boundingRect().center()).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre)
    QTest.qWait(30)


def settle(runtime: _Runtime) -> None:
    """Let the background jobs and the queued signals finish."""
    for _ in range(30):
        runtime.jobs.wait_for_done(500)
        QCoreApplication.processEvents()
        QTest.qWait(20)
