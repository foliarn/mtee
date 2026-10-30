"""The Plugins view: installed plugins, the Marketplace, installs and restarts (plan 123.6).

QML reads the properties of ``PluginsViewModel`` and calls its slots; it never touches a file or a
network address. Every file, download and index read runs as a job, so it appears in Tasks with
progress and Cancel. Results return to the graphical thread through a signal.

A plugin's state is compared with a snapshot taken at start, when the plugins were loaded. A
plugin whose version or switch differs from that snapshot, or that is new, needs a restart and
has the status ``restart``. A plugin sent to the Recycle Bin is no longer listed, but it still
counts in ``restartNeeded``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from mtee import __version__
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
        self._index: MarketplaceIndex | None = None
        self._market_state = "idle"
        self._market_error = ""
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

    @Property(str, notify=changed)
    def marketplaceState(self) -> str:
        return self._market_state

    @Property(str, notify=changed)
    def marketplaceError(self) -> str:
        return self._market_error

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
            source_text = "Downloaded from the MTEE plugin list. Its file matched the list."
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
        }

    @Property(object, notify=changed)
    def refusal(self) -> Any:
        """The refused install as ``{title, text}``, or an empty string when there is none."""
        return dict(self._refusal) if self._refusal is not None else ""

    # ------------------------------------------------------------------ slots

    @Slot(str)
    def openDetail(self, plugin_id: str) -> None:
        """Open, or focus, the detail tab of a plugin."""
        title = self._title_of(plugin_id)
        if title:
            self.detailRequested.emit(plugin_id, title)

    @Slot(str, result=dict)
    def detail(self, plugin_id: str) -> dict[str, Any]:
        """The row of an installed plugin, or of a Marketplace plugin, or an empty dict."""
        for row in (*self._installed_rows, *self._market_rows):
            if row["id"] == plugin_id:
                return dict(row)
        return {}

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

        self._jobs.submit(task, label=f"Uninstalling {title}", visible=True)

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
                partial(self._installed, plugin.plugin_id, pending.source, pending.path)
            )

        self._jobs.submit(task, label=f"Installing {title}", visible=True)

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
    def install(self, plugin_id: str) -> None:
        """Download a Marketplace plugin as a job; then the warning asks for the install."""
        self._download(plugin_id)

    @Slot(str)
    def update(self, plugin_id: str) -> None:
        """Download the newer Marketplace version of a plugin, as ``install`` does."""
        self._download(plugin_id)

    @Slot()
    def checkMarketplace(self) -> None:
        """Read the plugin list again, as a job; a failure is one sentence."""
        if self._market_state == "loading":
            return
        self._market_state = "loading"
        self._market_error = ""
        self.changed.emit()
        opener = self._opener

        def task(context: JobContext) -> None:
            del context
            try:
                index = marketplace.fetch_index(opener=opener)
            except MarketplaceError as error:
                self._onGui.emit(partial(self._index_failed, str(error)))
                raise
            self._onGui.emit(partial(self._index_loaded, index))

        self._jobs.submit(task, label="Reading the plugin list", visible=True)

    @Slot()
    def marketplaceRequested(self) -> None:
        """Called when the Marketplace is shown: the list is read once per session."""
        if self._market_state == "idle":
            self.checkMarketplace()

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
        for row in (*self._installed_rows, *self._market_rows):
            if row["id"] == plugin_id:
                return str(row["title"])
        return ""

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
        if found is not None:
            entry = self._entry(plugin_id)
            if entry is not None:
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
            "librariesCount": libraries,
            "licence": licence,
            "homepage": homepage,
            "installedFrom": installed_from,
            "readme": readme,
        }

    def _marketplace_rows(
        self, disk: Mapping[str, installer.InstalledPlugin]
    ) -> list[dict[str, Any]]:
        if self._index is None:
            return []
        rows: list[dict[str, Any]] = []
        for entry in self._index.entries:
            candidate = self._candidate(entry)
            if candidate is None:
                continue
            found = disk.get(entry.id)
            if found is None:
                state, version, installed_version = "install", candidate.version, ""
            else:
                installed_version = found.description.version
                update = self._update_of(entry, installed_version)
                if update is not None:
                    state, version = "update", update.version
                else:
                    state, version = "installed", installed_version
            rows.append(
                {
                    "id": entry.id,
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

    def _entry(self, plugin_id: str) -> MarketplaceEntry | None:
        if self._index is None:
            return None
        return next((entry for entry in self._index.entries if entry.id == plugin_id), None)

    def _download(self, plugin_id: str) -> None:
        entry = self._entry(plugin_id)
        if entry is None:
            self._set_refusal(
                f"{plugin_id} was not installed",
                "The plugin is not in the plugin list. Read the list again and retry.",
            )
            return
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
                    _Pending(path, "marketplace", found.description, found.size),
                )
            )

        self._jobs.submit(task, label=f"Downloading {title}", visible=True)

    def _installed(self, plugin_id: str, source: str, package: Path) -> None:
        self._settings.set(f"{SOURCE_SETTING_PREFIX}{plugin_id}", source)
        if source == "marketplace":
            package.unlink(missing_ok=True)
        self._refresh()

    def _index_loaded(self, index: MarketplaceIndex) -> None:
        self._index = index
        self._market_state = "ready"
        self._market_error = ""
        self._checked_at = self._clock()
        self._refresh()

    def _index_failed(self, text: str) -> None:
        self._market_state = "failed"
        self._market_error = text
        self._checked_at = self._clock()
        self.changed.emit()

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


def _letter(title: str, plugin_id: str) -> str:
    source = title.strip() or plugin_id
    return source[:1].upper()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:MAX_README_CHARS]
    except OSError:
        return ""
