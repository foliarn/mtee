"""A Plugins view whose state a test or a capture sets (plan 123.6).

It has the properties and slots of ``PluginsViewModel``, so the QML is the same. The rows default to
the invented plugins of the demo. Installs, downloads and removals change only these lists, the
same way the real view does after its jobs: a confirmed install clears the pending package, a
removed plugin leaves the installed list and waits for a restart.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.models import demo_workspace
from mtee.models.demo_plugins_view import _INSTALLED, _MARKETPLACE

__all__ = ["FakePluginsView", "use_fake_view"]

OFFICIAL = "foliarn/mtee-plugins"


def _market_row(row: dict[str, Any], address: str = OFFICIAL) -> dict[str, Any]:
    """A Marketplace row with its key and source, as the real view gives it."""
    copy = dict(row)
    copy.setdefault("key", f"{row['id']}@{address}")
    copy.setdefault("source", address)
    copy.setdefault("sourceTitle", "Official" if address == OFFICIAL else address)
    copy.setdefault("duplicate", False)
    return copy


def _installed_row(row: dict[str, Any], market: list[dict[str, Any]]) -> dict[str, Any]:
    """An installed row with the key of the Marketplace row that updates it."""
    copy = dict(row)
    offer = next((item["key"] for item in market if item["id"] == row["id"]), "")
    copy.setdefault("offerKey", offer)
    return copy


class FakePluginsView(QObject):
    """The Plugins view with a settable state; every slot call is kept in ``calls``."""

    changed = Signal()
    noticeRaised = Signal(str)
    detailRequested = Signal(str, str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        installed: Iterable[dict[str, Any]] | None = None,
        marketplace: Iterable[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._marketplace = [
            _market_row(row) for row in (_MARKETPLACE if marketplace is None else marketplace)
        ]
        self._installed = [
            _installed_row(row, self._marketplace)
            for row in (_INSTALLED if installed is None else installed)
        ]
        self._sources: list[dict[str, Any]] = [
            {"address": OFFICIAL, "title": OFFICIAL, "official": True, "enabled": True}
        ]
        self._add_error = ""
        self._state = "ready"
        self._error = ""
        self._search = ""
        self._restart: set[str] = {"convert"}
        self._pending: dict[str, Any] = {}
        self._refusal: dict[str, str] | None = None
        self.calls: list[tuple[Any, ...]] = []

    # ------------------------------------------------------------------ properties

    @Property(list, notify=changed)
    def installed(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._installed if self._matches(row)]

    @Property(list, notify=changed)
    def marketplace(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._marketplace if self._matches(row)]

    @Property(str, notify=changed)
    def marketplaceState(self) -> str:
        return self._state

    @Property(str, notify=changed)
    def marketplaceError(self) -> str:
        return self._error

    @Property(list, notify=changed)
    def marketplaces(self) -> list[dict[str, Any]]:
        return [dict(source) for source in self._sources]

    @Property(str, notify=changed)
    def marketplaceAddError(self) -> str:
        return self._add_error

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
        return bool(self._restart)

    @Property(str, notify=changed)
    def restartText(self) -> str:
        count = len(self._restart)
        if count == 0:
            return ""
        return "1 plugin needs a restart" if count == 1 else f"{count} plugins need a restart"

    @Property(dict, notify=changed)
    def pendingInstall(self) -> dict[str, Any]:
        return dict(self._pending)

    @Property(dict, notify=changed)
    def refusal(self) -> dict[str, Any]:
        return dict(self._refusal) if self._refusal is not None else {}

    # ------------------------------------------------------------------ slots

    @Slot(str)
    def openDetail(self, plugin_id: str) -> None:
        self.calls.append(("openDetail", plugin_id))
        title = self._title_of(plugin_id)
        if title:
            self.detailRequested.emit(plugin_id, title)

    @Slot(str, result=dict)
    def detail(self, key: str) -> dict[str, Any]:
        row = self._find(key)
        return dict(row) if row is not None else {}

    @Slot(str, result=bool)
    def addMarketplace(self, text: str) -> bool:
        self.calls.append(("addMarketplace", text))
        address = text.strip()
        if not address or any(source["address"] == address for source in self._sources):
            self._add_error = "This marketplace is already in the list."
            self.changed.emit()
            return False
        self._sources.append(
            {"address": address, "title": address, "official": False, "enabled": True}
        )
        self._add_error = ""
        self.changed.emit()
        return True

    @Slot(str)
    def removeMarketplace(self, address: str) -> None:
        self.calls.append(("removeMarketplace", address))
        if address != OFFICIAL:
            self._sources = [source for source in self._sources if source["address"] != address]
            self.changed.emit()

    @Slot(str, bool)
    def setMarketplaceEnabled(self, address: str, enabled: bool) -> None:
        self.calls.append(("setMarketplaceEnabled", address, bool(enabled)))
        for source in self._sources:
            if source["address"] == address:
                source["enabled"] = bool(enabled)
        self.changed.emit()

    @Slot()
    def clearMarketplaceAddError(self) -> None:
        self.calls.append(("clearMarketplaceAddError",))
        self._add_error = ""
        self.changed.emit()

    @Slot(str, bool)
    def setEnabled(self, plugin_id: str, enabled: bool) -> None:
        self.calls.append(("setEnabled", plugin_id, bool(enabled)))
        for row in self._installed:
            if row["id"] == plugin_id:
                row["enabled"] = bool(enabled)
                self._restart.add(plugin_id)
        self.changed.emit()

    @Slot(str)
    def uninstall(self, plugin_id: str) -> None:
        self.calls.append(("uninstall", plugin_id))
        self._installed = [row for row in self._installed if row["id"] != plugin_id]
        self._restart.add(plugin_id)
        self.changed.emit()

    @Slot(str)
    def chooseFile(self, url: str) -> None:
        self.calls.append(("chooseFile", url))

    @Slot()
    def confirmInstall(self) -> None:
        self.calls.append(("confirmInstall",))
        self._pending = {}
        self.changed.emit()

    @Slot()
    def cancelInstall(self) -> None:
        self.calls.append(("cancelInstall",))
        self._pending = {}
        self.changed.emit()

    @Slot()
    def dismissRefusal(self) -> None:
        self.calls.append(("dismissRefusal",))
        self._refusal = None
        self.changed.emit()

    @Slot(str)
    def install(self, plugin_id: str) -> None:
        self.calls.append(("install", plugin_id))

    @Slot(str)
    def update(self, plugin_id: str) -> None:
        self.calls.append(("update", plugin_id))

    @Slot()
    def checkMarketplace(self) -> None:
        self.calls.append(("checkMarketplace",))

    @Slot()
    def marketplaceRequested(self) -> None:
        self.calls.append(("marketplaceRequested",))

    @Slot()
    def openPluginsFolder(self) -> None:
        self.calls.append(("openPluginsFolder",))

    @Slot()
    def restartNow(self) -> None:
        self.calls.append(("restartNow",))

    # ------------------------------------------------------------------ test seams

    def set_marketplace(
        self, state: str, rows: Iterable[dict[str, Any]] | None = None, error: str = ""
    ) -> None:
        """Set the Marketplace state; ``rows`` replaces the list when given."""
        self._state = state
        self._error = error
        if rows is not None:
            self._marketplace = [dict(row) for row in rows]
        self.changed.emit()

    def set_pending(self, pending: dict[str, Any]) -> None:
        self._pending = dict(pending)
        self._refusal = None
        self.changed.emit()

    def set_refusal(self, title: str, text: str) -> None:
        self._refusal = {"title": title, "text": text}
        self.changed.emit()

    def set_restart(self, plugin_ids: Iterable[str]) -> None:
        self._restart = set(plugin_ids)
        self.changed.emit()

    def set_search(self, text: str) -> None:
        self.search = text

    # ------------------------------------------------------------------ internals

    def _matches(self, row: dict[str, Any]) -> bool:
        query = self._search.strip().casefold()
        if not query:
            return True
        fields = (row["title"], row["description"], row.get("author", ""))
        return any(query in str(field).casefold() for field in fields)

    def _title_of(self, key: str) -> str:
        row = self._find(key)
        return str(row["title"]) if row is not None else ""

    def _find(self, key: str) -> dict[str, Any] | None:
        """The row of a plugin id or key: the installed row of an id, else a Marketplace row."""
        plugin_id, _, address = key.partition("@")
        for row in self._installed:
            if row["id"] == plugin_id:
                return row
        if address:
            return next((row for row in self._marketplace if row["key"] == key), None)
        return next((row for row in self._marketplace if row["id"] == plugin_id), None)


def use_fake_view(monkeypatch: Any) -> None:
    """Make the demo workspace build a ``FakePluginsView`` instead of its own view.

    Call before the demo runtime is built: the QML reads ``workspace.pluginsView`` once, when the
    window loads, so the fake must be in place from the start.
    """
    monkeypatch.setattr(demo_workspace, "DemoPluginsView", FakePluginsView)
