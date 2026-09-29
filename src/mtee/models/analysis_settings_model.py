"""Qt model of the Analysis settings tab, persisted in the settings table."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.domain.analysis import BPM_LIMITS, AnalysisSettings
from mtee.domain.musical_key import KEY_NOTATIONS
from mtee.persistence.settings_repository import SettingsRepository

__all__ = ["SETTING_ANALYSIS", "AnalysisSettingsModel"]

SETTING_ANALYSIS = "analysis/settings"


class AnalysisSettingsModel(QObject):
    """Expose the choices of the Analysis tab and keep them across sessions."""

    changed = Signal()

    def __init__(self, repository: SettingsRepository, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._settings = self._load()

    @property
    def settings(self) -> AnalysisSettings:
        return self._settings

    @Property(str, notify=changed)
    def notation(self) -> str:
        return self._settings.notation

    @Property(int, notify=changed)
    def bpmMin(self) -> int:
        return self._settings.bpm_min

    @Property(int, notify=changed)
    def bpmMax(self) -> int:
        return self._settings.bpm_max

    @Property(int, notify=changed)
    def parallelJobs(self) -> int:
        return self._settings.parallel_jobs

    @Property(int, notify=changed)
    def bpmDecimals(self) -> int:
        return self._settings.bpm_decimals

    @Property(bool, notify=changed)
    def writeTags(self) -> bool:
        return self._settings.write_tags

    @Slot(str)
    def setNotation(self, notation: str) -> None:
        if notation in KEY_NOTATIONS:
            self._update(notation=notation)

    @Slot(int)
    def setBpmMin(self, value: int) -> None:
        """Change the lowest tempo; the highest follows to keep one full octave."""
        low = min(max(int(value), BPM_LIMITS[0]), BPM_LIMITS[1] // 2)
        self._update(bpm_min=low, bpm_max=max(self._settings.bpm_max, 2 * low))

    @Slot(int)
    def setBpmMax(self, value: int) -> None:
        """Change the highest tempo; the lowest follows to keep one full octave."""
        high = min(max(int(value), 2 * BPM_LIMITS[0]), BPM_LIMITS[1])
        self._update(bpm_max=high, bpm_min=min(self._settings.bpm_min, high // 2))

    @Slot(int)
    def setParallelJobs(self, value: int) -> None:
        self._update(parallel_jobs=int(value))

    @Slot(int)
    def setBpmDecimals(self, value: int) -> None:
        self._update(bpm_decimals=int(value))

    @Slot(bool)
    def setWriteTags(self, value: bool) -> None:
        self._update(write_tags=bool(value))

    def _update(self, **changes: object) -> None:
        updated = replace(self._settings, **changes).normalized()
        if updated == self._settings:
            return
        self._settings = updated
        self._repository.set_json(
            SETTING_ANALYSIS,
            {
                "notation": updated.notation,
                "bpm_min": updated.bpm_min,
                "bpm_max": updated.bpm_max,
                "parallel_jobs": updated.parallel_jobs,
                "bpm_decimals": updated.bpm_decimals,
                "write_tags": updated.write_tags,
            },
        )
        self.changed.emit()

    def _load(self) -> AnalysisSettings:
        stored = self._repository.get_json(SETTING_ANALYSIS, {})
        defaults = AnalysisSettings()
        if not isinstance(stored, dict):
            return defaults
        try:
            return AnalysisSettings(
                notation=str(stored.get("notation", defaults.notation)),
                bpm_min=int(stored.get("bpm_min", defaults.bpm_min)),
                bpm_max=int(stored.get("bpm_max", defaults.bpm_max)),
                parallel_jobs=int(stored.get("parallel_jobs", defaults.parallel_jobs)),
                bpm_decimals=int(stored.get("bpm_decimals", defaults.bpm_decimals)),
                write_tags=bool(stored.get("write_tags", defaults.write_tags)),
            ).normalized()
        except (TypeError, ValueError):
            return defaults
