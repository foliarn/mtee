"""Immutable playback state shared by the native service and Qt models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = ["PlaybackState", "PlaybackStatus"]


class PlaybackStatus(StrEnum):
    IDLE = "Idle"
    LOADING = "Loading"
    PLAYING = "Playing"
    PAUSED = "Paused"
    ENDED = "Ended"
    ERROR = "Error"


@dataclass(frozen=True, slots=True)
class PlaybackState:
    """Snapshot of the player; times are integer microseconds throughout MTEE."""

    status: PlaybackStatus = PlaybackStatus.IDLE
    track_ids: tuple[str, ...] = ()
    current_id: str = ""
    current_index: int = -1
    position_us: int = 0
    duration_us: int | None = None
    seeking: bool = False
    volume: int = 72
    muted: bool = False
    seekable: bool = False
    source: str = ""
    source_title: str = ""
    error_message: str = ""
    session_id: int = 0
    codec: str = ""
    sample_rate: int | None = None
    channels: str = ""
    shuffle: bool = False
    repeat: str = "off"
    history: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_playing(self) -> bool:
        return self.status is PlaybackStatus.PLAYING

    @property
    def has_track(self) -> bool:
        return bool(self.current_id)
