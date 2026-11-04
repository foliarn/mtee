"""The Plugins view: installed plugins, the Marketplace, installs and restarts (plan 123.6).

QML reads the properties of ``PluginsViewModel`` and calls its slots; it never touches a file or a
network address. Every file, download and index read runs as a job, so it appears in the Tasks
window with progress and Cancel. Results return to the graphical thread through a signal.

A plugin's state is compared with a snapshot taken at start, when the plugins were loaded. A
plugin whose version or switch differs from that snapshot, or that is new, needs a restart and
has the status ``restart``. A plugin sent to the Recycle Bin is no longer listed, but it still
counts in ``restartNeeded``.
"""

from __future__ import annotations

import sys
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from mtee import __version__
from mtee.domain.job_summaries import fixed
from mtee.models.plugin_list import plugin_list_rows
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins import installer, marketplace
from mtee.plugins.api import SUPPORTED_API_VERSIONS
from mtee.plugins.loader import LoadedPlugin, PluginManager, PluginPreferences, PluginStatus
from mtee.plugins.marketplace import (
    MarketplaceCancelledError,
    MarketplaceEntry,
    MarketplaceError,
    MarketplaceIndex,
    MarketplaceVersion,
)
from mtee.plugins.package import (
    PYTHON_VERSION,
    PackageError,
    PluginDescription,
    mtee_runtime_libraries,
)
from mtee.services.jobs import JobContext, JobService
from mtee.services.platform.shell_reveal import WindowsShellReveal
from mtee.services.restart import restart_command, restart_environment, start_detached

__all__ = ["PluginsViewModel"]

Opener = Callable[..., Any]
# Where an installed plugin came from, kept in the settings: "file" or "marketplace".
SOURCE_SETTING_PREFIX = "plugin-source."
# The address of the marketplace a plugin was installed from; empty for a file.
ADDRESS_SETTING_PREFIX = "plugin-source-address."
# The marketplaces of the list, as a JSON list of {"address", "enabled"}.
MARKETPLACES_SETTING = "plugins.marketplaces"
PLATFORM = "win_amd64" if sys.platform == "win32" else "any"
MAX_README_CHARS = 200_000
_STATUS_TEXT = {
    "running": "Running",
    "disabled": "Disabled",
    "failed": "Failed",
    "restart": "Restart needed",
}


@dataclass(frozen=True, slots=True)
class _Pending:
    """A package checked and waiting for the user's confirmation."""

    path: Path
    source: str
    description: PluginDescription
    size: int
    # The address of the marketplace it was downloaded from; empty for a file.
    address: str = ""


@dataclass(frozen=True, slots=True)
class _SourceRead:
    """The result of reading one enabled marketplace: its list, or the one-sentence error."""

    address: str
    index: MarketplaceIndex | None
    error: str


class PluginsViewModel(QObject):
    """State and actions of the Plugins view; the lists are plain dicts for QML."""

    changed = Signal()
    noticeRaised = Signal(str)
    # The plugin id and its title: the workspace opens or focuses the plugin's detail tab.
    detailRequested = Signal(str, str)
    _onGui = Signal(object)

    def __init__(
        self,
        *,
        manager: PluginManager,
        preferences: PluginPreferences,
        settings: SettingsRepository,
        data_dir: Path,
        jobs: JobService,
        trash: installer.Trash,
        reveal: Callable[[Path], None] | None = None,
        restart: Callable[[], None] | None = None,
        quit_app: Callable[[], None] | None = None,
        opener: Opener | None = None,
        mtee_libraries: Mapping[str, str] | None = None,
        mtee_version: str = __version__,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._preferences = preferences
        self._settings = settings
        self._data_dir = data_dir
        self._jobs = jobs
        self._trash = trash
        self._opener = opener
        self._mtee_version = mtee_version
        self._libraries: dict[str, str] = dict(
            mtee_runtime_libraries() if mtee_libraries is None else mtee_libraries
        )
        self._clock = clock
        self._reveal: Callable[[Path], None] = reveal or WindowsShellReveal().open_folder
        self._restart: Callable[[], None] = restart or (
            lambda: start_detached(restart_command(), restart_environment())
        )
        self._quit: Callable[[], None] = quit_app or (lambda: None)
        self._search = ""
        self._marketplaces = self._load_marketplaces()
        # The lists read from the enabled marketplaces, in the order of the list, and the errors.
        self._indexes: list[tuple[str, MarketplaceIndex]] = []
        self._source_errors: dict[str, str] = {}
        self._market_state = "idle"
        self._market_error = ""
        # Set when the list of marketplaces changes while a read runs: the lists are read again.
        self._read_again = False
        self._add_error = ""
        self._checked_at: datetime | None = None
        self._refusal: dict[str, str] | None = None
        self._pending: _Pending | None = None
        self._installed_rows: list[dict[str, Any]] = []
        self._market_rows: list[dict[str, Any]] = []
        self._restart_ids: frozenset[str] = frozenset()
        # The snapshot of the start: what was loaded, the version on disk and the switch.
        self._started: dict[str, LoadedPlugin] = {
            record.plugin_id: record for record in manager.plugins
        }
        startup_disk = {found.plugin_id: found for found in installer.installed(data_dir)}
        self._started_versions: dict[str, str] = {}
        for plugin_id in set(self._started) | set(startup_disk):
            if plugin_id in startup_disk:
                self._started_versions[plugin_id] = startup_disk[plugin_id].description.version
            else:
                manifest = self._started[plugin_id].discovered.manifest
                self._started_versions[plugin_id] = manifest.version if manifest else ""
        self._started_enabled = set(preferences.enabled())
        self._onGui.connect(self._run_on_gui)
        self._refresh()

    # ------------------------------------------------------------------ properties

    @Property(list, notify=changed)
    def installed(self) -> list[dict[str, Any]]:
        """The plugins of the plugins folder and of the folders given for this run."""
        return [dict(row) for row in self._installed_rows if self._matches(row)]

    @Property(list, notify=changed)
    def marketplace(self) -> list[dict[str, Any]]:
        """The compatible plugins of the Marketplace list, in the order of the list."""
        return [dict(row) for row in self._market_rows if self._matches(row)]

    @Property(list, notify=changed)
    def plugins(self) -> list[dict[str, Any]]:
        """The one list of the view: installed and Marketplace plugins, each once (plan 132.6)."""
        installed = [dict(row) for row in self._installed_rows if self._matches(row)]
        market = [dict(row) for row in self._market_rows if self._matches(row)]
        listed = {entry.id for _, entry in self._offers()}
        return plugin_list_rows(installed, market, listed)

    @Property(str, notify=changed)
    def marketplaceState(self) -> str:
        return self._market_state

    @Property(str, notify=changed)
    def marketplaceError(self) -> str:
        return self._market_error

    @Property(list, notify=changed)
    def marketplaces(self) -> list[dict[str, Any]]:
        """The marketplaces of the list, the official one first, with the state of each read."""
        return [self._marketplace_info(item) for item in self._marketplaces]

    @Property(str, notify=changed)
    def marketplaceAddError(self) -> str:
        """The one-sentence reason the last added marketplace was refused, or an empty text."""
        return self._add_error

    @Property(str, notify=changed)
    def lastCheckedText(self) -> str:
        if self._checked_at is None:
            return ""
        seconds = int((self._clock() - self._checked_at).total_seconds())
        if seconds < 60:
            return "Last checked just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"Last checked {minutes} min ago"
        return f"Last checked {minutes // 60} h ago"

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
        """The package waiting for the warning's confirmation, or an empty dict."""
        pending = self._pending
        if pending is None:
            return {}
        description = pending.description
        if pending.source == "marketplace":
            source_text = (
                f"Downloaded from {_source_name(pending.address)}. Its file matched the list."
            )
        else:
            source_text = f"Local file: {pending.path.name}"
        return {
            "title": description.title,
            "version": description.version,
            "author": description.author,
            "sizeText": _size_text(pending.size),
            "usesNetwork": description.uses_network,
            "librariesCount": len(description.libraries),
            "source": pending.source,
            "sourceText": source_text,
            "sourceAddress": pending.address,
        }

    @Property(dict, notify=changed)
    def refusal(self) -> dict[str, str]:
        """The refused install as ``{title, text}``, or an empty dict when there is none.

        A ``dict`` property, not ``object``: QML reads the fields of a JavaScript object only.
        """
        return dict(self._refusal) if self._refusal is not None else {}

    # ------------------------------------------------------------------ slots

    @Slot(str)
    def openDetail(self, key: str) -> None:
        """Open, or focus, the detail tab of a plugin, given by its id or its key ``id@address``."""
        row = self._find_row(key)
        if row is not None:
            self.detailRequested.emit(key, str(row["title"]))

    @Slot(str, result=dict)
    def detail(self, key: str) -> dict[str, Any]:
        """The row of a plugin, given by its id or its key, or an empty dict.

        A plain id gives the installed plugin, or else its first Marketplace row. A key gives the
        installed plugin only when it was installed from that address; otherwise the Marketplace
        row of that key.
        """
        row = self._find_row(key)
        return dict(row) if row is not None else {}

    @Slot(str, bool)
    def setEnabled(self, plugin_id: str, enabled: bool) -> None:
        """Save the switch; the plugin starts or stops at the next start."""
        if any(row["id"] == plugin_id for row in self._installed_rows):
            self._preferences.set_enabled(plugin_id, enabled)
            self._refresh()

    @Slot(str)
    def uninstall(self, plugin_id: str) -> None:
        """Send the plugin folder to the Recycle Bin, without a prompt; its data stays."""
        title = self._title_of(plugin_id) or plugin_id
        data_dir = self._data_dir
        trash = self._trash
        preferences = self._preferences

        def task(context: JobContext) -> None:
            del context
            installer.uninstall(plugin_id, data_dir=data_dir, trash=trash, preferences=preferences)
            self._onGui.emit(self._refresh)

        self._jobs.submit(
            task,
            label=f"Uninstalling {title}",
            visible=True,
            summary=fixed(f"Plugin {title} uninstalled"),
        )

    @Slot(str)
    def chooseFile(self, url: str) -> None:
        """Check the package file chosen in the file dialog and wait for the confirmation."""
        path = Path(QUrl(url).toLocalFile())
        if not url or not path.name:
            return
        try:
            found = installer.inspect(
                path,
                installed=installer.installed(self._data_dir),
                mtee_version=self._mtee_version,
                mtee_libraries=self._libraries,
            )
        except (PackageError, OSError) as error:
            self._set_refusal(f"{path.stem} was not installed", str(error))
            return
        self._set_pending(_Pending(path, "file", found.description, found.size))

    @Slot()
    def confirmInstall(self) -> None:
        """Install the package that was checked and confirmed, as a job."""
        pending = self._pending
        if pending is None:
            return
        self._pending = None
        self.changed.emit()
        title = f"{pending.description.title} {pending.description.version}"
        data_dir = self._data_dir
        trash = self._trash
        preferences = self._preferences
        mtee_version = self._mtee_version
        libraries = dict(self._libraries)

        def task(context: JobContext) -> None:
            del context
            try:
                plugin = installer.install(
                    pending.path,
                    data_dir=data_dir,
                    trash=trash,
                    preferences=preferences,
                    mtee_version=mtee_version,
                    mtee_libraries=libraries,
                )
            except installer.InstallRefusedError as error:
                self._onGui.emit(
                    partial(self._set_refusal, f"{title} was not installed", str(error))
                )
                if pending.source == "marketplace":
                    pending.path.unlink(missing_ok=True)
                raise
            self._onGui.emit(
                partial(
                    self._installed, plugin.plugin_id, pending.source, pending.path, pending.address
                )
            )

        self._jobs.submit(
            task,
            label=f"Installing {title}",
            visible=True,
            summary=fixed(f"Plugin {title} installed"),
        )

    @Slot()
    def cancelInstall(self) -> None:
        """Forget the package that waits for confirmation."""
        self._drop_pending()
        self.changed.emit()

    @Slot()
    def dismissRefusal(self) -> None:
        self._refusal = None
        self.changed.emit()

    @Slot(str)
    def install(self, key: str) -> None:
        """Download a Marketplace plugin as a job; ``key`` is its id or its key ``id@address``."""
        self._download(key)

    @Slot(str)
    def update(self, key: str) -> None:
        """Download the newer Marketplace version of a plugin, as ``install`` does."""
        self._download(key)

    @Slot()
    def checkMarketplace(self) -> None:
        """Read the list of every enabled marketplace, as one job.

        Some lists failing is shown in ``marketplaceError``; the job fails only when all do.
        """
        if self._market_state == "loading":
            return
        self._market_state = "loading"
        self._market_error = ""
        self.changed.emit()
        opener = self._opener
        addresses = [item["address"] for item in self._marketplaces if item["enabled"]]

        def task(context: JobContext) -> None:
            del context
            reads = [_read_source(address, opener) for address in addresses]
            self._onGui.emit(partial(self._reads_done, reads))
            failed = [read for read in reads if read.index is None]
            if reads and len(failed) == len(reads):
                raise MarketplaceError(failed[0].error)

        self._jobs.submit(
            task,
            label="Reading the plugin list",
            visible=True,
            summary=fixed("Plugin list read"),
        )

    @Slot()
    def marketplaceRequested(self) -> None:
        """Called when the Marketplace is shown: the list is read once per session."""
        if self._market_state == "idle":
            self.checkMarketplace()

    @Slot(str, result=bool)
    def addMarketplace(self, text: str) -> bool:
        """Add a marketplace given as ``owner/repo``, a GitHub page or an https address.

        Return False and keep the reason in ``marketplaceAddError`` when it is refused.
        """
        try:
            address = marketplace.normalize_address(text)
        except MarketplaceError as error:
            self._add_error = str(error)
            self.changed.emit()
            return False
        if any(item["address"] == address for item in self._marketplaces):
            self._add_error = "This marketplace is already in the list."
            self.changed.emit()
            return False
        self._marketplaces.append({"address": address, "enabled": True})
        self._add_error = ""
        self._save_marketplaces()
        self._reread_marketplaces()
        self._refresh()
        return True

    @Slot(str)
    def removeMarketplace(self, address: str) -> None:
        """Remove a marketplace from the list. The official one is never removed."""
        if address == marketplace.OFFICIAL_ADDRESS:
            return
        self._marketplaces = [item for item in self._marketplaces if item["address"] != address]
        self._indexes = [(listed, index) for listed, index in self._indexes if listed != address]
        self._source_errors.pop(address, None)
        self._save_marketplaces()
        self._reread_marketplaces()
        self._refresh()

    @Slot(str, bool)
    def setMarketplaceEnabled(self, address: str, enabled: bool) -> None:
        """Switch a marketplace on or off; a disabled one is not read."""
        for item in self._marketplaces:
            if item["address"] == address:
                item["enabled"] = bool(enabled)
                self._save_marketplaces()
                self._reread_marketplaces()
                self._refresh()
                return

    @Slot()
    def clearMarketplaceAddError(self) -> None:
        if self._add_error:
            self._add_error = ""
            self.changed.emit()

    @Slot()
    def openPluginsFolder(self) -> None:
        folder = installer.plugins_folder(self._data_dir)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            self._reveal(folder)
        except OSError as error:
            self.noticeRaised.emit(f"The plugins folder could not be opened: {error}")

    @Slot()
    def restartNow(self) -> None:
        """Start MTEE again with the same arguments, then quit through the normal path."""
        try:
            self._restart()
        except OSError as error:
            self.noticeRaised.emit(f"MTEE could not restart: {error}")
            return
        self._quit()

    # ------------------------------------------------------------------ internals

    @Slot(object)
    def _run_on_gui(self, call: object) -> None:
        if callable(call):
            call()

    def _matches(self, row: Mapping[str, Any]) -> bool:
        query = self._search.strip().casefold()
        if not query:
            return True
        fields = (row["title"], row["description"], row["author"])
        return any(query in str(field).casefold() for field in fields)

    def _title_of(self, plugin_id: str) -> str:
        row = self._find_row(plugin_id)
        return str(row["title"]) if row is not None else ""

    def _find_row(self, key: str) -> dict[str, Any] | None:
        """The row a plugin id or key stands for; see ``detail`` for the rules."""
        plugin_id, address = _split_key(key)
        installed = next((row for row in self._installed_rows if row["id"] == plugin_id), None)
        if installed is not None and (not address or self._source_address(plugin_id) == address):
            return installed
        if address:
            return next((row for row in self._market_rows if row["key"] == key), None)
        return next((row for row in self._market_rows if row["id"] == plugin_id), None)

    def _marketplace_info(self, item: Mapping[str, Any]) -> dict[str, Any]:
        address = str(item["address"])
        return {
            "address": address,
            "title": address,
            "official": address == marketplace.OFFICIAL_ADDRESS,
            "enabled": bool(item["enabled"]),
            "stateText": self._state_text(address),
        }

    def _state_text(self, address: str) -> str:
        """The result of the last read of a marketplace: its plugin count or its error."""
        if address in self._source_errors:
            return self._source_errors[address]
        for listed, index in self._indexes:
            if listed == address:
                return _plugins_text(len(index.entries))
        return ""

    def _load_marketplaces(self) -> list[dict[str, Any]]:
        """The stored list, with the official marketplace first; it is added when missing."""
        stored = self._settings.get_json(MARKETPLACES_SETTING, None)
        listed: list[dict[str, Any]] = []
        for item in stored if isinstance(stored, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("address"), str):
                continue
            address = item["address"]
            if address and all(address != known["address"] for known in listed):
                listed.append({"address": address, "enabled": bool(item.get("enabled", True))})
        official = next(
            (item for item in listed if item["address"] == marketplace.OFFICIAL_ADDRESS), None
        )
        if official is None:
            official = {"address": marketplace.OFFICIAL_ADDRESS, "enabled": True}
        else:
            listed.remove(official)
        return [official, *listed]

    def _save_marketplaces(self) -> None:
        self._settings.set_json(MARKETPLACES_SETTING, self._marketplaces)

    def _reread_marketplaces(self) -> None:
        """Read the lists again after the marketplaces changed, when they were read before."""
        if self._market_state == "loading":
            self._read_again = True
        elif self._market_state != "idle":
            self.checkMarketplace()

    def _current_sources(self) -> list[tuple[str, MarketplaceIndex]]:
        """The lists read from the marketplaces that are enabled now, in the order of the list."""
        enabled = {item["address"] for item in self._marketplaces if item["enabled"]}
        return [(address, index) for address, index in self._indexes if address in enabled]

    def _offers(self) -> list[tuple[str, MarketplaceEntry]]:
        """Every plugin of the current sources, with the address it comes from."""
        return [
            (address, entry)
            for address, index in self._current_sources()
            for entry in index.entries
        ]

    def _source_address(self, plugin_id: str) -> str:
        """The address a plugin was installed from, or an empty text when it was not."""
        if self._settings.get(f"{SOURCE_SETTING_PREFIX}{plugin_id}", "") != "marketplace":
            return ""
        address = self._settings.get(f"{ADDRESS_SETTING_PREFIX}{plugin_id}", "") or ""
        # An install made before the addresses were kept came from the official list.
        return address or marketplace.OFFICIAL_ADDRESS

    def _offer_for(self, plugin_id: str, source: str) -> tuple[str, MarketplaceEntry] | None:
        """The offer of a plugin: from ``source`` when it offers the id, else the first source."""
        offers = self._offers()
        if source:
            preferred = next(
                (offer for offer in offers if offer[0] == source and offer[1].id == plugin_id),
                None,
            )
            if preferred is not None:
                return preferred
        return next((offer for offer in offers if offer[1].id == plugin_id), None)

    def _resolve_offer(self, key: str) -> tuple[str, MarketplaceEntry] | None:
        """The offer a key stands for; a plain id uses the source of the installed plugin."""
        plugin_id, address = _split_key(key)
        if address:
            return next(
                (
                    offer
                    for offer in self._offers()
                    if offer[0] == address and offer[1].id == plugin_id
                ),
                None,
            )
        installed = any(row["id"] == plugin_id for row in self._installed_rows)
        return self._offer_for(plugin_id, self._source_address(plugin_id) if installed else "")

    def _is_offer(self, address: str, plugin_id: str) -> bool:
        """Whether the offer of a plugin that comes from ``address`` is the one that updates it."""
        offer = self._offer_for(plugin_id, self._source_address(plugin_id))
        return offer is not None and offer[0] == address

    def _refresh(self) -> None:
        """Read the plugins folder and rebuild every list; called after each change."""
        disk = {found.plugin_id: found for found in installer.installed(self._data_dir)}
        root = installer.plugins_folder(self._data_dir)
        uninstalled = {
            plugin_id
            for plugin_id in self._started_versions
            if plugin_id not in disk and self._folder_removed(plugin_id, root)
        }
        restart = set(uninstalled)
        rows: list[dict[str, Any]] = []
        for plugin_id in sorted((set(disk) | set(self._started_versions)) - uninstalled):
            found = disk.get(plugin_id)
            record = self._started.get(plugin_id)
            enabled = self._preferences.is_enabled(plugin_id)
            changed = self._changed(plugin_id, found, enabled)
            if changed:
                restart.add(plugin_id)
            status, error = self._status(record, changed)
            rows.append(self._installed_row(plugin_id, found, record, status, error, enabled))
        rows.sort(key=lambda row: str(row["title"]).casefold())
        self._installed_rows = rows
        self._restart_ids = frozenset(restart)
        self._market_rows = self._marketplace_rows(disk)
        self.changed.emit()

    def _folder_removed(self, plugin_id: str, root: Path) -> bool:
        """Whether a plugin of the plugins folder that was loaded at start has been removed."""
        record = self._started.get(plugin_id)
        if record is None:
            return True
        # A folder given with --plugin-dir is not in the plugins folder: it is never removed here.
        return record.discovered.folder.parent == root and not record.discovered.folder.exists()

    def _changed(
        self, plugin_id: str, found: installer.InstalledPlugin | None, enabled: bool
    ) -> bool:
        """Whether the plugin differs from the snapshot of the start; a new one always does."""
        started_version = self._started_versions.get(plugin_id)
        if started_version is None:
            return True
        now_version = found.description.version if found is not None else started_version
        return now_version != started_version or enabled != (plugin_id in self._started_enabled)

    @staticmethod
    def _status(record: LoadedPlugin | None, changed: bool) -> tuple[str, str]:
        """Return the status key and the error sentence of a plugin."""
        if changed:
            return "restart", ""
        if record is None:
            return "failed", "The plugin folder holds no plugin package."
        if not record.discovered.is_valid:
            return "failed", record.discovered.error
        if record.status is PluginStatus.FAILED:
            return "failed", record.error
        if record.status is PluginStatus.RUNNING:
            return "running", ""
        return "disabled", ""

    def _installed_row(
        self,
        plugin_id: str,
        found: installer.InstalledPlugin | None,
        record: LoadedPlugin | None,
        status: str,
        error: str,
        enabled: bool,
    ) -> dict[str, Any]:
        manifest = record.discovered.manifest if record is not None else None
        folder: Path | None
        if found is not None:
            description = found.description
            title, version, author = description.title, description.version, description.author
            text, network = description.description, description.uses_network
            licence, homepage = description.licence, description.homepage
            libraries = len(description.libraries)
            folder = found.folder
        else:
            title = manifest.title if manifest is not None else plugin_id
            version = manifest.version if manifest is not None else ""
            author, licence, homepage = "", "", ""
            text = manifest.description if manifest is not None else ""
            network = manifest.uses_network if manifest is not None else False
            libraries = 0
            folder = record.discovered.package_dir if record is not None else None
        readme = _read_text(folder / "README.md") if folder is not None else ""
        update = ""
        offer_key = ""
        offer = self._offer_for(plugin_id, self._source_address(plugin_id))
        if offer is not None:
            offer_address, entry = offer
            offer_key = _key(entry.id, offer_address)
            if found is not None:
                candidate = self._update_of(entry, found.description.version)
                update = candidate.version if candidate is not None else ""
        installed_from = self._settings.get(f"{SOURCE_SETTING_PREFIX}{plugin_id}", "") or ""
        return {
            "id": plugin_id,
            "title": title,
            "version": version,
            "author": author,
            "description": text,
            "letter": _letter(title, plugin_id),
            "status": status,
            "statusText": _STATUS_TEXT[status],
            "error": error,
            "usesNetwork": bool(network),
            "enabled": enabled,
            "updateVersion": update,
            "offerKey": offer_key,
            "librariesCount": libraries,
            "licence": licence,
            "homepage": homepage,
            "installedFrom": installed_from,
            "readme": readme,
        }

    def _marketplace_rows(
        self, disk: Mapping[str, installer.InstalledPlugin]
    ) -> list[dict[str, Any]]:
        """One row per plugin and source, the sources in the order of the list."""
        sources = self._current_sources()
        # A plugin offered by more than one source is shown once per source, and marked.
        offered = Counter(entry.id for _, index in sources for entry in index.entries)
        rows: list[dict[str, Any]] = []
        for address, index in sources:
            for entry in index.entries:
                candidate = self._candidate(entry)
                if candidate is None:
                    continue
                found = disk.get(entry.id)
                if found is None:
                    state, version, installed_version = "install", candidate.version, ""
                else:
                    installed_version = found.description.version
                    update = (
                        self._update_of(entry, installed_version)
                        if self._is_offer(address, entry.id)
                        else None
                    )
                    if update is not None:
                        state, version = "update", update.version
                    else:
                        state, version = "installed", installed_version
                rows.append(
                    {
                        "id": entry.id,
                        "key": _key(entry.id, address),
                        "source": address,
                        "sourceTitle": _source_title(address),
                        "duplicate": offered[entry.id] > 1,
                        "title": entry.title,
                        "version": version,
                        "author": entry.author,
                        "description": entry.description,
                        "letter": _letter(entry.title, entry.id),
                        "usesNetwork": entry.uses_network,
                        "state": state,
                        "installedVersion": installed_version,
                    }
                )
        return rows

    def _candidate(self, entry: MarketplaceEntry) -> MarketplaceVersion | None:
        return marketplace.compatible_version(
            entry,
            mtee_version=self._mtee_version,
            api_versions=SUPPORTED_API_VERSIONS,
            python=PYTHON_VERSION,
            platform=PLATFORM,
        )

    def _update_of(
        self, entry: MarketplaceEntry, installed_version: str
    ) -> MarketplaceVersion | None:
        return marketplace.available_update(
            entry,
            installed_version,
            mtee_version=self._mtee_version,
            api_versions=SUPPORTED_API_VERSIONS,
            python=PYTHON_VERSION,
            platform=PLATFORM,
        )

    def _download(self, key: str) -> None:
        plugin_id, _ = _split_key(key)
        offer = self._resolve_offer(key)
        if offer is None:
            self._set_refusal(
                f"{plugin_id} was not installed",
                "The plugin is not in the plugin list. Read the list again and retry.",
            )
            return
        address, entry = offer
        candidate = self._candidate(entry)
        if candidate is None:
            self._set_refusal(
                f"{entry.title} was not installed",
                "The plugin list has no version of it that this MTEE can install.",
            )
            return
        title = f"{entry.title} {candidate.version}"
        data_dir = self._data_dir
        opener = self._opener
        mtee_version = self._mtee_version
        libraries = dict(self._libraries)

        def task(context: JobContext) -> None:
            path: Path | None = None

            def progress(done: int, size: int) -> None:
                context.report_progress(done / size if size else 1.0)

            try:
                path = marketplace.download(
                    entry,
                    candidate,
                    data_dir=data_dir,
                    opener=opener,
                    progress=progress,
                    cancelled=lambda: context.is_cancelled,
                )
                found = installer.inspect(
                    path,
                    installed=installer.installed(data_dir),
                    mtee_version=mtee_version,
                    mtee_libraries=libraries,
                )
            except MarketplaceCancelledError:
                context.raise_if_cancelled()
                raise
            except (MarketplaceError, PackageError, OSError) as error:
                if path is not None:
                    path.unlink(missing_ok=True)
                self._onGui.emit(
                    partial(self._set_refusal, f"{title} was not installed", str(error))
                )
                raise
            self._onGui.emit(
                partial(
                    self._set_pending,
                    _Pending(path, "marketplace", found.description, found.size, address),
                )
            )

        self._jobs.submit(
            task,
            label=f"Downloading {title}",
            visible=True,
            summary=fixed(f"{title} downloaded"),
        )

    def _installed(self, plugin_id: str, source: str, package: Path, address: str) -> None:
        self._settings.set(f"{SOURCE_SETTING_PREFIX}{plugin_id}", source)
        self._settings.set(
            f"{ADDRESS_SETTING_PREFIX}{plugin_id}", address if source == "marketplace" else ""
        )
        if source == "marketplace":
            package.unlink(missing_ok=True)
        self._refresh()

    def _reads_done(self, reads: list[_SourceRead]) -> None:
        """Keep the result of each read; the state is failed only when every list failed."""
        self._indexes = [(read.address, read.index) for read in reads if read.index is not None]
        self._source_errors = {read.address: read.error for read in reads if read.index is None}
        failed = len(self._source_errors)
        if reads and failed == len(reads):
            self._market_state = "failed"
            self._market_error = reads[0].error
        else:
            self._market_state = "ready"
            self._market_error = (
                f"{failed} of {len(reads)} plugin lists could not be read. See Settings > Plugins."
                if failed
                else ""
            )
        self._checked_at = self._clock()
        self._refresh()
        if self._read_again:
            self._read_again = False
            self.checkMarketplace()

    def _set_pending(self, pending: _Pending) -> None:
        self._drop_pending()
        self._refusal = None
        self._pending = pending
        self.changed.emit()

    def _drop_pending(self) -> None:
        """Forget the waiting package. A downloaded copy is removed: it can be fetched again."""
        pending = self._pending
        self._pending = None
        if pending is not None and pending.source == "marketplace":
            pending.path.unlink(missing_ok=True)

    def _set_refusal(self, title: str, text: str) -> None:
        self._refusal = {"title": title, "text": text}
        self.changed.emit()


def _size_text(size: int) -> str:
    if size < 1024 * 1024:
        return f"{max(1, round(size / 1024))} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _key(plugin_id: str, address: str) -> str:
    """The key of a plugin offered by a marketplace: ``id@address``."""
    return f"{plugin_id}@{address}"


def _split_key(key: str) -> tuple[str, str]:
    """Split a plugin id or a key at its first ``@``; a plain id has no address.

    Plugin ids never contain ``@``, so the address keeps any ``@`` after the first one.
    """
    plugin_id, separator, address = key.partition("@")
    return plugin_id, (address if separator else "")


def _source_title(address: str) -> str:
    """The short name of a marketplace in a list: ``Official`` or its address."""
    return "Official" if address == marketplace.OFFICIAL_ADDRESS else address


def _source_name(address: str) -> str:
    """The name of a marketplace in a sentence."""
    if address == marketplace.OFFICIAL_ADDRESS:
        return "the official MTEE plugin list"
    return address


def _plugins_text(count: int) -> str:
    return "1 plugin" if count == 1 else f"{count} plugins"


def _read_source(address: str, opener: Opener | None) -> _SourceRead:
    """Read the list of one marketplace; a failure is kept as its one-sentence error."""
    try:
        index = marketplace.fetch_index(marketplace.index_url(address), opener=opener)
    except MarketplaceError as error:
        return _SourceRead(address, None, str(error))
    return _SourceRead(address, index, "")


def _letter(title: str, plugin_id: str) -> str:
    source = title.strip() or plugin_id
    return source[:1].upper()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:MAX_README_CHARS]
    except OSError:
        return ""
