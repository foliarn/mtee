"""The failing sample plugin: ``create`` always raises."""

from mtee.plugins.api import PluginContext, PluginService

FAILURE = "The sample plugin was made to fail."


def create(context: PluginContext) -> PluginService:
    """Raise, as a plugin does when a dependency or a setting is missing."""
    raise RuntimeError(FAILURE)
