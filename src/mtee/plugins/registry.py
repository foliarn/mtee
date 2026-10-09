"""Static registry of bundled plugins; implementation modules load on demand."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PluginDefinition:
    plugin_id: str
    title: str
    description: str
    factory_module: str
    factory_name: str


_BUILTINS = (
    PluginDefinition(
        "genre_manager",
        "Genre Manager",
        "Classify and organize tracks in your library",
        "mtee.plugins.genre_manager.models",
        "GenreManagerModel",
    ),
)


def bundled_plugins() -> tuple[PluginDefinition, ...]:
    """List metadata without importing a plugin or querying its catalogue."""
    return _BUILTINS


def load_plugin(plugin_id: str, *args: Any, **kwargs: Any) -> Any:
    """Instantiate one bundled plugin only after its page is opened."""
    definition = next((item for item in _BUILTINS if item.plugin_id == plugin_id), None)
    if definition is None:
        raise KeyError(plugin_id)
    module = importlib.import_module(definition.factory_module)
    return getattr(module, definition.factory_name)(*args, **kwargs)
