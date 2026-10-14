"""Mirror the playback into the system media controls and route their commands back.

The adapter in ``mtee.platform.media_transport`` knows nothing of the player. This
service decides what the system shows, maps commands onto the existing player
actions, and keeps every player access on the interface thread. The cover of the
loaded track is decoded on Qt's thread pool, the way the accent of the cover is.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from contextlib import suppress
from dataclasses import dataclass

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage, QImageWriter

from mtee.domain.playback import PlaybackStatus
from mtee.persistence.library_repository import LibraryRepository
from mtee.platform.media_transport import (
    MediaMetadata,
    MediaTransport,
    TransportCommand,
    TransportState,
)
from mtee.services.artwork_service import ArtworkService
from mtee.services.player_service import PlayerService

__all__ = ["COVER_SIZE", "MediaControls"]

_LOGGER = logging.getLogger(__name__)
COVER_SIZE = 512
_COVER_CACHE_LIMIT = 32
_LOADED_STATUSES = (PlaybackStatus.PLAYING, PlaybackStatus.PAUSED, PlaybackStatus.LOADING)


class _Bridge(QObject):
    """Carries worker and system callbacks to the interface thread."""

    commandReceived = Signal(object)
    coverReady = Signal(int, object, object)


class _CoverJob(QRunnable):
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
        png: bytes | None = None
        try:
            # A file without embedded artwork gets no cover at all, not a stand-in image.
            if self._artwork.image_bytes(self._path):
                png = _encode_png(self._artwork.thumbnail(self._path, COVER_SIZE))
        except Exception:
            _LOGGER.debug("The cover of %s could not be prepared", self._path, exc_info=True)
            png = None
        self._bridge.coverReady.emit(self._request, self._key, png)


@dataclass(slots=True)
class _Shown:
    """What the system currently displays for the loaded track."""

    text: tuple[str, str, str, str]
    cover_key: tuple[str, int] | None
    cover: bytes | None


class MediaControls(QObject):
    """Feed the media flyout from the player and turn media commands into player actions."""

    def __init__(
        self,
        player: PlayerService,
        library: LibraryRepository,
        transport: MediaTransport,
        parent: QObject | None = None,
        *,
        artwork: ArtworkService | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._library = library
        self._transport = transport
        self._artwork = artwork or ArtworkService()
        self._bridge = _Bridge(self)
        self._bridge.commandReceived.connect(self._on_command, Qt.ConnectionType.QueuedConnection)
        self._bridge.coverReady.connect(self._on_cover, Qt.ConnectionType.QueuedConnection)
        self._covers: OrderedDict[tuple[str, int], bytes | None] = OrderedDict()
        self._shown: _Shown | None = None
        self._state: TransportState | None = None
        self._request = 0
        self._closed = False
        player.stateChanged.connect(self._sync)
        transport.set_command_handler(self._bridge.commandReceived.emit)
        self._sync()

    @Slot()
    def _sync(self) -> None:
        if self._closed:
            return
        state = self._player.state
        if state.status in _LOADED_STATUSES and state.current_id:
            playing = state.status is PlaybackStatus.PLAYING or (
                state.status is PlaybackStatus.LOADING and not self._player.pause_pending
            )
            self._push_state(TransportState.PLAYING if playing else TransportState.PAUSED)
            self._show_track(state.current_id)
        else:
            self._push_state(TransportState.STOPPED)
            self._show_track("")

    def _push_state(self, state: TransportState) -> None:
        if state is not self._state:
            self._state = state
            self._transport.set_state(state)

    def _show_track(self, track_id: str) -> None:
        if not track_id:
            # Nothing loaded: a cover still being decoded must not appear later.
            self._request += 1
            if self._shown is not None:
                self._shown = None
                self._transport.set_metadata(None)
            return
        track = self._player.current_track
        title = str(track.get("title") or "")
        artist = str(track.get("artist") or "")
        album = str(track.get("album") or "")
        text = (track_id, title, artist, album)
        if self._shown is not None and self._shown.text == text:
            return
        self._request += 1
        source = self._library.artwork_source(track_id)
        cover_key = (track_id, source[1].generation) if source is not None else None
        cover: bytes | None = None
        if source is not None and cover_key is not None:
            if cover_key in self._covers:
                self._covers.move_to_end(cover_key)
                cover = self._covers[cover_key]
            else:
                self._start_cover(self._request, cover_key, str(source[0]))
        self._shown = _Shown(text=text, cover_key=cover_key, cover=cover)
        self._push_metadata()

    def _start_cover(self, request: int, key: tuple[str, int], path: str) -> None:
        QThreadPool.globalInstance().start(
            _CoverJob(request, key, path, self._artwork, self._bridge)
        )

    def _push_metadata(self) -> None:
        shown = self._shown
        if shown is None:
            return
        _track_id, title, artist, album = shown.text
        self._transport.set_metadata(
            MediaMetadata(
                title=title or "MTEE",
                artist=artist,
                album=album,
                cover_png=shown.cover,
            )
        )

    @Slot(int, object, object)
    def _on_cover(self, request: int, key: object, png: object) -> None:
        if self._closed or not isinstance(key, tuple):
            return
        result = png if isinstance(png, bytes) else None
        self._covers[key] = result
        self._covers.move_to_end(key)
        while len(self._covers) > _COVER_CACHE_LIMIT:
            self._covers.popitem(last=False)
        shown = self._shown
        if request != self._request or shown is None or shown.cover_key != key:
            return
        shown.cover = result
        self._push_metadata()

    @Slot(object)
    def _on_command(self, command: object) -> None:
        if self._closed or not isinstance(command, TransportCommand):
            return
        status = self._player.state.status
        if command is TransportCommand.PLAY:
            # Play only resumes or starts; a track already playing is left alone.
            if status is PlaybackStatus.PLAYING or (
                status is PlaybackStatus.LOADING and not self._player.pause_pending
            ):
                return
            self._player.toggle_play()
        elif command in (TransportCommand.PAUSE, TransportCommand.STOP):
            # Stop pauses rather than releasing the track, so Play resumes it.
            self._player.pause()
        elif command is TransportCommand.NEXT:
            self._player.next()
        elif command is TransportCommand.PREVIOUS:
            self._player.previous()

    def close(self) -> None:
        """Detach from the player and the system; later callbacks are ignored."""
        if self._closed:
            return
        self._closed = True
        with suppress(RuntimeError, TypeError):
            self._player.stateChanged.disconnect(self._sync)
        self._transport.set_command_handler(None)
        self._transport.close()
        self._shown = None


def _encode_png(image: QImage) -> bytes | None:
    if image.isNull():
        return None
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    try:
        if not QImageWriter(buffer, QByteArray(b"PNG")).write(image):
            return None
        data: QByteArray = buffer.data()
        return bytes(data.data())
    finally:
        buffer.close()
