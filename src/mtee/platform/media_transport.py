"""System media transport: Windows System Media Transport Controls behind a small adapter.

On Windows, ``WindowsMediaTransport`` publishes a session through a
``Windows.Media.Playback.MediaPlayer`` whose command manager is disabled: the
player itself stays silent and only its ``SystemMediaTransportControls`` is used.
The session feeds the media flyout, the lock screen and the hardware media keys,
Bluetooth headphone buttons included.

Everywhere else, or when the Windows runtime cannot be loaded, the factory returns
``NullMediaTransport``: the application starts and simply has no system controls.

Button presses arrive on a Windows runtime thread. The adapter forwards them to the
command handler without touching Qt; the owner is responsible for marshalling them to
the interface thread.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

__all__ = [
    "CommandHandler",
    "MediaMetadata",
    "MediaTransport",
    "NullMediaTransport",
    "TransportCommand",
    "TransportState",
    "WindowsMediaTransport",
    "command_for_button",
    "create_media_transport",
]

_LOGGER = logging.getLogger(__name__)

# Values of Windows.Media.SystemMediaTransportControlsButton, kept as plain integers so
# that this module imports on every platform.
_BUTTON_PLAY = 0
_BUTTON_PAUSE = 1
_BUTTON_STOP = 2
_BUTTON_NEXT = 6
_BUTTON_PREVIOUS = 7


class TransportCommand(Enum):
    """A request from outside the window, such as a media key."""

    PLAY = "play"
    PAUSE = "pause"
    STOP = "stop"
    NEXT = "next"
    PREVIOUS = "previous"


class TransportState(Enum):
    """The playback state shown to the system."""

    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class MediaMetadata:
    """What the media flyout shows for the loaded track.

    ``cover_png`` is an encoded image; the system decodes it.
    """

    title: str
    artist: str = ""
    album: str = ""
    cover_png: bytes | None = None


CommandHandler = Callable[[TransportCommand], None]


class MediaTransport(Protocol):
    """Everything the application needs from the system media controls."""

    def set_command_handler(self, handler: CommandHandler | None) -> None: ...

    def set_metadata(self, metadata: MediaMetadata | None) -> None: ...

    def set_state(self, state: TransportState) -> None: ...

    def close(self) -> None: ...


class NullMediaTransport:
    """Silent stand-in used when the system controls are unavailable."""

    def set_command_handler(self, handler: CommandHandler | None) -> None:
        return

    def set_metadata(self, metadata: MediaMetadata | None) -> None:
        return

    def set_state(self, state: TransportState) -> None:
        return

    def close(self) -> None:
        return


def command_for_button(button: int) -> TransportCommand | None:
    """Map a ``SystemMediaTransportControlsButton`` value; other buttons are ignored."""
    return _BUTTON_COMMANDS.get(int(button))


_BUTTON_COMMANDS: dict[int, TransportCommand] = {
    _BUTTON_PLAY: TransportCommand.PLAY,
    _BUTTON_PAUSE: TransportCommand.PAUSE,
    _BUTTON_STOP: TransportCommand.STOP,
    _BUTTON_NEXT: TransportCommand.NEXT,
    _BUTTON_PREVIOUS: TransportCommand.PREVIOUS,
}


class WindowsMediaTransport:
    """System Media Transport Controls of a desktop process, through pywinrt.

    Construction raises when the Windows runtime is unavailable; use
    ``create_media_transport`` to fall back silently.
    """

    def __init__(self) -> None:
        # Imported here: the projections exist only on Windows.
        from winrt.runtime import ApartmentType, init_apartment
        from winrt.windows.media import MediaPlaybackStatus, MediaPlaybackType
        from winrt.windows.media.playback import MediaPlayer
        from winrt.windows.storage.streams import (
            DataWriter,
            InMemoryRandomAccessStream,
            RandomAccessStreamReference,
        )

        self._playback_type = MediaPlaybackType
        self._data_writer = DataWriter
        self._stream_class = InMemoryRandomAccessStream
        self._reference_class = RandomAccessStreamReference
        self._status_values = {
            TransportState.PLAYING: MediaPlaybackStatus.PLAYING,
            TransportState.PAUSED: MediaPlaybackStatus.PAUSED,
            TransportState.STOPPED: MediaPlaybackStatus.STOPPED,
        }
        self._handler: CommandHandler | None = None
        self._stream: Any = None
        self._closed = False
        # The interface thread is a single-threaded COM apartment, where the blocking
        # calls that fill a stream are refused. The covers are therefore encoded on one
        # worker that joins the multithreaded apartment.
        self._stream_worker = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="mtee-media-cover",
            initializer=init_apartment,
            initargs=(ApartmentType.MULTI_THREADED,),
        )
        self._player = MediaPlayer()
        try:
            # The player plays nothing; only its system transport controls are used.
            self._player.command_manager.is_enabled = False
            controls = self._player.system_media_transport_controls
            controls.is_enabled = True
            controls.is_play_enabled = True
            controls.is_pause_enabled = True
            controls.is_stop_enabled = True
            controls.is_next_enabled = True
            controls.is_previous_enabled = True
            controls.playback_status = MediaPlaybackStatus.STOPPED
            self._controls = controls
            self._token = controls.add_button_pressed(self._on_button_pressed)
        except Exception:
            self._stream_worker.shutdown(wait=False)
            self._player.close()
            raise

    def set_command_handler(self, handler: CommandHandler | None) -> None:
        self._handler = handler

    def set_metadata(self, metadata: MediaMetadata | None) -> None:
        if self._closed:
            return
        try:
            stream: Any = None
            reference: Any = None
            if metadata is not None and metadata.cover_png:
                stream, reference = self._stream_worker.submit(
                    self._encode_cover, metadata.cover_png
                ).result()
            updater = self._controls.display_updater
            updater.clear_all()
            if metadata is not None:
                updater.type = self._playback_type.MUSIC
                properties = updater.music_properties
                properties.title = metadata.title
                properties.artist = metadata.artist
                properties.album_title = metadata.album
                if reference is not None:
                    updater.thumbnail = reference
            updater.update()
            # The system reads the stream later: keep it alive until it is replaced.
            self._stream = stream
        except Exception:
            _LOGGER.warning("The system media information could not be updated", exc_info=True)

    def set_state(self, state: TransportState) -> None:
        if self._closed:
            return
        try:
            self._controls.playback_status = self._status_values[state]
        except Exception:
            _LOGGER.warning("The system playback state could not be updated", exc_info=True)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._handler = None
        try:
            self._controls.remove_button_pressed(self._token)
        except Exception:
            _LOGGER.debug("Could not remove the media button handler", exc_info=True)
        self._stream_worker.shutdown(wait=False)
        try:
            self._player.close()
        except Exception:
            _LOGGER.debug("Could not close the media player", exc_info=True)
        self._stream = None

    def _encode_cover(self, data: bytes) -> tuple[Any, Any]:
        """Run on the multithreaded worker: copy the encoded cover into a readable stream."""
        stream = self._stream_class()
        writer = self._data_writer(stream.get_output_stream_at(0))
        writer.write_bytes(data)
        writer.store_async().get()
        writer.flush_async().get()
        writer.detach_stream()
        stream.seek(0)
        return stream, self._reference_class.create_from_stream(stream)

    def _on_button_pressed(self, sender: object, args: Any) -> None:
        """Runs on a Windows runtime thread: no Qt object is touched here."""
        handler = self._handler
        if handler is None:
            return
        command = command_for_button(args.button)
        if command is None:
            return
        try:
            handler(command)
        except Exception:
            _LOGGER.exception("A media command could not be forwarded")


def create_media_transport() -> MediaTransport:
    """The Windows transport when it can be created, otherwise a silent stand-in."""
    if sys.platform != "win32":
        return NullMediaTransport()
    try:
        return WindowsMediaTransport()
    except Exception as error:
        _LOGGER.warning("Windows media controls are unavailable: %s", error)
        return NullMediaTransport()
