"""The "Hide tracks not on this device" choice of the track lists (plan 125.3).

One stored choice serves every track list. The filter is in force only while a plugin provides
``TrackAvailability``; without one, no track is asked about and nothing changes on screen.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from mtee.plugins.availability_registry import TrackAvailabilityRegistry

__all__ = ["SETTING_HIDE_NOT_ON_DEVICE", "AvailabilityFilter"]

SETTING_HIDE_NOT_ON_DEVICE = "library/hide_not_on_device"


class _Settings(Protocol):
    def get_json(self, key: str, default: Any = None) -> Any: ...

    def set_json(self, key: str, value: Any) -> None: ...


class AvailabilityFilter:
    """The stored choice, the provider that answers, and the tracks to leave out."""

    def __init__(self) -> None:
        self._registry: TrackAvailabilityRegistry | None = None
        self._settings: _Settings | None = None
        self._wanted = False

    def attach(self, registry: TrackAvailabilityRegistry, settings: _Settings) -> None:
        """Use ``registry`` for the answers and the setting of ``settings`` for the choice."""
        self._registry = registry
        self._settings = settings
        self._wanted = bool(settings.get_json(SETTING_HIDE_NOT_ON_DEVICE, False))

    @property
    def provided(self) -> bool:
        """Return whether a running plugin provides track availability."""
        return self._registry is not None and self._registry.provided

    @property
    def wanted(self) -> bool:
        """Return the stored choice, whether or not a plugin answers for it."""
        return self._wanted

    @property
    def hiding(self) -> bool:
        """Return whether tracks are being left out: a provider exists and the choice is on."""
        return self.provided and self._wanted

    def set_wanted(self, value: bool) -> None:
        """Store the choice for every track list."""
        self._wanted = value
        if self._settings is not None:
            self._settings.set_json(SETTING_HIDE_NOT_ON_DEVICE, value)

    def remote_ids(self, track_ids: Sequence[str]) -> frozenset[str]:
        """Return the tracks to leave out among ``track_ids``; nothing is asked unless hiding."""
        if self._registry is None or not self.hiding:
            return frozenset()
        return self._registry.remote_ids(track_ids)
