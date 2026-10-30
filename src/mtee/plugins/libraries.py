"""The libraries bundled by the plugins that load: one copy per library, and the import finder.

Python imports a library once per process, so the plugins that load share one copy of each
library they bundle. ``plan_libraries`` chooses that copy: for each library, the highest bundled
version that every plugin using it accepts. When no bundled version suits every plugin, the later
plugin (by identifier) is refused with one sentence and is not loaded.

``LibraryFinder`` is a meta path finder. It serves each top-level module of a chosen library from
the ``libs/`` folder of its copy. A ``libs/`` folder is never put on ``sys.path`` as a whole, so the
order of the plugins does not decide which copy is imported. Submodules resolve through the
``__path__`` of their package.

This module does not import Qt.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder
from pathlib import Path
from types import ModuleType

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from mtee.plugins.package import BundledLibrary, PluginDescription, normalize_name

__all__ = [
    "LibraryFinder",
    "LibraryPlan",
    "LibraryUser",
    "bundled_library",
    "choose_copy",
    "clash_sentence",
    "install_finder",
    "plan_libraries",
    "uninstall_finder",
]


@dataclass(frozen=True, slots=True)
class LibraryUser:
    """A plugin that loads: its id, its description and the ``libs/`` folder of its package."""

    plugin_id: str
    description: PluginDescription
    libs_dir: Path


@dataclass(frozen=True, slots=True)
class LibraryPlan:
    """The chosen copies, as top-level module -> ``libs/`` folder, and the plugins refused.

    ``refused`` maps a plugin identifier to the sentence that says why it is not loaded.
    """

    locations: dict[str, Path] = field(default_factory=dict)
    refused: dict[str, str] = field(default_factory=dict)


def bundled_library(description: PluginDescription, name: str) -> BundledLibrary | None:
    """Return the copy of library ``name`` that ``description`` bundles, or ``None``."""
    key = normalize_name(name)
    for library in description.libraries:
        if normalize_name(library.name) == key:
            return library
    return None


def choose_copy(name: str, users: Sequence[PluginDescription]) -> int | None:
    """Return the index in ``users`` of the plugin whose bundled copy of ``name`` is chosen.

    Every bundled copy of ``name`` among ``users`` is a candidate. The chosen one is the highest
    version that every user accepts; of two copies of that version, the first user's is kept.
    Return ``None`` when no candidate suits every user.
    """
    candidates: list[tuple[Version, int]] = []
    for index, user in enumerate(users):
        copy = bundled_library(user, name)
        if copy is None:
            continue
        try:
            version = Version(copy.version)
        except InvalidVersion:
            continue
        if _suits_every_user(name, users, copy.version):
            candidates.append((version, index))
    if not candidates:
        return None
    highest = max(version for version, _ in candidates)
    return min(index for version, index in candidates if version == highest)


def clash_sentence(
    name: str, first: PluginDescription, second: PluginDescription, verdict: str
) -> str:
    """Return the sentence that names two plugins whose ranges for ``name`` share no copy.

    ``verdict`` is the last sentence, which says what became of the plugin refused.
    """
    first_range = _accepted_range(first, name)
    second_range = _accepted_range(second, name)
    return (
        f"{first.title} and {second.title} need different versions of {name} "
        f"({first_range} and {second_range}). {verdict}"
    )


def plan_libraries(users: Sequence[LibraryUser]) -> LibraryPlan:
    """Choose one copy of each shared library and refuse the plugins that cannot share one.

    The plugins are taken in identifier order. A refused plugin is removed, and the choice is made
    again for the rest, because removing it can change which copy suits the others.
    """
    active = sorted(users, key=lambda user: user.plugin_id)
    refused: dict[str, str] = {}
    while True:
        clash = _first_clash(active)
        if clash is None:
            break
        later, sentence = clash
        refused[later.plugin_id] = sentence
        active = [user for user in active if user.plugin_id != later.plugin_id]
    return LibraryPlan(locations=_locations(active), refused=refused)


class LibraryFinder(MetaPathFinder):
    """Serves the top-level modules of the chosen libraries from their ``libs/`` folders."""

    def __init__(self, locations: Mapping[str, Path]) -> None:
        self.locations = dict(locations)

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        folder = self.locations.get(fullname)
        if folder is None:
            # Only top-level names are mapped; a submodule resolves through its package.
            return None
        return PathFinder.find_spec(fullname, [str(folder)])


def install_finder(locations: Mapping[str, Path]) -> None:
    """Replace any earlier library finder by one that serves ``locations``, first on the path."""
    uninstall_finder()
    if locations:
        sys.meta_path.insert(0, LibraryFinder(locations))


def uninstall_finder() -> None:
    """Remove every library finder from ``sys.meta_path``; modules already imported stay."""
    sys.meta_path[:] = [finder for finder in sys.meta_path if not isinstance(finder, LibraryFinder)]


def _suits_every_user(name: str, users: Sequence[PluginDescription], version: str) -> bool:
    for user in users:
        library = bundled_library(user, name)
        if library is None or not _accepts(library, version):
            return False
    return True


def _accepts(library: BundledLibrary, version: str) -> bool:
    try:
        return SpecifierSet(library.accepts).contains(version, prereleases=True)
    except InvalidSpecifier:
        return False


def _accepted_range(description: PluginDescription, name: str) -> str:
    library = bundled_library(description, name)
    return library.accepts if library is not None else ""


def _bundled_names(users: Sequence[LibraryUser]) -> list[str]:
    names = {
        normalize_name(library.name) for user in users for library in user.description.libraries
    }
    return sorted(names)


def _first_clash(users: Sequence[LibraryUser]) -> tuple[LibraryUser, str] | None:
    """Return the first plugin that cannot share a library with the plugins before it, and why."""
    for name in _bundled_names(users):
        holders = [user for user in users if bundled_library(user.description, name) is not None]
        if len(holders) < 2:
            continue
        kept: list[LibraryUser] = []
        for holder in holders:
            descriptions = [user.description for user in [*kept, holder]]
            if kept and choose_copy(name, descriptions) is None:
                earlier = next(
                    (
                        user
                        for user in kept
                        if choose_copy(name, [user.description, holder.description]) is None
                    ),
                    kept[0],
                )
                verdict = f"{holder.description.title} was not started."
                sentence = clash_sentence(name, earlier.description, holder.description, verdict)
                return holder, sentence
            kept.append(holder)
    return None


def _locations(users: Sequence[LibraryUser]) -> dict[str, Path]:
    """Map each top-level module of a chosen library to the ``libs/`` folder of its copy."""
    locations: dict[str, Path] = {}
    for name in _bundled_names(users):
        holders = [user for user in users if bundled_library(user.description, name) is not None]
        owner: LibraryUser | None = holders[0] if len(holders) == 1 else None
        if len(holders) > 1:
            index = choose_copy(name, [user.description for user in holders])
            owner = holders[index] if index is not None else None
        if owner is None:
            continue
        for module, provider in owner.description.top_level_modules.items():
            if normalize_name(provider) == name:
                locations.setdefault(module, owner.libs_dir)
    return dict(sorted(locations.items()))
