"""A plugin whose factory raises: the core must disable it alone and keep running."""

from mtee.plugins.api import PluginManifest

MANIFEST = PluginManifest(
    plugin_id="sample_failing",
    title="Sample plugin (fails)",
    description="Its factory raises, to check that one plugin cannot stop MTEE.",
    version="0.1.0",
    api_version=1,
    factory="mtee.plugins.sample_failing:create",
)
