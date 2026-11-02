"""Backend contract for the shared player service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from mtee.domain.source_tracks import PlayableSource

__all__ = [
    "BackendEvent",
    "BackendEventHandler",
    "GaplessPlayerBackend",
    "PlayerBackend",
    "PlayerBackendError",
]


class PlayerBackendError(RuntimeError):
    """A native player could not be started or commanded."""


@dataclass(frozen=True, slots=True)
class BackendEvent:
    """Value copied out of a backend callback before leaving its native thread."""

    name: str
    session_id: int
    value: object = None


BackendEventHandler = Callable[[BackendEvent], None]


class PlayerBackend(Protocol):
    """Small native-player interface with no QML or database dependencies."""

    def set_event_handler(self, handler: BackendEventHandler | None) -> None: ...

    def load(self, source: Path | PlayableSource, session_id: int, /) -> None:
        """Replace what plays by ``source``: a file path or a ``PlayableSource`` (url, headers)."""
        ...

    def set_paused(self, paused: bool) -> None: ...

    def seek(self, position_us: int) -> None: ...

    def set_volume(self, value: int) -> None: ...

    def set_gain_db(self, value: float) -> None: ...

    def position_us(self) -> int | None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


@runtime_checkable
class GaplessPlayerBackend(PlayerBackend, Protocol):
    """A backend that can open the next entry ahead of time and switch with no gap.

    ``queue_next`` appends the entry that follows the playing one, with the gain it is
    played at; the backend switches to it at the exact end of the playing entry and then
    reports it with the events of ``session_id``. ``clear_next`` forgets it. Backends
    without these methods simply load each entry when the previous one has ended.
    """

    def queue_next(
        self, source: Path | PlayableSource, session_id: int, gain_db: float, /
    ) -> None: ...

    def clear_next(self) -> None: ...
