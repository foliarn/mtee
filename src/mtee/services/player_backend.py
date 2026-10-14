"""Backend contract for the shared player service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__ = ["BackendEvent", "BackendEventHandler", "PlayerBackend", "PlayerBackendError"]


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

    def load(self, path: Path, session_id: int) -> None: ...

    def set_paused(self, paused: bool) -> None: ...

    def seek(self, position_us: int) -> None: ...

    def set_volume(self, value: int) -> None: ...

    def set_gain_db(self, value: float) -> None: ...

    def position_us(self) -> int | None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...
