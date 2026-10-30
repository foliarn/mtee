"""The Plugins page of Settings: the plugins found at start, with the state each had.

The page lists the plugins of the plugins folder and of the folders given with ``--plugin-dir``
for this run. A switch only changes the saved choice: it applies at the next start, so a plugin
switched off stays ``Running`` until then and a plugin switched on stays ``Disabled``.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.plugins.loader import (
    DiscoveredPlugin,
    LoadedPlugin,
    PluginManager,
    PluginPreferences,
    PluginStatus,
)

__all__ = ["PluginSettingsModel"]


class PluginSettingsModel(QObject):
    """State of the Plugins page; every change is saved at once and applies after a restart."""

    changed = Signal()

    def __init__(
        self,
        manager: PluginManager,
        preferences: PluginPreferences,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._preferences = preferences

    def is_available(self) -> bool:
        """Whether a plugin was found: without one the Plugins page does not exist."""
        return bool(self._discovered())

    available = Property(bool, is_available, notify=changed)

    @Property(list, notify=changed)
    def plugins(self) -> list[dict[str, Any]]:
        """One entry per plugin found: its manifest, state, error and switch."""
        started = {record.plugin_id: record for record in self._manager.plugins}
        enabled = set(self._preferences.enabled())
        return [
            _entry(found, started.get(found.plugin_id), found.plugin_id in enabled)
            for found in self._discovered()
        ]

    @Slot(str, bool)
    def setEnabled(self, plugin_id: str, enabled: bool) -> None:
        """Save the choice of the user; the plugin starts or stops at the next start."""
        if any(found.plugin_id == plugin_id and found.is_valid for found in self._discovered()):
            self._preferences.set_enabled(plugin_id, enabled)
            self.changed.emit()

    def _discovered(self) -> list[DiscoveredPlugin]:
        return [record.discovered for record in self._manager.plugins]


def _entry(found: DiscoveredPlugin, record: LoadedPlugin | None, enabled: bool) -> dict[str, Any]:
    """The Settings entry of one plugin: what is shown, and the switch."""
    manifest = found.manifest
    status = record.status if record is not None else PluginStatus.DISABLED
    error = ""
    pending = ""
    if not found.is_valid:
        status = PluginStatus.FAILED
        error = found.error
    elif status is PluginStatus.FAILED and record is not None:
        error = (
            f"Could not start: {record.error.rstrip('.')}. "
            "The plugin was switched off for this session and MTEE kept running."
        )
    elif status is PluginStatus.RUNNING and not enabled:
        pending = "You switched this plugin off. It stays active until MTEE restarts."
    elif status is PluginStatus.DISABLED and enabled:
        pending = "You switched this plugin on. It starts the next time MTEE starts."
    return {
        "id": found.plugin_id,
        "title": manifest.title if manifest is not None else found.plugin_id,
        "version": manifest.version if manifest is not None else "",
        "description": manifest.description if manifest is not None else "",
        "network": bool(manifest.uses_network) if manifest is not None else False,
        "status": status.name.lower(),
        "error": error,
        "pending": pending,
        "enabled": enabled and found.is_valid,
        "switchable": found.is_valid,
    }
