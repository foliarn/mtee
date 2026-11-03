"""The ``TrackAvailability`` of the running plugin, as the track lists ask for it (plan 125.3)."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from mtee.plugins.api import TrackAvailability
from mtee.plugins.loader import LoadedPlugin, PluginStatus

__all__ = ["TrackAvailabilityRegistry"]

_LOGGER = logging.getLogger(__name__)
REMOTE = "remote"


class TrackAvailabilityRegistry:
    """Asks the one running plugin that provides ``TrackAvailability`` which tracks are remote.

    The loader keeps at most one provider. The track lists call ``remote_ids`` on the graphical
    thread while they draw; a track the provider does not name counts as local.
    """

    def __init__(self) -> None:
        self._plugin_id = ""
        self._provider: TrackAvailability | None = None

    def register(self, records: Sequence[LoadedPlugin]) -> None:
        """Remember the ``TrackAvailability`` of the first running plugin that declares one."""
        self._provider = None
        for record in records:
            if record.status is not PluginStatus.RUNNING:
                continue
            for contribution in record.contributions:
                if isinstance(contribution, TrackAvailability):
                    self._plugin_id = record.plugin_id
                    self._provider = contribution
                    return

    @property
    def provided(self) -> bool:
        """Return whether a running plugin provides track availability."""
        return self._provider is not None

    def remote_ids(self, track_ids: Sequence[str]) -> frozenset[str]:
        """Return the identifiers among ``track_ids`` that the provider reports as remote.

        Nothing is asked when no plugin provides availability or ``track_ids`` is empty. A
        provider that raises, or does not answer with a mapping, counts every track as local.
        """
        provider = self._provider
        wanted = [track_id for track_id in track_ids if track_id]
        if provider is None or not wanted:
            return frozenset()
        try:
            answer = provider.status(wanted)
        except Exception:
            _LOGGER.exception(
                "Plugin %s could not give the availability of its tracks.", self._plugin_id
            )
            return frozenset()
        if not isinstance(answer, Mapping):
            _LOGGER.warning(
                "Plugin %s gave no mapping of availability; all tracks are local.", self._plugin_id
            )
            return frozenset()
        known = frozenset(wanted)
        return frozenset(
            str(track_id)
            for track_id, value in answer.items()
            if value == REMOTE and str(track_id) in known
        )
