"""Discovery of the plugins in the folders the user gave.

Nothing is loaded from a folder the user did not give (``--plugin-dir`` or a saved folder).
A plugin folder holds plugin packages: ``<folder>/<id>/manifest.py`` and ``__init__.py``.
Discovery imports only the ``manifest.py`` of each package, never the package itself, so
the code of a plugin runs only once it is enabled.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import mtee.plugins
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import SUPPORTED_API_VERSIONS, PluginManifest
from mtee.plugins.registry import bundled_plugins

__all__ = [
    "MANIFEST_ATTRIBUTE",
    "MANIFEST_FILE",
    "SETTING_ENABLED",
    "SETTING_FOLDERS",
    "DiscoveredPlugin",
    "PluginPreferences",
    "add_to_package_path",
    "discover",
    "remove_from_package_path",
    "split_existing_folders",
]

MANIFEST_FILE = "manifest.py"
MANIFEST_ATTRIBUTE = "MANIFEST"
SETTING_FOLDERS = "plugins.folders"
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

    @property
    def is_valid(self) -> bool:
        """Return whether the manifest was accepted."""
        return self.manifest is not None and not self.error


class PluginPreferences:
    """The plugin folders and the enabled plugins, kept in the application settings."""

    def __init__(self, settings: SettingsRepository) -> None:
        self._settings = settings

    def folders(self) -> list[Path]:
        """Return the saved plugin folders, in the order they were given."""
        return [Path(value) for value in self._stored_list(SETTING_FOLDERS)]

    def add_folders(self, folders: Iterable[Path]) -> list[Path]:
        """Save ``folders`` besides the saved ones and return the whole list.

        A folder already saved is not repeated; relative paths are resolved first. Nothing
        is written when the list does not change.
        """
        saved = self._stored_list(SETTING_FOLDERS)
        known = {_path_key(value) for value in saved}
        for folder in folders:
            resolved = str(Path(folder).resolve())
            if _path_key(resolved) not in known:
                known.add(_path_key(resolved))
                saved.append(resolved)
        if saved != self._stored_list(SETTING_FOLDERS):
            self._settings.set_json(SETTING_FOLDERS, saved)
        return [Path(value) for value in saved]

    def remove_folder(self, folder: Path) -> None:
        """Forget a saved folder; the plugins found in it are no longer discovered."""
        saved = self._stored_list(SETTING_FOLDERS)
        kept = [value for value in saved if _path_key(value) != _path_key(folder)]
        if kept != saved:
            self._settings.set_json(SETTING_FOLDERS, kept)

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


def split_existing_folders(folders: Sequence[Path]) -> tuple[list[Path], list[Path]]:
    """Return the folders that exist and the folders that are missing, in order."""
    existing: list[Path] = []
    missing: list[Path] = []
    for folder in folders:
        (existing if folder.is_dir() else missing).append(folder)
    return existing, missing


def discover(folders: Sequence[Path]) -> list[DiscoveredPlugin]:
    """List the plugin packages found in ``folders`` and read their manifests.

    Only the direct children that hold a ``manifest.py`` are listed. A folder that does
    not exist is skipped (``split_existing_folders`` reports it). A refused manifest is
    returned with its reason; the first plugin found keeps an identifier that appears twice.
    """
    reserved = _reserved_names()
    found: list[DiscoveredPlugin] = []
    seen: dict[str, Path] = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        for package_dir in sorted(folder.iterdir(), key=lambda path: path.name):
            if not (package_dir / MANIFEST_FILE).is_file():
                continue
            plugin = _inspect(folder, package_dir, reserved)
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


def _inspect(folder: Path, package_dir: Path, reserved: frozenset[str]) -> DiscoveredPlugin:
    """Check the name of a package, read its manifest and validate it."""
    name = package_dir.name
    if not _PLUGIN_ID.match(name):
        return _refused(folder, package_dir, "The plugin folder name is not lowercase snake_case.")
    if name in reserved:
        return _refused(folder, package_dir, f"The name {name} is used by MTEE itself.")
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


def _path_key(path: Path | str) -> str:
    """Compare folders as Windows does: case and separators do not matter."""
    return str(path).replace("/", "\\").rstrip("\\").casefold()
