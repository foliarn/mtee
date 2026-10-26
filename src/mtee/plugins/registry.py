"""Plugin switch of the release.

MTEE 0.1 ships no bundled plugin. ``PLUGIN_UI_ENABLED`` is ``False``, so no plugin entry
is shown and no plugin service is built. The switch stays in place so that the views which
depend on it keep their v0.1 behaviour; a plugin platform can later add its own registry
here without changing the core.
"""

from __future__ import annotations

__all__ = ["PLUGIN_UI_ENABLED", "plugin_ui_enabled"]

# v0.1 ships without plugins. Plugin entries and services stay hidden while this is False.
PLUGIN_UI_ENABLED = False


def plugin_ui_enabled() -> bool:
    """Return whether the plugin entries and services are active in this build."""
    return PLUGIN_UI_ENABLED
