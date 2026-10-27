"""Plugin switch and registry of the release.

MTEE 0.1 ships no bundled plugin. ``PLUGIN_UI_ENABLED`` is ``False``, so no plugin entry
is shown and no plugin service is built. The code of a plugin is not part of the public tree:
``conversion`` is loaded from the private plugin repository, and only when the switch is on.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

__all__ = [
    "PLUGIN_UI_ENABLED",
    "PluginDefinition",
    "bundled_plugins",
    "load_plugin",
    "plugin_ui_enabled",
]

# v0.1 ships without plugins. Plugin entries and services stay hidden while this is False.
PLUGIN_UI_ENABLED = False


@dataclass(frozen=True, slots=True)
class PluginDefinition:
    """Metadata of one plugin; its module is imported only when the plugin is loaded."""

    plugin_id: str
    title: str
    description: str
    factory_module: str
    factory_name: str


_BUILTINS = (
    PluginDefinition(
        "conversion",
        "Convert",
        "Convert audio files through FFmpeg, with a visible job queue",
        "mtee.plugins.conversion.models",
        "create_conversion_model",
    ),
)


def plugin_ui_enabled() -> bool:
    """Return whether the plugin entries and services are active in this build."""
    return PLUGIN_UI_ENABLED


def bundled_plugins() -> tuple[PluginDefinition, ...]:
    """List the plugin metadata without importing a plugin."""
    return _BUILTINS


def load_plugin(plugin_id: str, *args: Any, **kwargs: Any) -> Any:
    """Build one plugin's service. Refused while the plugin switch is off."""
    if not plugin_ui_enabled():
        raise RuntimeError(f"Plugin {plugin_id} is not enabled in this build.")
    definition = next(item for item in _BUILTINS if item.plugin_id == plugin_id)
    module = importlib.import_module(definition.factory_module)
    return getattr(module, definition.factory_name)(*args, **kwargs)
