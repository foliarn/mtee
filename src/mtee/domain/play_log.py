"""Permanent listening log: the counting rule and the tracker of the open play event.

The tracker never reads a clock. Callers pass a ``ClockReading``: a monotonic
reading in microseconds, used for every duration, and the UTC wall time, read
once when the event becomes audible. Loading, pauses and errors add no heard
time. A seek closes the playing span at the seek instant and never adds the
skipped span, because heard time only grows while the clock runs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from mtee.domain.time import MICROSECONDS_PER_SECOND

__all__ = [
    "COUNTING_THRESHOLD_US",
    "ClockReading",
    "ListeningPeriod",
    "PlayEvent",
    "PlayTracker",
    "PlayedTrack",
    "format_listened_at",
    "is_counted_play",
]

# A play counts once at least 30 s were heard. A track shorter than this counts when
# it is played to its end (the Spotify rule).
COUNTING_THRESHOLD_US = 30 * MICROSECONDS_PER_SECOND


def format_listened_at(instant: datetime | None) -> str:
    """The local date and time of a listening for the English UI, or a dash when none."""
    if instant is None:
        return "—"
    local = instant.astimezone() if instant.tzinfo is not None else instant
    return local.strftime("%d %b %Y, %H:%M")


@dataclass(frozen=True, slots=True)
class ClockReading:
    """One instant: a monotonic reading in microseconds and the UTC wall time."""

    mono_us: int
    wall: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.mono_us, int) or isinstance(self.mono_us, bool):
            raise TypeError("mono_us must be an integer of microseconds")
        if self.wall.utcoffset() is None:
            raise ValueError("wall must be a timezone-aware datetime")


@dataclass(frozen=True, slots=True)
class PlayedTrack:
    """The snapshot of a track taken when its event opens."""

    track_id: str
    path: str
    artist: str = ""
    title: str = ""
    album: str = ""
    duration_us: int = 0


@dataclass(frozen=True, slots=True)
class PlayEvent:
    """One closed listening, ready to be appended to the log."""

    event_id: str
    track: PlayedTrack
    started_at: datetime
    ended_at: datetime
    heard_ms: int
    counted: bool


@dataclass(frozen=True, slots=True)
class ListeningPeriod:
    """UTC period ``[start, end)``. A ``None`` side is unbounded; both ``None`` is all time."""

    start: datetime | None = None
    end: datetime | None = None

    def __post_init__(self) -> None:
        for bound in (self.start, self.end):
            if bound is not None and bound.utcoffset() is None:
                raise ValueError("period bounds must be timezone-aware datetimes")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("period end must be after its start")


def is_counted_play(heard_us: int, duration_us: int, completed: bool) -> bool:
    """Return whether a listening counts as a play.

    ``completed`` means the decoder reached the end of the file; it only matters for
    tracks whose duration is known and shorter than the threshold.
    """
    if heard_us >= COUNTING_THRESHOLD_US:
        return True
    return completed and 0 < duration_us < COUNTING_THRESHOLD_US


@dataclass(slots=True)
class _OpenEvent:
    event_id: str
    track: PlayedTrack
    heard_us: int = 0
    playing_since_us: int | None = None
    started_at: datetime | None = None
    started_mono_us: int | None = None


class PlayTracker:
    """Track the heard time of the single event that is open at a time.

    ``open`` starts a new event and closes the previous one. A restart of the same
    track is an ``open`` as well, so it always produces a new event.
    """

    def __init__(self, *, new_event_id: Callable[[], str] = lambda: str(uuid4())) -> None:
        self._new_event_id = new_event_id
        self._open: _OpenEvent | None = None

    @property
    def is_open(self) -> bool:
        return self._open is not None

    def open(self, track: PlayedTrack, now: ClockReading, *, playing: bool) -> PlayEvent | None:
        """Close the previous event with ``completed=False`` and open a new one."""
        closed = self.close(now, completed=False)
        self._open = _OpenEvent(self._new_event_id(), track)
        if playing:
            self._start_clock(now)
        return closed

    def set_playing(self, playing: bool, now: ClockReading) -> None:
        """Run or stop the heard-time clock of the open event."""
        event = self._open
        if event is None:
            return
        if playing:
            self._start_clock(now)
        else:
            _accrue(event, now)
            event.playing_since_us = None

    def checkpoint(self, now: ClockReading) -> None:
        """Close the playing span at ``now``; used when the playhead jumps (seek)."""
        if self._open is not None:
            _accrue(self._open, now)

    def close(self, now: ClockReading, *, completed: bool) -> PlayEvent | None:
        """Close the open event, if any. Events that were never audible are dropped."""
        event = self._open
        if event is None:
            return None
        self._open = None
        _accrue(event, now)
        if event.started_at is None or event.started_mono_us is None or event.heard_us <= 0:
            return None
        ended_at = event.started_at + timedelta(microseconds=now.mono_us - event.started_mono_us)
        return PlayEvent(
            event_id=event.event_id,
            track=event.track,
            started_at=event.started_at,
            ended_at=ended_at,
            heard_ms=event.heard_us // 1000,
            counted=is_counted_play(event.heard_us, event.track.duration_us, completed),
        )

    def _start_clock(self, now: ClockReading) -> None:
        event = self._open
        if event is None or event.playing_since_us is not None:
            return
        event.playing_since_us = now.mono_us
        if event.started_at is None:
            event.started_at = now.wall
            event.started_mono_us = now.mono_us


def _accrue(event: _OpenEvent, now: ClockReading) -> None:
    """Add the time since the clock started to the heard time, and restart it at ``now``."""
    if event.playing_since_us is None:
        return
    event.heard_us += max(0, now.mono_us - event.playing_since_us)
    event.playing_since_us = now.mono_us
