"""Accent colour of the playing track's cover, computed off the interface thread."""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import Property, QObject, QRunnable, Qt, QThreadPool, Signal, Slot

from mtee.persistence.library_repository import LibraryRepository
from mtee.services.artwork_service import ArtworkService
from mtee.services.cover_palette import accent_from_image
from mtee.services.player_service import PlayerService

__all__ = ["CoverAccentModel"]

_CACHE_LIMIT = 256
_THUMBNAIL_SIZE = 64
Accent = tuple[str, str] | None


class _Bridge(QObject):
    computed = Signal(int, object, object)


class _Compute(QRunnable):
    def __init__(
        self,
        request: int,
        key: tuple[str, int],
        path: str,
        artwork: ArtworkService,
        bridge: _Bridge,
    ) -> None:
        super().__init__()
        self._request = request
        self._key = key
        self._path = path
        self._artwork = artwork
        self._bridge = bridge

    def run(self) -> None:
        accent: Accent = None
        try:
            # A file without artwork gets a generated stand-in image: it has no accent.
            if self._artwork.image_bytes(self._path):
                accent = accent_from_image(self._artwork.thumbnail(self._path, _THUMBNAIL_SIZE))
        except Exception:
            accent = None
        self._bridge.computed.emit(self._request, self._key, accent)


class CoverAccentModel(QObject):
    """``baseColor`` and ``darkColor`` of the cover of the playing track.

    Both are empty and ``hasAccent`` is false when the track has no cover or when none of
    its colours stands out. While a track is being computed the previous accent stays, so
    the interface can fade from one colour to the next.
    """

    accentChanged = Signal()

    def __init__(
        self,
        player: PlayerService,
        library: LibraryRepository,
        parent: QObject | None = None,
        *,
        artwork: ArtworkService | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._library = library
        self._artwork = artwork or ArtworkService()
        self._bridge = _Bridge(self)
        self._bridge.computed.connect(self._on_computed, Qt.ConnectionType.QueuedConnection)
        self._cache: OrderedDict[tuple[str, int], Accent] = OrderedDict()
        self._track_id = ""
        self._request = 0
        self._accent: Accent = None
        player.stateChanged.connect(self._sync)
        self._sync()

    @Property(str, notify=accentChanged)
    def baseColor(self) -> str:
        return self._accent[0] if self._accent else ""

    @Property(str, notify=accentChanged)
    def darkColor(self) -> str:
        return self._accent[1] if self._accent else ""

    @Property(bool, notify=accentChanged)
    def hasAccent(self) -> bool:
        return self._accent is not None

    @Slot()
    def _sync(self) -> None:
        track_id = self._player.state.current_id
        if track_id == self._track_id:
            return
        self._track_id = track_id
        self._request += 1
        source = self._library.artwork_source(track_id) if track_id else None
        if source is None:
            self._apply(None)
            return
        key = (track_id, source[1].generation)
        if key in self._cache:
            self._cache.move_to_end(key)
            self._apply(self._cache[key])
            return
        QThreadPool.globalInstance().start(
            _Compute(self._request, key, str(source[0]), self._artwork, self._bridge)
        )

    @Slot(int, object, object)
    def _on_computed(self, request: int, key: object, accent: object) -> None:
        result: Accent = accent if isinstance(accent, tuple) else None
        if isinstance(key, tuple):
            self._cache[key] = result
            self._cache.move_to_end(key)
            while len(self._cache) > _CACHE_LIMIT:
                self._cache.popitem(last=False)
        if request == self._request:
            self._apply(result)

    def _apply(self, accent: Accent) -> None:
        if accent != self._accent:
            self._accent = accent
            self.accentChanged.emit()
