"""Static registry of bundled plugins; implementation modules load on demand.

``PLUGIN_UI_ENABLED`` is the single switch of the v0.1 release: it is ``False``, so no
plugin entry is shown and no plugin service is built. The plugin code, its migrations and
this registry stay in place for the plugin platform that comes later.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mtee.persistence.database import Database, discover_migrations

__all__ = [
    "PLUGIN_UI_ENABLED",
    "PluginDefinition",
    "bundled_plugins",
    "load_plugin",
    "plugin_ui_enabled",
    "prepare_plugin_schema",
]

# v0.1 ships without plugins. Set to True to show the Plugins entry again and to attach
# the plugin services at start-up.
PLUGIN_UI_ENABLED = False

_PLUGINS_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class PluginDefinition:
    plugin_id: str
    title: str
    description: str
    factory_module: str
    factory_name: str
    requires: tuple[str, ...] = ()

    @property
    def migrations_dir(self) -> Path:
        """Return the directory of the scripts that create the plugin's tables."""
        return _PLUGINS_ROOT / self.plugin_id / "migrations"


_BUILTINS = (
    PluginDefinition(
        "artist_manager",
        "Artist manager",
        "Review the artists credited on your tracks",
        "mtee.plugins.artist_manager.models",
        "ArtistManagerModel",
    ),
    PluginDefinition(
        "genre_manager",
        "Genre Manager",
        "Classify and organize tracks in your library",
        "mtee.plugins.genre_manager.models",
        "GenreManagerModel",
        requires=("artist_manager",),
    ),
)


def plugin_ui_enabled() -> bool:
    """Return whether the plugin entries and services are active in this build."""
    return PLUGIN_UI_ENABLED


def bundled_plugins() -> tuple[PluginDefinition, ...]:
    """List metadata without importing a plugin or querying its catalogue."""
    return _BUILTINS


def _definition(plugin_id: str) -> PluginDefinition:
    definition = next((item for item in _BUILTINS if item.plugin_id == plugin_id), None)
    if definition is None:
        raise KeyError(plugin_id)
    return definition


def load_plugin(plugin_id: str, *args: Any, **kwargs: Any) -> Any:
    """Instantiate one bundled plugin only after its page is opened."""
    definition = _definition(plugin_id)
    module = importlib.import_module(definition.factory_module)
    return getattr(module, definition.factory_name)(*args, **kwargs)


def prepare_plugin_schema(database: Database, plugin_id: str) -> None:
    """Create or upgrade the tables of a plugin, after those of the plugins it requires.

    Plugin repositories call this when they are opened, so the tables of a plugin exist
    only in a database where that plugin is loaded. Calling it again applies nothing.
    """
    definition = _definition(plugin_id)
    for required in definition.requires:
        prepare_plugin_schema(database, required)
    database.migrate_plugin(plugin_id, discover_migrations(definition.migrations_dir))
