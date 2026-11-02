"""What the player needs to reach the audio of a track that has no file (plan 125.2)."""

from __future__ import annotations

from typing import Protocol

from mtee.domain.source_tracks import PlayableSource

__all__ = ["SourceOpenError", "TrackSourceOpener"]


class SourceOpenError(RuntimeError):
    """The audio of a plugin track could not be reached; the message names the plugin."""

    readable = True


class TrackSourceOpener(Protocol):
    """Resolves a plugin track into something the player can load.

    ``open`` may take a network round trip: the player calls it off the graphical thread.
    It raises ``SourceOpenError`` with a sentence that names the plugin.
    """

    def open(self, plugin_id: str, source_key: str) -> PlayableSource: ...

    def plugin_title(self, plugin_id: str) -> str: ...
