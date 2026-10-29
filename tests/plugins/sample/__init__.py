"""The sample plugin: one of each contribution, built on the plugin interface alone.

The contract tests (``tests/plugins/test_contract.py``) and the UI tests run it, and
``docs/plugins.md`` points to it as the model of a plugin. It records each call of its
functions in ``EVENTS`` so that a test can see what the core ran.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.plugins.api import (
    CellValue,
    Contribution,
    PaneAction,
    PluginActivity,
    PluginContext,
    PluginRowsModel,
    PluginService,
    PluginSettings,
    SettingsPage,
    SidebarSection,
    StartupTask,
    TabAction,
    TabHeader,
    TabKind,
    TabRequest,
    TrackAction,
    TrackColumn,
    TrackListRow,
)

EVENTS: list[str] = []
HERE = Path(__file__).parent
LIST_KIND = "sample.list"


class SettingsBackend(QObject):
    """What the Settings page reads and changes; the values live in the plugin settings."""

    changed = Signal()

    def __init__(self, settings: PluginSettings, item_count: int) -> None:
        super().__init__()
        self._settings = settings
        self._item_count = item_count

    @Property(str, notify=changed)
    def label(self) -> str:
        return self._settings.get("label", "") or ""

    @Slot(str)
    def setLabel(self, value: str) -> None:
        self._settings.set("label", value)
        self.changed.emit()

    @Property(bool, notify=changed)
    def loud(self) -> bool:
        return bool(self._settings.get_json("loud", False))

    @Slot(bool)
    def setLoud(self, value: bool) -> None:
        self._settings.set_json("loud", value)
        self.changed.emit()

    @Property(int, notify=changed)
    def copies(self) -> int:
        stored = self._settings.get_json("copies", 1)
        return stored if isinstance(stored, int) and 1 <= stored <= 5 else 1

    @Slot(int)
    def setCopies(self, value: int) -> None:
        self._settings.set_json("copies", max(1, min(5, value)))
        self.changed.emit()

    @Property(bool, notify=changed)
    def signedIn(self) -> bool:
        return bool(self._settings.get_json("signed_in", False))

    @Slot()
    def toggleSignIn(self) -> None:
        self._settings.set_json("signed_in", not self.signedIn)
        EVENTS.append("sign in" if self.signedIn else "sign out")
        self.changed.emit()

    @Property(int, constant=True)
    def itemCount(self) -> int:
        return self._item_count


class Service:
    """The plugin service: it builds the contributions and releases what it holds."""

    def __init__(self, context: PluginContext) -> None:
        self._context = context
        self._watching = False
        self._lists = PluginRowsModel(
            [
                {"id": "all", "name": "All samples", "icon": "music", "badge": 2},
                {"id": "group", "name": "Groups", "kind": "group"},
                {"id": "missing", "name": "Missing only", "depth": 1},
            ]
        )
        self._foot = PluginRowsModel([{"text": "Sample is connected", "tone": "secondary"}])
        self._backend = SettingsBackend(context.settings, self._count_items())

    def _count_items(self) -> int:
        cursor = self._context.database.connection().execute("SELECT COUNT(*) FROM sample_items")
        return int(cursor.fetchone()[0])

    # -- the functions the core calls
    def _rows(self, ref: str) -> list[TrackListRow]:
        """Return the rows of a list. Runs on a job thread: read only the plugin's own data."""
        EVENTS.append(f"rows {ref}")
        library_ids = self._context.library.track_ids()
        found = self._context.database.connection().execute(
            "SELECT item_id, title, artist, state FROM sample_items ORDER BY rowid"
        )
        rows: list[TrackListRow] = []
        for item in found:
            state = str(item["state"])
            if ref == "missing" and state != "missing":
                continue
            # A row with a local file plays that track; a row without one is unavailable.
            playable = library_ids[0] if state == "local" and library_ids else ""
            rows.append(
                TrackListRow(
                    row_id=str(item["item_id"]),
                    title=str(item["title"]),
                    artist=str(item["artist"]),
                    album="Sample album",
                    duration_seconds=180.0,
                    track_id=playable,
                    data={"state": state},
                )
            )
        return rows

    @staticmethod
    def _cell(row: Mapping[str, Any]) -> CellValue | None:
        """Return the badge of a row. Runs on a job thread."""
        state = (row.get("data") or {}).get("state")
        if state == "missing":
            return CellValue("Missing", "secondary", action="fetch")
        if state == "local":
            return CellValue("Local")
        return None

    @staticmethod
    def _only_missing(rows: Sequence[Mapping[str, Any]]) -> bool:
        return bool(rows) and all((row.get("data") or {}).get("state") == "missing" for row in rows)

    def _toggle_watch(self, ref: str) -> None:
        self._watching = not self._watching
        EVENTS.append("watch")

    # -- the contributions
    def contributions(self) -> Sequence[Contribution]:
        return [
            PluginActivity(
                "main",
                "Sample",
                "music",
                actions=(
                    PaneAction(
                        "refresh", "Refresh the samples", "repeat", lambda: EVENTS.append("refresh")
                    ),
                ),
                foot=self._foot,
            ),
            SidebarSection(
                "lists",
                "Sample lists",
                "main",
                self._lists,
                activate=lambda row_id: (
                    None if row_id == "group" else TabRequest(LIST_KIND, row_id)
                ),
            ),
            TabKind(
                LIST_KIND,
                lambda ref: f"Sample {ref}",
                self._rows,
                header=lambda ref: TabHeader(
                    f"Sample {ref}", "Sample list", "Rows of the sample table.", "Sample plugin"
                ),
            ),
            TabAction(
                "fetch_all",
                LIST_KIND,
                lambda ref: "Fetch missing (2)",
                lambda ref: EVENTS.append(f"fetch_all {ref}"),
                icon="arrow-down",
                kind="primary",
            ),
            TabAction(
                "watch",
                LIST_KIND,
                "Watch",
                self._toggle_watch,
                kind="toggle",
                checked=lambda ref: self._watching,
            ),
            TrackColumn(
                "status",
                "Sample status",
                self._cell,
                default_visible_for=(LIST_KIND,),
                run_action=lambda row: EVENTS.append(f"fetch {row['id']}"),
            ),
            TrackAction(
                "mark",
                "Mark as wanted",
                "Sample",
                lambda rows: EVENTS.append("mark " + ",".join(str(row["id"]) for row in rows)),
                enabled_fn=self._only_missing,
            ),
            SettingsPage("settings", "Sample", HERE / "settings.qml", backend=self._backend),
            StartupTask("hello", lambda job_context: EVENTS.append("startup")),
        ]

    def unload(self) -> None:
        EVENTS.append("unload")


def create(context: PluginContext) -> PluginService:
    """Build the service; the core has already applied the plugin migrations."""
    EVENTS.append("create")
    return Service(context)
