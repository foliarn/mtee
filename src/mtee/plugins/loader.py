"""Discovery and lifecycle of the plugins in the plugin folders.

Plugins are loaded from the plugins folder ``<data-dir>/plugins/<id>/`` of each installed plugin,
and from the folders given with ``--plugin-dir`` for one run. A plugin folder holds plugin
packages: ``<folder>/<id>/manifest.py`` and ``__init__.py``. Discovery imports only the
``manifest.py`` of each package, never the package itself, so the code of a plugin runs only once
it is enabled.

``PluginManager`` then loads the enabled plugins after the core services: it chooses the shared
libraries, applies the plugin's migrations, runs its factory and reads its contributions. A plugin
that fails in any of these steps is marked ``Failed`` alone; the application keeps starting.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import logging
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

import mtee.plugins
from mtee.persistence.database import DatabaseError, discover_migrations
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import (
    SUPPORTED_API_VERSIONS,
    Contribution,
    PluginContext,
    PluginManifest,
    PluginService,
)
from mtee.plugins.contributions import check_contributions
from mtee.plugins.libraries import LibraryUser, install_finder, plan_libraries, uninstall_finder
from mtee.plugins.package import (
    LIBS_DIRECTORY,
    PLUGIN_JSON,
    PackageError,
    PluginDescription,
    description_matches_manifest,
)
from mtee.plugins.registry import bundled_plugins

__all__ = [
    "MANIFEST_ATTRIBUTE",
    "MANIFEST_FILE",
    "MIGRATIONS_DIRECTORY",
    "SETTING_ENABLED",
    "DiscoveredPlugin",
    "LoadedPlugin",
    "PluginManager",
    "PluginPreferences",
    "PluginStatus",
    "add_to_package_path",
    "discover",
    "plugin_id_problem",
    "remove_from_package_path",
]

_LOGGER = logging.getLogger(__name__)
MIGRATIONS_DIRECTORY = "migrations"

MANIFEST_FILE = "manifest.py"
MANIFEST_ATTRIBUTE = "MANIFEST"
SETTING_ENABLED = "plugins.enabled"
_PLUGIN_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_FACTORY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class DiscoveredPlugin:
    """One plugin package found in a plugin folder; ``error`` says why a manifest is refused."""

    plugin_id: str
    folder: Path
    package_dir: Path
    manifest: PluginManifest | None
    error: str = ""
    # The plugin.json of the folder, when it describes this package (an installed plugin).
    declared: PluginDescription | None = None

    @property
    def is_valid(self) -> bool:
        """Return whether the manifest was accepted."""
        return self.manifest is not None and not self.error


class PluginPreferences:
    """The enabled plugins, kept in the application settings."""

    def __init__(self, settings: SettingsRepository) -> None:
        self._settings = settings

    def enabled(self) -> list[str]:
        """Return the identifiers of the plugins the user switched on."""
        return self._stored_list(SETTING_ENABLED)

    def is_enabled(self, plugin_id: str) -> bool:
        return plugin_id in self.enabled()

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        """Switch a plugin on or off; the change applies at the next start."""
        current = self.enabled()
        wanted = [*current, plugin_id] if enabled and plugin_id not in current else current
        if not enabled:
            wanted = [value for value in current if value != plugin_id]
        if wanted != current:
            self._settings.set_json(SETTING_ENABLED, wanted)

    def _stored_list(self, key: str) -> list[str]:
        """Return the strings stored for ``key``; a value of another shape reads as empty."""
        stored = self._settings.get_json(key, [])
        if not isinstance(stored, list):
            return []
        return [value for value in stored if isinstance(value, str) and value]


def discover(folders: Sequence[Path]) -> list[DiscoveredPlugin]:
    """List the plugin packages found in ``folders`` and read their manifests.

    Only the direct children that hold a ``manifest.py`` are listed. A folder that does
    not exist is skipped. A refused manifest is
    returned with its reason; the first plugin found keeps an identifier that appears twice.
    A folder that holds a ``plugin.json`` (an unpacked package) refuses every plugin whose
    manifest disagrees with it on id, version or interface version.
    """
    found: list[DiscoveredPlugin] = []
    seen: dict[str, Path] = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        try:
            children = sorted(folder.iterdir(), key=lambda path: path.name)
        except OSError as error:
            _LOGGER.warning("Plugin folder %s cannot be read: %s", folder, error)
            continue
        declared, declared_error = _read_declared(folder)
        for package_dir in children:
            if not (package_dir / MANIFEST_FILE).is_file():
                continue
            plugin = _against_declared(_inspect(folder, package_dir), declared, declared_error)
            if plugin.is_valid and plugin.plugin_id in seen:
                plugin = _refused(
                    folder,
                    package_dir,
                    f"Another plugin folder already provides {plugin.plugin_id} "
                    f"({seen[plugin.plugin_id]}).",
                )
            elif plugin.is_valid:
                seen[plugin.plugin_id] = package_dir
            found.append(plugin)
    return found


def add_to_package_path(folder: Path) -> None:
    """Let ``mtee.plugins.<id>`` be imported from ``folder``, after the core's own folder."""
    entry = str(folder)
    if entry not in mtee.plugins.__path__:
        mtee.plugins.__path__.append(entry)


def remove_from_package_path(folder: Path) -> None:
    """Undo ``add_to_package_path``."""
    entry = str(folder)
    if entry in mtee.plugins.__path__:
        mtee.plugins.__path__.remove(entry)


class PluginStatus(StrEnum):
    """The state shown for a plugin in Settings > Plugins."""

    DISABLED = "Disabled"
    RUNNING = "Running"
    FAILED = "Failed"


@dataclass(slots=True)
class LoadedPlugin:
    """A discovered plugin with its state; ``error`` is the readable reason of a failure."""

    discovered: DiscoveredPlugin
    status: PluginStatus
    error: str = ""
    service: PluginService | None = None
    contributions: tuple[Contribution, ...] = ()

    @property
    def plugin_id(self) -> str:
        return self.discovered.plugin_id

    @property
    def title(self) -> str:
        manifest = self.discovered.manifest
        return manifest.title if manifest is not None else self.discovered.plugin_id


ContextFactory = Callable[[PluginManifest], PluginContext]


class PluginManager:
    """Loads the enabled plugins of the plugin folders and unloads them on exit.

    The enabled list comes from ``PluginPreferences``. A plugin is switched on or off in the
    preferences and the change applies at the next start.
    """

    def __init__(
        self, preferences: PluginPreferences, *, notify: Callable[[str], None] | None = None
    ) -> None:
        self._preferences = preferences
        self._notify = notify
        self._plugins: list[LoadedPlugin] = []
        self._path_entries: list[Path] = []
        self._library_locations: dict[str, Path] = {}

    @property
    def plugins(self) -> list[LoadedPlugin]:
        """Every plugin found in the last ``load_enabled``, with its state."""
        return list(self._plugins)

    @property
    def library_locations(self) -> dict[str, Path]:
        """The chosen copy of each shared top-level module: its ``libs/`` folder.

        A helper process reads this mapping to put the same copies on its own path.
        """
        return dict(self._library_locations)

    def load_enabled(
        self, context_factory: ContextFactory, folders: Sequence[Path]
    ) -> list[LoadedPlugin]:
        """Discover the plugins in ``folders``, load those the user enabled, and return all of them.

        The shared libraries of the plugins that will load are chosen, and their import finder
        is installed, before any factory is imported. A plugin that cannot share a library is
        marked ``Failed`` and not loaded. The failure of one plugin is stored on it, logged, and
        announced in one notice that names it; the others load as usual.
        """
        self.unload_all()
        discovered = discover(folders)
        enabled = set(self._preferences.enabled())
        wanted = [
            plugin for plugin in discovered if plugin.is_valid and plugin.plugin_id in enabled
        ]
        plan = plan_libraries(_library_users(wanted))
        install_finder(plan.locations)
        self._library_locations = dict(plan.locations)
        self._plugins = []
        failed: list[LoadedPlugin] = []
        for plugin in discovered:
            record = self._record(plugin, enabled, plan.refused, context_factory)
            if record.status is PluginStatus.FAILED and plugin.plugin_id in enabled:
                failed.append(record)
            self._plugins.append(record)
        self._announce(failed)
        return self.plugins

    def unload_all(self) -> None:
        """Unload the running plugins, newest first, and forget their modules.

        A plugin that fails to unload is logged and does not stop the others. Data stays.
        """
        for record in reversed(self._plugins):
            if record.service is not None:
                self._release(record)
                record.status = PluginStatus.DISABLED
            record.service = None
            record.contributions = ()
        for folder in self._path_entries:
            remove_from_package_path(folder)
        self._path_entries = []
        self._library_locations = {}
        uninstall_finder()

    def _record(
        self,
        plugin: DiscoveredPlugin,
        enabled: set[str],
        refused: Mapping[str, str],
        context_factory: ContextFactory,
    ) -> LoadedPlugin:
        """Return the state of one discovered plugin, loading it when it is enabled."""
        if not plugin.is_valid:
            _LOGGER.warning("Plugin %s refused: %s", plugin.plugin_id, plugin.error)
            return LoadedPlugin(plugin, PluginStatus.FAILED, plugin.error)
        if plugin.plugin_id not in enabled:
            return LoadedPlugin(plugin, PluginStatus.DISABLED)
        if plugin.plugin_id in refused:
            _LOGGER.error("Plugin %s not loaded: %s", plugin.plugin_id, refused[plugin.plugin_id])
            return LoadedPlugin(plugin, PluginStatus.FAILED, refused[plugin.plugin_id])
        return self._load(plugin, context_factory)

    def _load(self, discovered: DiscoveredPlugin, context_factory: ContextFactory) -> LoadedPlugin:
        """Run the migrations, the factory and ``contributions()`` of one plugin."""
        manifest = discovered.manifest
        assert manifest is not None  # a valid plugin always has its manifest
        record = LoadedPlugin(discovered, PluginStatus.FAILED)
        service: PluginService | None = None
        try:
            add_to_package_path(discovered.folder)
            if discovered.folder not in self._path_entries:
                self._path_entries.append(discovered.folder)
            importlib.invalidate_caches()
            context = context_factory(manifest)
            migrations = discovered.package_dir / MIGRATIONS_DIRECTORY
            if migrations.is_dir():
                context.database.migrate_plugin(manifest.plugin_id, discover_migrations(migrations))
            module_name, _, function_name = manifest.factory.partition(":")
            factory = getattr(importlib.import_module(module_name), function_name)
            service = factory(context)
            record.contributions = _read_contributions(manifest.plugin_id, service)
        except Exception as error:
            _LOGGER.error("Plugin %s failed to load.", manifest.plugin_id, exc_info=error)
            record.error = _describe(error)
            record.contributions = ()
            if service is not None:
                self._release_service(manifest.plugin_id, service)
            _forget_modules(manifest.plugin_id)
        else:
            record.status = PluginStatus.RUNNING
            record.service = service
        return record

    def _release(self, record: LoadedPlugin) -> None:
        if record.service is not None:
            self._release_service(record.plugin_id, record.service)
        _forget_modules(record.plugin_id)

    @staticmethod
    def _release_service(plugin_id: str, service: PluginService) -> None:
        try:
            service.unload()
        except Exception as error:
            _LOGGER.error("Plugin %s did not unload cleanly.", plugin_id, exc_info=error)

    def _announce(self, failed: list[LoadedPlugin]) -> None:
        """Show one notice for the plugins that could not start."""
        if not failed or self._notify is None:
            return
        if len(failed) == 1:
            record = failed[0]
            self._notify(
                f"The plugin {record.title} could not start and is disabled: {record.error}"
            )
            return
        names = ", ".join(record.title for record in failed)
        self._notify(
            f"{len(failed)} plugins could not start and are disabled: {names}. "
            "See Settings > Plugins."
        )


def _library_users(plugins: Sequence[DiscoveredPlugin]) -> list[LibraryUser]:
    """Return the plugins that bundle libraries, with the ``libs/`` folder of each package."""
    return [
        LibraryUser(plugin.plugin_id, plugin.declared, plugin.folder / LIBS_DIRECTORY)
        for plugin in plugins
        if plugin.declared is not None and plugin.declared.libraries
    ]


def _read_contributions(plugin_id: str, service: object) -> tuple[Contribution, ...]:
    """Return what ``service`` contributes, refusing a service or a contribution that is broken."""
    contributions = getattr(service, "contributions", None)
    unload = getattr(service, "unload", None)
    if not callable(contributions) or not callable(unload):
        raise TypeError(
            "The plugin factory must return an object with contributions() and unload()."
        )
    declared = contributions()
    if isinstance(declared, str | bytes) or not isinstance(declared, Sequence):
        raise TypeError("contributions() must return a list of contributions.")
    for index, item in enumerate(declared):
        if not isinstance(item, Contribution):
            raise TypeError(
                f"Contribution {index + 1} is a {type(item).__name__}, not a Contribution."
            )
    check_contributions(plugin_id, declared)
    return tuple(declared)


def _describe(error: Exception) -> str:
    """Return the sentence stored for a failure; the type is added unless it is a database error."""
    if isinstance(error, DatabaseError):
        return str(error)
    text = str(error)
    return f"{type(error).__name__}: {text}" if text else type(error).__name__


def _forget_modules(plugin_id: str) -> None:
    """Drop the imported modules of a plugin, so a later load imports it again."""
    package = f"mtee.plugins.{plugin_id}"
    for name in [key for key in sys.modules if key == package or key.startswith(f"{package}.")]:
        del sys.modules[name]
    with contextlib.suppress(AttributeError):
        delattr(mtee.plugins, plugin_id)


def plugin_id_problem(name: str) -> str:
    """Return why ``name`` cannot be a plugin identifier, or an empty string when it can."""
    if not _PLUGIN_ID.match(name):
        return f"The plugin id {name!r} is not lowercase snake_case."
    if name in _reserved_names():
        return f"The name {name} is used by MTEE itself."
    return ""


def _inspect(folder: Path, package_dir: Path) -> DiscoveredPlugin:
    """Check the name of a package, read its manifest and validate it."""
    name = package_dir.name
    problem = plugin_id_problem(name)
    if problem:
        return _refused(folder, package_dir, problem)
    if not (package_dir / "__init__.py").is_file():
        return _refused(folder, package_dir, "The plugin folder has no __init__.py.")
    manifest, error = _read_manifest(package_dir)
    if manifest is None:
        return _refused(folder, package_dir, error)
    problem = _manifest_problem(manifest, name)
    if problem:
        return DiscoveredPlugin(name, folder, package_dir, manifest, problem)
    return DiscoveredPlugin(name, folder, package_dir, manifest)


def _refused(folder: Path, package_dir: Path, error: str) -> DiscoveredPlugin:
    return DiscoveredPlugin(package_dir.name, folder, package_dir, None, error)


def _read_declared(folder: Path) -> tuple[PluginDescription | None, str]:
    """Read the ``plugin.json`` of a plugin folder, if it has one, and return it with a problem.

    A folder without ``plugin.json`` (sources, ``--plugin-dir``) returns ``(None, "")``.
    """
    path = folder / PLUGIN_JSON
    if not path.is_file():
        return None, ""
    try:
        return PluginDescription.from_json(path.read_text(encoding="utf-8")), ""
    except PackageError as error:
        return None, str(error)
    except (OSError, UnicodeDecodeError) as error:
        return None, f"The plugin.json of this folder cannot be read: {error}"


def _against_declared(
    plugin: DiscoveredPlugin, declared: PluginDescription | None, declared_error: str
) -> DiscoveredPlugin:
    """Refuse a valid plugin whose folder ``plugin.json`` is unreadable or disagrees with it."""
    if not plugin.is_valid or plugin.manifest is None:
        return plugin
    problem = declared_error
    if not problem and declared is not None:
        problem = description_matches_manifest(declared, plugin.manifest)
    if not problem:
        return replace(plugin, declared=declared)
    return DiscoveredPlugin(
        plugin.plugin_id, plugin.folder, plugin.package_dir, plugin.manifest, problem
    )


def _read_manifest(package_dir: Path) -> tuple[PluginManifest | None, str]:
    """Execute ``manifest.py`` alone and return its ``MANIFEST``, or the reason it failed.

    The file is loaded from its path under a private module name, so the package's own
    ``__init__.py`` and factory module are not imported.
    """
    module_name = f"_mtee_plugin_manifest_{package_dir.name}"
    spec = importlib.util.spec_from_file_location(module_name, package_dir / MANIFEST_FILE)
    if spec is None or spec.loader is None:
        return None, "The manifest cannot be loaded."
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        return None, f"The manifest cannot be loaded: {error}"
    finally:
        sys.modules.pop(module_name, None)
    manifest = getattr(module, MANIFEST_ATTRIBUTE, None)
    if not isinstance(manifest, PluginManifest):
        return None, f"The manifest does not define {MANIFEST_ATTRIBUTE} as a PluginManifest."
    return manifest, ""


def _manifest_problem(manifest: PluginManifest, folder_name: str) -> str:
    """Return why ``manifest`` is refused, or an empty string when it is acceptable."""
    if manifest.plugin_id != folder_name:
        return (
            f"The manifest id {manifest.plugin_id!r} differs from the folder name {folder_name!r}."
        )
    for label, value in (
        ("title", manifest.title),
        ("version", manifest.version),
        ("factory", manifest.factory),
    ):
        if not isinstance(value, str) or not value.strip():
            return f"The manifest has no {label}."
    if manifest.api_version not in SUPPORTED_API_VERSIONS:
        supported = ", ".join(str(version) for version in sorted(SUPPORTED_API_VERSIONS))
        return (
            f"The plugin needs plugin interface {manifest.api_version}; "
            f"this MTEE supports {supported}."
        )
    if not _FACTORY.match(manifest.factory):
        return f"The factory {manifest.factory!r} is not written as module:function."
    module = manifest.factory.partition(":")[0]
    package = f"mtee.plugins.{manifest.plugin_id}"
    if module != package and not module.startswith(f"{package}."):
        return f"The factory module must be inside {package}."
    return ""


def _reserved_names() -> frozenset[str]:
    """Return the names under ``mtee.plugins`` that MTEE itself provides.

    A plugin of such a name would be shadowed by the core, since the core folder comes
    first in the import path. The identifiers of the legacy registry are included.
    """
    own = Path(mtee.plugins.__file__ or "").parent
    names = {definition.plugin_id for definition in bundled_plugins()}
    if own.is_dir():
        for entry in own.iterdir():
            if entry.suffix == ".py":
                names.add(entry.stem)
            elif (entry / "__init__.py").is_file():
                names.add(entry.name)
    return frozenset(names)
