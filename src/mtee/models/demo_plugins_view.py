"""The Plugins view of the demo: invented plugins in the states of the 123.5 mock-ups.

It has the same properties and slots as ``PluginsViewModel``, so the QML is the same. Nothing is
installed, downloaded or removed for real: the switch and the search change memory only, and the
file and network actions show a notice.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

__all__ = ["DemoPluginsView"]

_NOT_IN_DEMO = "Plugins are not installed or downloaded in the demo."

_INSTALLED: tuple[dict[str, Any], ...] = (
    {
        "id": "spotify",
        "title": "Spotify",
        "version": "1.0.0",
        "author": "Axel Raux",
        "description": "Compare Spotify playlists with your library, import and push them, and "
        "download missing tracks from TIDAL.",
        "letter": "S",
        "status": "running",
        "statusText": "Running",
        "error": "",
        "usesNetwork": True,
        "enabled": True,
        "updateVersion": "",
        "librariesCount": 6,
        "licence": "GPL-3.0-or-later",
        "homepage": "",
        "installedFrom": "file",
        "readme": "",
    },
    {
        "id": "sample",
        "title": "Sample",
        "version": "0.1.0",
        "author": "MTEE",
        "description": "A plugin that adds one list and one page, for developers.",
        "letter": "S",
        "status": "disabled",
        "statusText": "Disabled",
        "error": "",
        "usesNetwork": False,
        "enabled": False,
        "updateVersion": "",
        "librariesCount": 0,
        "licence": "GPL-3.0-or-later",
        "homepage": "",
        "installedFrom": "file",
        "readme": "",
    },
    {
        "id": "genre_manager",
        "title": "Genre Manager",
        "version": "0.2.0",
        "author": "MTEE",
        "description": "Classify tracks by genre and keep the genre tree.",
        "letter": "G",
        "status": "failed",
        "statusText": "Failed",
        "error": "Needs MTEE 0.3 or later.",
        "usesNetwork": False,
        "enabled": True,
        "updateVersion": "",
        "librariesCount": 0,
        "licence": "GPL-3.0-or-later",
        "homepage": "",
        "installedFrom": "marketplace",
        "readme": "",
    },
    {
        "id": "convert",
        "title": "Convert",
        "version": "1.1.0",
        "author": "MTEE",
        "description": "Convert audio files through FFmpeg, with a visible job queue.",
        "letter": "C",
        "status": "restart",
        "statusText": "Restart needed",
        "error": "",
        "usesNetwork": False,
        "enabled": True,
        "updateVersion": "1.2.0",
        "librariesCount": 0,
        "licence": "GPL-3.0-or-later",
        "homepage": "",
        "installedFrom": "marketplace",
        "readme": "",
    },
)

_MARKETPLACE: tuple[dict[str, Any], ...] = (
    {
        "id": "convert",
        "title": "Convert",
        "version": "1.2.0",
        "author": "MTEE",
        "description": "Convert audio files through FFmpeg, with a visible job queue.",
        "letter": "C",
        "usesNetwork": False,
        "state": "update",
        "installedVersion": "1.1.0",
    },
    {
        "id": "artist_manager",
        "title": "Artist manager",
        "version": "0.4.0",
        "author": "MTEE",
        "description": "Credits, artist pages and tag fixes for the whole library.",
        "letter": "A",
        "usesNetwork": False,
        "state": "install",
        "installedVersion": "",
    },
    {
        "id": "genre_manager",
        "title": "Genre Manager",
        "version": "0.2.0",
        "author": "MTEE",
        "description": "Classify tracks by genre and keep the genre tree.",
        "letter": "G",
        "usesNetwork": False,
        "state": "installed",
        "installedVersion": "0.2.0",
    },
    {
        "id": "loudness_report",
        "title": "Loudness report",
        "version": "0.3.0",
        "author": "MTEE",
        "description": "A report of the loudness of each album, as a text file.",
        "letter": "L",
        "usesNetwork": False,
        "state": "install",
        "installedVersion": "",
    },
)


class DemoPluginsView(QObject):
    """The Plugins view of the demo, with invented data and no real action."""

    changed = Signal()
    noticeRaised = Signal(str)
    detailRequested = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._installed = [dict(row) for row in _INSTALLED]
        self._search = ""
        self._restart_ids = {"convert"}

    @Property(list, notify=changed)
    def installed(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._installed if self._matches(row)]

    @Property(list, notify=changed)
    def marketplace(self) -> list[dict[str, Any]]:
        return [dict(row) for row in _MARKETPLACE if self._matches(row)]

    @Property(str, notify=changed)
    def marketplaceState(self) -> str:
        return "ready"

    @Property(str, notify=changed)
    def marketplaceError(self) -> str:
        return ""

    @Property(str, notify=changed)
    def lastCheckedText(self) -> str:
        return "Last checked 2 min ago"

    def _read_search(self) -> str:
        return self._search

    def _write_search(self, value: str) -> None:
        if value != self._search:
            self._search = value
            self.changed.emit()

    search = Property(str, _read_search, _write_search, notify=changed)

    @Property(bool, notify=changed)
    def restartNeeded(self) -> bool:
        return bool(self._restart_ids)

    @Property(str, notify=changed)
    def restartText(self) -> str:
        count = len(self._restart_ids)
        if count == 0:
            return ""
        return "1 plugin needs a restart" if count == 1 else f"{count} plugins need a restart"

    @Property(dict, notify=changed)
    def pendingInstall(self) -> dict[str, Any]:
        return {}

    @Property(object, notify=changed)
    def refusal(self) -> Any:
        return ""

    @Slot(str)
    def openDetail(self, plugin_id: str) -> None:
        title = self._title_of(plugin_id)
        if title:
            self.detailRequested.emit(plugin_id, title)

    @Slot(str, result=dict)
    def detail(self, plugin_id: str) -> dict[str, Any]:
        for row in (*self._installed, *_MARKETPLACE):
            if row["id"] == plugin_id:
                return dict(row)
        return {}

    @Slot(str, bool)
    def setEnabled(self, plugin_id: str, enabled: bool) -> None:
        for row in self._installed:
            if row["id"] == plugin_id:
                row["enabled"] = bool(enabled)
                self._restart_ids.add(plugin_id)
        self.changed.emit()

    @Slot(str)
    def uninstall(self, plugin_id: str) -> None:
        self._installed = [row for row in self._installed if row["id"] != plugin_id]
        self._restart_ids.add(plugin_id)
        self.changed.emit()

    @Slot(str)
    def chooseFile(self, _url: str) -> None:
        self.noticeRaised.emit(_NOT_IN_DEMO)

    @Slot()
    def confirmInstall(self) -> None:
        """Nothing is pending in the demo."""

    @Slot()
    def cancelInstall(self) -> None:
        """Nothing is pending in the demo."""

    @Slot()
    def dismissRefusal(self) -> None:
        """No refusal is shown in the demo."""

    @Slot(str)
    def install(self, _plugin_id: str) -> None:
        self.noticeRaised.emit(_NOT_IN_DEMO)

    @Slot(str)
    def update(self, _plugin_id: str) -> None:
        self.noticeRaised.emit(_NOT_IN_DEMO)

    @Slot()
    def checkMarketplace(self) -> None:
        """The demo list is always the same."""

    @Slot()
    def marketplaceRequested(self) -> None:
        """The demo list is always the same."""

    @Slot()
    def openPluginsFolder(self) -> None:
        self.noticeRaised.emit(_NOT_IN_DEMO)

    @Slot()
    def restartNow(self) -> None:
        self.noticeRaised.emit(_NOT_IN_DEMO)

    def _matches(self, row: dict[str, Any]) -> bool:
        query = self._search.strip().casefold()
        if not query:
            return True
        fields = (row["title"], row["description"], row.get("author", ""))
        return any(query in str(field).casefold() for field in fields)

    def _title_of(self, plugin_id: str) -> str:
        for row in (*self._installed, *_MARKETPLACE):
            if row["id"] == plugin_id:
                return str(row["title"])
        return ""
