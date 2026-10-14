"""Qt model of the playback loudness normalization choices, kept in the settings table."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.domain.loudness import NORMALIZATION_LEVELS, NormalizationSettings
from mtee.persistence.settings_repository import SettingsRepository

__all__ = ["SETTING_NORMALIZATION", "PlaybackSettingsModel"]

SETTING_NORMALIZATION = "playback/normalization"


class PlaybackSettingsModel(QObject):
    """Expose the normalization switch and target to the Settings page, and keep them."""

    changed = Signal()

    def __init__(self, repository: SettingsRepository, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._settings = self._load()

    @property
    def settings(self) -> NormalizationSettings:
        return self._settings

    @Property(bool, notify=changed)
    def normalizationEnabled(self) -> bool:
        return self._settings.enabled

    @Property(str, notify=changed)
    def normalizationLevel(self) -> str:
        return self._settings.level

    @Slot(bool)
    def setNormalizationEnabled(self, value: bool) -> None:
        self._update(enabled=bool(value))

    @Slot(str)
    def setNormalizationLevel(self, level: str) -> None:
        if level in NORMALIZATION_LEVELS:
            self._update(level=level)

    def _update(self, **changes: object) -> None:
        updated = replace(self._settings, **changes).normalized()
        if updated == self._settings:
            return
        self._settings = updated
        self._repository.set_json(
            SETTING_NORMALIZATION,
            {"enabled": updated.enabled, "level": updated.level},
        )
        self.changed.emit()

    def _load(self) -> NormalizationSettings:
        stored = self._repository.get_json(SETTING_NORMALIZATION, {})
        defaults = NormalizationSettings()
        if not isinstance(stored, dict):
            return defaults
        enabled = stored.get("enabled", defaults.enabled)
        level = stored.get("level", defaults.level)
        return NormalizationSettings(
            enabled=enabled if type(enabled) is bool else defaults.enabled,
            level=level if isinstance(level, str) else defaults.level,
        ).normalized()
