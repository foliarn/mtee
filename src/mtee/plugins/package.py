"""The package format of a plugin: the ``.mteeplugin`` archive and its ``plugin.json``.

A package is a zip archive. Its root holds ``plugin.json``, the plugin folder ``<id>/``
(``manifest.py``, code, ``migrations/``, QML), ``libs/`` with the libraries the plugin bundles as
unpacked wheels, an optional ``README.md`` and ``LICENSES/`` with the licence texts of the plugin
and of each bundled library. ``plugin.json`` is read before any code of the package runs.

This module holds the format for the packing script (``scripts/pack_plugin.py``) and for the
installer. It does not import Qt. The fields are described in ``docs/plugins.md``, section 11.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mtee.plugins.api import PluginManifest

__all__ = [
    "LIBS_DIRECTORY",
    "LICENSES_DIRECTORY",
    "PACKAGE_SUFFIX",
    "PLUGIN_JSON",
    "PLUGIN_JSON_SCHEMA",
    "BundledLibrary",
    "PackageError",
    "PluginDescription",
    "description_matches_manifest",
]

PACKAGE_SUFFIX = ".mteeplugin"
PLUGIN_JSON = "plugin.json"
LIBS_DIRECTORY = "libs"
LICENSES_DIRECTORY = "LICENSES"
PLUGIN_JSON_SCHEMA = 1


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
