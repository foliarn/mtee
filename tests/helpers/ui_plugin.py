"""A tiny plugin that makes one of each UI contribution, for the tests of plan 121.5.

``write_ui_plugin`` writes the package ``ui_probe`` into a plugin folder. The plugin keeps
its calls in ``mtee.plugins.ui_probe.EVENTS`` (a list of strings) so a test can see which
function the core ran. The first row of its track list plays the first library track; the
second and third rows have no local file.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

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
    CellValue, PaneAction, PluginActivity, PluginRowsModel, SettingsPage, SidebarSection,
    StartupTask, TabAction, TabHeader, TabKind, TabRequest, TrackAction, TrackColumn,
    TrackListRow,
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
            StartupTask("hello", lambda context: EVENTS.append("startup")),
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
