"""The manifest of the remote plugin; the core reads it before it imports anything else."""

from mtee.plugins.api import PluginManifest

MANIFEST = PluginManifest(
    plugin_id="remote",
    title="MTEE Remote",
    description="Syncs MTEE with your MTEE Remote server and shows its state in the window header.",
    version="0.1.0",
    api_version=1,
    factory="mtee.plugins.remote:create",
    uses_network=True,
)
