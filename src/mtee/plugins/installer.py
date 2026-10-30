"""Install, update and remove plugins from ``.mteeplugin`` packages (plan 123.2).

The plugins folder ``<data-dir>/plugins/`` holds one folder per installed plugin,
``<data-dir>/plugins/<id>/``, laid out like a package: ``plugin.json``, ``<id>/``, ``libs/`` and
the rest. A package is read without running any of its code: ``inspect`` checks the zip and its
``plugin.json``. ``install`` then extracts the whole package into ``.staging/<id>/``, checks the
extracted plugin again, and renames it into place. Nothing is deleted permanently: a replaced or
removed plugin folder goes to the Recycle Bin through the trash service the caller passes in.

This module does not import Qt.
"""

from __future__ import annotations

import contextlib
import logging
import re
import shutil
import stat
import sys
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from packaging.specifiers import InvalidSpecifier, SpecifierSet

from mtee.plugins.api import SUPPORTED_API_VERSIONS
from mtee.plugins.libraries import bundled_library, choose_copy, clash_sentence
from mtee.plugins.loader import PluginPreferences, discover, plugin_id_problem
from mtee.plugins.package import (
    PLUGIN_JSON,
    PYTHON_VERSION,
    PackageError,
    PluginDescription,
    normalize_name,
)

__all__ = [
    "MAX_UNPACKED_BYTES",
    "PLUGINS_FOLDER",
    "STAGING_FOLDER",
    "InstallRefusedError",
    "InstalledPlugin",
    "PackageInfo",
    "Trash",
    "clean_staging",
    "inspect",
    "install",
    "installed",
    "plugin_data_folder",
    "plugin_folders",
    "plugins_folder",
    "uninstall",
]

_LOGGER = logging.getLogger(__name__)
PLUGINS_FOLDER = "plugins"
STAGING_FOLDER = ".staging"
# The same folder name as ``mtee.plugins.context.PLUGIN_DATA_DIRECTORY``.
PLUGIN_DATA_FOLDER = "plugin-data"
MAX_UNPACKED_BYTES = 500 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024


class InstallRefusedError(PackageError):
    """A package, or a plugin folder, is refused; the message is one readable sentence."""

    # Shown in Tasks as its message alone (see docs/plugins.md, the readable attribute).
    readable = True


class Trash(Protocol):
    """What the installer needs from the trash service: a folder goes to the Recycle Bin."""

    def recycle_folder(self, path: Path) -> object: ...


@dataclass(frozen=True, slots=True)
class InstalledPlugin:
    """A plugin folder of the plugins folder, with the ``plugin.json`` it holds."""

    plugin_id: str
    folder: Path
    description: PluginDescription


@dataclass(frozen=True, slots=True)
class PackageInfo:
    """What a checked package says about itself.

    ``size`` is the size of the package file. ``installed_version`` is the version of a plugin of
    the same id already installed, or ``None``; ``replaces`` tells whether there is one.
    """

    description: PluginDescription
    size: int
    installed_version: str | None

    @property
    def replaces(self) -> bool:
        return self.installed_version is not None


def plugins_folder(data_dir: Path) -> Path:
    """Return the folder that holds the installed plugins."""
    return data_dir / PLUGINS_FOLDER


def plugin_data_folder(data_dir: Path, plugin_id: str) -> Path:
    """Return the folder of a plugin's own data: it survives an update and an uninstall."""
    return data_dir / PLUGIN_DATA_FOLDER / plugin_id


def plugin_folders(data_dir: Path) -> list[Path]:
    """Return the folder of every installed plugin, and of every folder unpacked by hand.

    The staging folder and any other folder whose name starts with a dot are left out.
    """
    root = plugins_folder(data_dir)
    if not root.is_dir():
        return []
    return [
        child
        for child in sorted(root.iterdir(), key=lambda path: path.name)
        if child.is_dir() and not child.name.startswith(".")
    ]


def installed(data_dir: Path) -> list[InstalledPlugin]:
    """List the installed plugins, read from the ``plugin.json`` of each folder.

    A folder without a readable ``plugin.json``, or whose name is not the id it declares, is left
    out. Discovery still reports such a folder when it is loaded.
    """
    found: list[InstalledPlugin] = []
    for folder in plugin_folders(data_dir):
        path = folder / PLUGIN_JSON
        if not path.is_file():
            continue
        try:
            description = PluginDescription.from_json(path.read_text(encoding="utf-8"))
        except (PackageError, OSError, UnicodeDecodeError) as error:
            _LOGGER.warning("Plugin folder %s has no readable plugin.json: %s", folder, error)
            continue
        if description.id != folder.name:
            _LOGGER.warning("Plugin folder %s holds the plugin %s.", folder, description.id)
            continue
        found.append(InstalledPlugin(folder.name, folder, description))
    return found


def inspect(
    package_path: Path,
    *,
    installed: Sequence[InstalledPlugin],
    mtee_version: str,
    mtee_libraries: Mapping[str, str],
) -> PackageInfo:
    """Check a package file without running any of its code, and describe it.

    Raise ``InstallRefusedError``, with one sentence, when the package cannot be installed here.
    ``installed`` lists the plugins already in the plugins folder: a plugin of the same id is
    replaced, so only the other ones can conflict. ``mtee_libraries`` are the libraries MTEE
    ships, by name and version.
    """
    try:
        archive = zipfile.ZipFile(package_path)
    except (OSError, zipfile.BadZipFile) as error:
        raise InstallRefusedError(
            f"{package_path.name} is not a plugin package that can be read."
        ) from error
    with archive:
        _check_entries(archive)
        description = _read_description(archive)
        _check_description(description, mtee_version=mtee_version, mtee_libraries=mtee_libraries)
        _check_package_folder(archive, description.id)
        replaced = _check_conflicts(description, installed)
    return PackageInfo(description, package_path.stat().st_size, replaced)


def install(
    package_path: Path,
    *,
    data_dir: Path,
    trash: Trash,
    preferences: PluginPreferences,
    mtee_version: str,
    mtee_libraries: Mapping[str, str],
) -> InstalledPlugin:
    """Install a package into the plugins folder and return the installed plugin.

    The package is checked first (``inspect``), extracted into ``.staging/<id>/``, and checked
    again once extracted. A plugin of the same id is sent to the Recycle Bin before the new folder
    takes its place. The plugin is switched on, unless it was installed before and switched off.
    """
    found = inspect(
        package_path,
        installed=installed(data_dir),
        mtee_version=mtee_version,
        mtee_libraries=mtee_libraries,
    )
    plugin_id = found.description.id
    root = plugins_folder(data_dir)
    staging = root / STAGING_FOLDER / plugin_id
    if staging.exists():
        raise InstallRefusedError("Another install has not finished. Restart MTEE and try again.")
    staging.mkdir(parents=True)
    target = root / plugin_id
    try:
        _extract(package_path, staging)
        _check_extracted(staging, plugin_id)
        if target.exists():
            trash.recycle_folder(target)
        staging.rename(target)
    except BaseException:
        # The staging folder was created by this call and holds only what this call extracted, so
        # it is removed. A plugin folder is never removed here; it went to the Recycle Bin, if any.
        shutil.rmtree(staging, ignore_errors=True)
        _remove_empty(staging.parent)
        raise
    _remove_empty(staging.parent)
    switched_off_before = found.replaces and not preferences.is_enabled(plugin_id)
    if not switched_off_before:
        preferences.set_enabled(plugin_id, True)
    return InstalledPlugin(plugin_id, target, found.description)


def _remove_empty(folder: Path) -> None:
    """Remove ``folder`` when it is empty; a folder that still holds anything is kept."""
    with contextlib.suppress(OSError):
        folder.rmdir()


def uninstall(
    plugin_id: str, *, data_dir: Path, trash: Trash, preferences: PluginPreferences
) -> None:
    """Send the plugin folder to the Recycle Bin and switch the plugin off.

    The plugin's data folder and its database tables stay in place.
    """
    folder = plugins_folder(data_dir) / plugin_id
    if plugin_id_problem(plugin_id) or not folder.is_dir():
        raise InstallRefusedError(f"The plugin {plugin_id} is not installed.")
    trash.recycle_folder(folder)
    preferences.set_enabled(plugin_id, False)


def clean_staging(data_dir: Path, trash: Trash) -> bool:
    """Send a leftover staging folder, from an install that was interrupted, to the Recycle Bin.

    Return whether there was one. Called at start, before any plugin is discovered.
    """
    staging = plugins_folder(data_dir) / STAGING_FOLDER
    if not staging.exists():
        return False
    trash.recycle_folder(staging)
    return True


def _check_entries(archive: zipfile.ZipFile) -> None:
    """Refuse an entry outside the package, a link, or more unpacked bytes than allowed."""
    total = 0
    for info in archive.infolist():
        name = info.filename
        if _leaves_package(name):
            raise InstallRefusedError(f"The package has an entry outside its folder: {name!r}.")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise InstallRefusedError(f"The package holds a link, {name!r}, which is refused.")
        total += info.file_size
        if total > MAX_UNPACKED_BYTES:
            raise InstallRefusedError("The package unpacks to more than 500 MB, which is refused.")


def _leaves_package(name: str) -> bool:
    """Return whether an entry name is absolute, has a drive, or goes up with ``..``."""
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return True
    return ".." in normalized.split("/")


def _read_description(archive: zipfile.ZipFile) -> PluginDescription:
    try:
        raw = archive.read(PLUGIN_JSON)
    except KeyError as error:
        raise InstallRefusedError("The package has no plugin.json.") from error
    except (OSError, zipfile.BadZipFile) as error:
        raise InstallRefusedError(f"The package is damaged and cannot be read: {error}") from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InstallRefusedError(
            "The plugin.json of the package is not written in UTF-8."
        ) from error
    try:
        return PluginDescription.from_json(text)
    except PackageError as error:
        raise InstallRefusedError(str(error)) from error


def _check_description(
    description: PluginDescription, *, mtee_version: str, mtee_libraries: Mapping[str, str]
) -> None:
    """Refuse a package whose Python, platform, MTEE range, interface, id or libraries differ."""
    if description.python != PYTHON_VERSION:
        raise InstallRefusedError(
            f"The package is built for Python {description.python}; "
            f"MTEE runs on Python {PYTHON_VERSION}."
        )
    if description.platform not in _supported_platforms():
        raise InstallRefusedError(
            f"The package is built for {description.platform}, which this MTEE cannot load."
        )
    try:
        in_range = SpecifierSet(description.mtee).contains(mtee_version, prereleases=True)
    except InvalidSpecifier as error:
        raise InstallRefusedError(
            f"The MTEE versions of the package, {description.mtee!r}, are not a version range."
        ) from error
    if not in_range:
        raise InstallRefusedError(
            f"The package is built for MTEE {description.mtee}, and this MTEE is {mtee_version}."
        )
    if description.api_version not in SUPPORTED_API_VERSIONS:
        supported = ", ".join(str(version) for version in sorted(SUPPORTED_API_VERSIONS))
        raise InstallRefusedError(
            f"The package needs plugin interface {description.api_version}; "
            f"this MTEE supports {supported}."
        )
    problem = plugin_id_problem(description.id)
    if problem:
        raise InstallRefusedError(problem)
    shipped = {normalize_name(name) for name in mtee_libraries}
    for library in description.libraries:
        if normalize_name(library.name) in shipped:
            raise InstallRefusedError(
                f"{description.title} bundles {library.name}, which MTEE already provides. "
                "Rebuild the package."
            )


def _supported_platforms() -> tuple[str, ...]:
    """Return the platforms a package may name on this system."""
    return ("any", "win_amd64") if sys.platform == "win32" else ("any",)


def _check_package_folder(archive: zipfile.ZipFile, plugin_id: str) -> None:
    if f"{plugin_id}/manifest.py" not in set(archive.namelist()):
        raise InstallRefusedError(f"The package has no {plugin_id}/manifest.py.")


def _check_conflicts(
    description: PluginDescription, installed: Sequence[InstalledPlugin]
) -> str | None:
    """Refuse a library that another installed plugin needs at an incompatible version.

    Return the version of the plugin of the same id that this package replaces, if any.
    """
    replaced: str | None = None
    others: list[PluginDescription] = []
    for plugin in installed:
        if plugin.plugin_id == description.id:
            replaced = plugin.description.version
        else:
            others.append(plugin.description)
    for other in sorted(others, key=lambda item: item.id):
        for library in description.libraries:
            if bundled_library(other, library.name) is None:
                continue
            if choose_copy(library.name, [description, other]) is None:
                verdict = f"{description.title} was not installed."
                raise InstallRefusedError(clash_sentence(library.name, description, other, verdict))
    return replaced


def _extract(package_path: Path, target: Path) -> None:
    """Write every entry of the package below ``target``, refusing a path outside it."""
    written = 0
    with zipfile.ZipFile(package_path) as archive:
        for info in archive.infolist():
            if _leaves_package(info.filename):
                raise InstallRefusedError(
                    f"The package has an entry outside its folder: {info.filename!r}."
                )
            parts = [part for part in info.filename.replace("\\", "/").split("/") if part]
            destination = target.joinpath(*parts)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as sink:
                while chunk := source.read(_CHUNK_BYTES):
                    written += len(chunk)
                    if written > MAX_UNPACKED_BYTES:
                        raise InstallRefusedError(
                            "The package unpacks to more than 500 MB, which is refused."
                        )
                    sink.write(chunk)


def _check_extracted(staging: Path, plugin_id: str) -> None:
    """Discover the extracted plugin: its manifest must agree with the ``plugin.json``."""
    found = discover([staging])
    if len(found) == 1 and found[0].is_valid and found[0].plugin_id == plugin_id:
        return
    if found and not found[0].is_valid:
        raise InstallRefusedError(found[0].error)
    raise InstallRefusedError(f"The extracted package does not hold the plugin {plugin_id}.")
