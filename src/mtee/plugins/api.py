"""The interface between MTEE and a plugin.

This is the only core module a plugin imports. It holds what a plugin declares in its
``manifest.py`` and, further down, what the core gives to the plugin's factory. Importing it
loads no Qt object, no database and no plugin: a manifest is read before the plugin is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "API_VERSION",
    "SUPPORTED_API_VERSIONS",
    "PluginManifest",
]

# The version of the contract between the core and a plugin (see docs/plugins.md, section 9).
API_VERSION = 1
SUPPORTED_API_VERSIONS = frozenset({API_VERSION})


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """What a plugin declares about itself, in the ``MANIFEST`` of its ``manifest.py``.

    ``plugin_id`` is lowercase snake_case, equals the name of the plugin folder and never
    changes after release. ``factory`` is ``"module:function"``: the module is inside
    ``mtee.plugins.<plugin_id>`` and is imported only when the plugin is enabled.
    ``uses_network`` is shown to the user before the plugin is switched on.
    """

    plugin_id: str
    title: str
    description: str
    version: str
    api_version: int
    factory: str
    uses_network: bool = False
