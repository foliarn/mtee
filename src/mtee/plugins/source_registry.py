"""The ``TrackSource`` of each running plugin, as the player and the cover provider call them."""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence

from mtee.domain.source_tracks import PlayableSource
from mtee.plugins.api import TrackSource
from mtee.plugins.loader import LoadedPlugin, PluginStatus
from mtee.services.track_sources import SourceOpenError

__all__ = ["TrackSourceRegistry"]

_LOGGER = logging.getLogger(__name__)


class TrackSourceRegistry:
    """Looks up the ``TrackSource`` a plugin registered and calls it safely.

    ``open`` and ``cover`` are called from job and image threads; the registry is filled once,
    after the plugins loaded, and read afterwards.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._titles: dict[str, str] = {}
        self._sources: dict[str, TrackSource] = {}

    def register(self, records: Sequence[LoadedPlugin]) -> None:
        """Remember the title of every plugin and the ``TrackSource`` of the running ones."""
        titles: dict[str, str] = {}
        sources: dict[str, TrackSource] = {}
        for record in records:
            titles[record.plugin_id] = record.title
            if record.status is not PluginStatus.RUNNING:
                continue
            for contribution in record.contributions:
                if isinstance(contribution, TrackSource):
                    sources[record.plugin_id] = contribution
        with self._lock:
            self._titles = titles
            self._sources = sources

    @property
    def running_plugin_ids(self) -> frozenset[str]:
        """The plugins that can open their tracks."""
        with self._lock:
            return frozenset(self._sources)

    def plugin_title(self, plugin_id: str) -> str:
        with self._lock:
            return self._titles.get(plugin_id, plugin_id)

    def open(self, plugin_id: str, source_key: str) -> PlayableSource:
        """Resolve a track of ``plugin_id``; raises ``SourceOpenError`` naming the plugin."""
        with self._lock:
            source = self._sources.get(plugin_id)
        title = self.plugin_title(plugin_id)
        if source is None:
            raise SourceOpenError(
                f"{title} is not running, so its tracks cannot be played. "
                "Switch the plugin on in Plugins and restart MTEE."
            )
        try:
            result = source.open(source_key)
        except Exception as error:
            _LOGGER.warning("Plugin %s could not open a track: %s", plugin_id, error)
            raise SourceOpenError(f"{title} could not open this track: {error}") from error
        if not isinstance(result, PlayableSource):
            raise SourceOpenError(
                f"{title} could not open this track: it did not return a PlayableSource."
            )
        return result

    def cover(self, plugin_id: str, source_key: str) -> bytes | None:
        """Return the cover bytes of a track, or ``None``; a failing plugin gives ``None``."""
        with self._lock:
            source = self._sources.get(plugin_id)
        if source is None or source.cover is None:
            return None
        try:
            data = source.cover(source_key)
        except Exception as error:
            _LOGGER.debug("Plugin %s could not give a cover: %s", plugin_id, error)
            return None
        return data if isinstance(data, bytes) and data else None
