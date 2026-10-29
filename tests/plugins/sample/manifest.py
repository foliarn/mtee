"""The manifest of the sample plugin; the core reads it before it imports anything else."""

from mtee.plugins.api import PluginManifest

MANIFEST = PluginManifest(
    plugin_id="sample",
    title="Sample plugin",
    description="Adds one of each contribution; the contract tests and the docs use it.",
    version="0.1.0",
    api_version=1,
    factory="mtee.plugins.sample:create",
)
