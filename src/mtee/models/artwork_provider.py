"""Lazy asynchronous thumbnail provider with a bounded per-session LRU cache."""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlImageProviderBase
from PySide6.QtQuick import QQuickImageProvider

from mtee.domain.tracks import SourceRevision
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.artwork_service import ArtworkService, placeholder_image

__all__ = ["ARTWORK_CACHE_LIMIT", "ARTWORK_PROVIDER_ID", "ArtworkProvider"]

_LOGGER = logging.getLogger(__name__)

ARTWORK_PROVIDER_ID = "artwork"
ARTWORK_CACHE_LIMIT = 128 * 1024 * 1024


class ArtworkProvider(QQuickImageProvider):
    """Decode and resize artwork on Qt's image worker threads, never in QML."""

    def __init__(
        self,
        library: LibraryRepository,
        artwork: ArtworkService | None = None,
        *,
        cache_limit: int = ARTWORK_CACHE_LIMIT,
    ) -> None:
        super().__init__(
            QQmlImageProviderBase.ImageType.Image,
            QQmlImageProviderBase.Flag.ForceAsynchronousImageLoading,
        )
        self._library = library
        self._artwork = artwork or ArtworkService()
        self._cache_limit = max(0, cache_limit)
        self._cache: OrderedDict[tuple[str, int, int], QImage] = OrderedDict()
        self._cache_bytes = 0
        self._lock = threading.RLock()

    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:
        """Return ``track-id/generation/size`` after checking the source revision."""
        try:
            parts = image_id.split("/")
            if len(parts) not in {2, 3}:
                raise ValueError("invalid artwork request")
            track_id, generation_text = parts[:2]
            generation = int(generation_text)
            target_size = min(1024, max(1, int(parts[2]))) if len(parts) == 3 else 1024
            if requested_size.isValid():
                target_size = min(target_size, max(requested_size.width(), requested_size.height()))
        except (ValueError, TypeError):
            image = placeholder_image(image_id, 64)
            size.setWidth(image.width())
            size.setHeight(image.height())
            return image
        key = (track_id, generation, target_size)
        self._invalidate_old_revisions(track_id, generation)
        source = self._library.artwork_source(track_id)
        try:
            observed = SourceRevision.observe(source[0]) if source is not None else None
        except OSError:
            observed = None
        cacheable = False
        if (
            source is None
            or source[1].generation != generation
            or observed is None
            or not source[1].matches(observed)
        ):
            image = placeholder_image(track_id, target_size)
        else:
            with self._lock:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    size.setWidth(cached.width())
                    size.setHeight(cached.height())
                    return cached
            try:
                image = self._artwork.thumbnail(source[0], target_size)
                final_revision = SourceRevision.observe(source[0])
                if not source[1].matches(final_revision):
                    image = placeholder_image(track_id, target_size)
                else:
                    cacheable = True
            except Exception:
                # Can fire per thumbnail: debug level keeps the log readable.
                _LOGGER.debug(
                    "Could not decode the artwork of track %s (%s)",
                    track_id,
                    source[0],
                    exc_info=True,
                )
                image = placeholder_image(track_id, target_size)
        size.setWidth(image.width())
        size.setHeight(image.height())
        if source is not None and cacheable:
            self._store(key, image)
        return image

    def _invalidate_old_revisions(self, track_id: str, generation: int) -> None:
        with self._lock:
            stale = [key for key in self._cache if key[0] == track_id and key[1] != generation]
            for key in stale:
                removed = self._cache.pop(key)
                self._cache_bytes -= removed.sizeInBytes()

    def _store(self, key: tuple[str, int, int], image: QImage) -> None:
        cost = image.sizeInBytes()
        if cost > self._cache_limit or self._cache_limit == 0:
            return
        with self._lock:
            previous = self._cache.pop(key, None)
            if previous is not None:
                self._cache_bytes -= previous.sizeInBytes()
            self._cache[key] = image
            self._cache_bytes += cost
            while self._cache_bytes > self._cache_limit and self._cache:
                _, removed = self._cache.popitem(last=False)
                self._cache_bytes -= removed.sizeInBytes()
