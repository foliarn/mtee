"""The package format of a plugin: the ``.mteeplugin`` archive and its ``plugin.json``.

A package is a zip archive. Its root holds ``plugin.json``, the plugin folder ``<id>/``
(``manifest.py``, code, ``migrations/``, QML), ``libs/`` with the libraries the plugin bundles as
unpacked wheels, an optional ``README.md`` and ``LICENSES/`` with the licence texts of the plugin
and of each bundled library. ``plugin.json`` is read before any code of the package runs.

This module holds the format for the packing script (``scripts/pack_plugin.py``) and for the
installer. It does not import Qt. The fields are described in ``docs/plugins.md``, section 11.
"""

from __future__ import annotations

import csv
import dataclasses
import importlib.metadata
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

if TYPE_CHECKING:
    from mtee.plugins.api import PluginManifest

__all__ = [
    "LIBS_DIRECTORY",
    "LICENSES_DIRECTORY",
    "MODULE_SUFFIXES",
    "PACKAGE_SUFFIX",
    "PLUGIN_JSON",
    "PLUGIN_JSON_SCHEMA",
    "PYTHON_VERSION",
    "BundledLibrary",
    "PackageError",
    "PluginDescription",
    "bundled_distributions",
    "description_matches_manifest",
    "distribution_name",
    "mtee_runtime_libraries",
    "normalize_name",
    "record_paths",
    "top_level_modules",
]

PACKAGE_SUFFIX = ".mteeplugin"
PLUGIN_JSON = "plugin.json"
LIBS_DIRECTORY = "libs"
LICENSES_DIRECTORY = "LICENSES"
PLUGIN_JSON_SCHEMA = 1
# The interpreter a package is built for; MTEE runs on this one version.
PYTHON_VERSION = "3.12"
MODULE_SUFFIXES = (".py", ".pyd", ".so")


class PackageError(ValueError):
    """A package or its ``plugin.json`` is refused; the message is one readable sentence."""


@dataclass(frozen=True, slots=True)
class BundledLibrary:
    """A Python library carried in the ``libs/`` folder of a package.

    ``version`` is the version bundled. ``accepts`` is the version range the plugin works with,
    for example ``">=2.28,<3"`` or ``"==2.31.0"``. ``licence`` is the licence the library names
    and may be empty.
    """

    name: str
    version: str
    accepts: str
    licence: str


@dataclass(frozen=True, slots=True)
class PluginDescription:
    """The static description of a package, as written in its ``plugin.json``.

    ``mtee`` is the range of MTEE versions the package was built for. ``platform`` is
    ``"win_amd64"`` when the bundled libraries are compiled for Windows, else ``"any"``.
    ``top_level_modules`` maps each importable module of ``libs/`` to the library that provides
    it.
    """

    id: str
    title: str
    description: str
    version: str
    api_version: int
    author: str
    homepage: str
    licence: str
    uses_network: bool
    python: str
    platform: str
    mtee: str
    libraries: tuple[BundledLibrary, ...]
    top_level_modules: dict[str, str]
    schema: int = PLUGIN_JSON_SCHEMA

    def to_json(self) -> str:
        """Return the ``plugin.json`` text: sorted keys, an indent of two, a final newline."""
        data = dataclasses.asdict(self)
        return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> PluginDescription:
        """Read a ``plugin.json`` text.

        Raise ``PackageError`` with one sentence when the text is not JSON, names an unknown
        schema, or lacks a field or gives it the wrong type.
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise PackageError(
                f"plugin.json is not valid JSON: {error.msg} (line {error.lineno})."
            ) from error
        if not isinstance(data, dict):
            raise PackageError("plugin.json must hold one JSON object.")
        schema = _read(data, "schema", int, "a whole number")
        if schema != PLUGIN_JSON_SCHEMA:
            raise PackageError(
                f"plugin.json has schema {schema}, but this MTEE reads schema {PLUGIN_JSON_SCHEMA}."
            )
        return cls(
            id=_read(data, "id", str, "a text"),
            title=_read(data, "title", str, "a text"),
            description=_read(data, "description", str, "a text"),
            version=_read(data, "version", str, "a text"),
            api_version=_read(data, "api_version", int, "a whole number"),
            author=_read(data, "author", str, "a text"),
            homepage=_read(data, "homepage", str, "a text"),
            licence=_read(data, "licence", str, "a text"),
            uses_network=_read(data, "uses_network", bool, "true or false"),
            python=_read(data, "python", str, "a text"),
            platform=_read(data, "platform", str, "a text"),
            mtee=_read(data, "mtee", str, "a text"),
            libraries=_libraries(_read(data, "libraries", list, "a list")),
            top_level_modules=_modules(_read(data, "top_level_modules", dict, "an object")),
            schema=schema,
        )


def description_matches_manifest(description: PluginDescription, manifest: PluginManifest) -> str:
    """Return why ``description`` and ``manifest`` disagree, or an empty string when they agree.

    The id, the version and the plugin interface version must be the same in both.
    """
    if description.id != manifest.plugin_id:
        return (
            f"plugin.json names the plugin {description.id!r}, "
            f"but manifest.py names {manifest.plugin_id!r}."
        )
    if description.version != manifest.version:
        return (
            f"plugin.json says version {description.version}, "
            f"but manifest.py says version {manifest.version}."
        )
    if description.api_version != manifest.api_version:
        return (
            f"plugin.json says plugin interface {description.api_version}, "
            f"but manifest.py says {manifest.api_version}."
        )
    return ""


def _read(
    data: Mapping[str, Any], key: str, kind: type, expected: str, where: str = "plugin.json"
) -> Any:
    """Return ``data[key]``, refusing a missing key and a value of another type."""
    if key not in data:
        raise PackageError(f"{where} has no {key} field.")
    value = data[key]
    # bool is a subclass of int in Python; a JSON true is not a whole number.
    if not isinstance(value, kind) or (isinstance(value, bool) and kind is not bool):
        raise PackageError(f"The {key} field of {where} must be {expected}.")
    return value


def _libraries(items: list[Any]) -> tuple[BundledLibrary, ...]:
    """Read the ``libraries`` list of a ``plugin.json``."""
    libraries: list[BundledLibrary] = []
    for index, item in enumerate(items, start=1):
        where = f"library {index} of plugin.json"
        if not isinstance(item, dict):
            raise PackageError(f"Library {index} of plugin.json must be an object.")
        libraries.append(
            BundledLibrary(
                name=_read(item, "name", str, "a text", where),
                version=_read(item, "version", str, "a text", where),
                accepts=_read(item, "accepts", str, "a text", where),
                licence=_read(item, "licence", str, "a text", where),
            )
        )
    return tuple(libraries)


def _modules(data: Mapping[str, Any]) -> dict[str, str]:
    """Read the ``top_level_modules`` object of a ``plugin.json``."""
    if not all(isinstance(library, str) for library in data.values()):
        raise PackageError(
            "top_level_modules of plugin.json must map module names to library names."
        )
    return {str(module): str(library) for module, library in data.items()}


def normalize_name(name: str) -> str:
    """Return the PEP 503 form of a distribution name: lowercase, runs of ``-_.`` as ``-``."""
    return canonicalize_name(name)


def mtee_runtime_libraries(
    *,
    requires: Callable[[str], Sequence[str] | None] = lambda name: _installed_requires(name),
    version: Callable[[str], str | None] = lambda name: _installed_version(name),
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return the libraries MTEE ships at run time, with the versions installed.

    The closure starts from the requirements of ``mtee`` and follows the requirements of each
    library in turn. A requirement counts when its environment marker is true (for
    ``environment``, or else for the running interpreter) and it is not an extra. A requirement
    that is not installed here is left out, since MTEE cannot ship it. The keys are PEP 503 names.
    ``requires`` and ``version`` read the installed metadata; a test passes its own.
    """
    shipped: dict[str, str] = {}
    pending = _runtime_names(requires("mtee") or (), environment)
    seen: set[str] = set()
    while pending:
        name = pending.pop(0)
        if name in seen:
            continue
        seen.add(name)
        installed = version(name)
        if installed is None:
            continue
        shipped[name] = installed
        pending.extend(_runtime_names(requires(name) or (), environment))
    return dict(sorted(shipped.items()))


def _installed_requires(name: str) -> list[str] | None:
    """Return the requirements of an installed distribution, or ``None`` if it is not installed."""
    try:
        return importlib.metadata.requires(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _installed_version(name: str) -> str | None:
    """Return the version of an installed distribution, or ``None`` when it is not installed."""
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _runtime_names(texts: Sequence[str], environment: Mapping[str, str] | None) -> list[str]:
    """Return the normalized names of the requirements that count at run time."""
    names: list[str] = []
    for text in texts:
        try:
            requirement = Requirement(text)
        except InvalidRequirement:
            continue
        marker = requirement.marker
        if marker is not None:
            if re.search(r"\bextra\b", str(marker)):
                continue
            if not marker.evaluate(dict(environment) if environment is not None else None):
                continue
        names.append(normalize_name(requirement.name))
    return names


def bundled_distributions(libs: Path) -> list[tuple[Path, importlib.metadata.PathDistribution]]:
    """Return the ``.dist-info`` folders of ``libs`` with their metadata, sorted by name."""
    return [
        (path, importlib.metadata.PathDistribution(path))
        for path in sorted(libs.glob("*.dist-info"))
    ]


def distribution_name(distribution: importlib.metadata.Distribution, dist_info: Path) -> str:
    """Return the name a distribution declares, or the one its folder name gives."""
    name = distribution.metadata.get("Name")
    return name.strip() if name else dist_info.name.removesuffix(".dist-info").split("-")[0]


def record_paths(dist_info: Path) -> list[str]:
    """Return the file paths listed in the ``RECORD`` of a distribution."""
    record = dist_info / "RECORD"
    if not record.is_file():
        return []
    rows = csv.reader(record.read_text(encoding="utf-8").splitlines())
    return [row[0] for row in rows if row and row[0]]


def top_level_modules(dist_info: Path) -> list[str]:
    """Return the importable top-level names of a distribution.

    ``top_level.txt`` is used when the distribution has one; otherwise the names come from the
    ``.py``, ``.pyd`` and ``.so`` files listed in its ``RECORD``.
    """
    listed = dist_info / "top_level.txt"
    if listed.is_file():
        names = {line.strip() for line in listed.read_text(encoding="utf-8").splitlines()}
        return sorted(name for name in names if name)
    modules: set[str] = set()
    for relative in record_paths(dist_info):
        parts = PurePosixPath(relative).parts
        if not parts or relative.startswith("..") or PurePosixPath(relative).is_absolute():
            continue
        if parts[0].endswith((".dist-info", ".data")) or not parts[-1].endswith(MODULE_SUFFIXES):
            continue
        modules.add(parts[0].split(".")[0] if len(parts) == 1 else parts[0])
    return sorted(modules)
