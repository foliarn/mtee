"""Scrubbing the playing track with the mouse on the waveform (plan 100).

``ScrubSession`` is a pure state machine: it receives timestamped mouse events and
returns the commands the player must execute. It has no Qt and no clock of its own,
which makes every rule testable. Ratios are positions on the waveform from ``0`` to
``1``; the mouse may give values below 0 or above 1 while it is held outside the bars.

Rules, in order of appearance:

* pressing seeks to that point and makes sure the track plays;
* while held, the sound follows the mouse with at most one seek per ``seek_interval_ms``;
* above ``fast_px_per_s`` the sound is cut and nothing is sought, until the mouse has been
  slower than that for ``slow_ms`` in a row: then the current point is sought and the
  sound returns;
* held beyond the left edge, the position stays at the start;
* held beyond the right edge, nothing is sought (a seek to the end would finish the track
  while the button is still down) and the sound is cut: releasing there asks for the next
  track, releasing after coming back inside does not.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

__all__ = [
    "EnsurePlaying",
    "Next",
    "ScrubCommand",
    "ScrubSession",
    "Seek",
    "Silence",
]

SEEK_INTERVAL_MS = 100
FAST_PX_PER_S = 2000.0
SLOW_MS = 80
SPEED_WINDOW_MS = 60


@dataclass(frozen=True, slots=True)
class Seek:
    """Move playback to this position, as a ratio in ``[0, 1]``."""

    ratio: float


@dataclass(frozen=True, slots=True)
class Silence:
    """Cut or restore the sound without changing the user's volume."""

    on: bool


@dataclass(frozen=True, slots=True)
class EnsurePlaying:
    """Resume playback if it is paused."""


@dataclass(frozen=True, slots=True)
class Next:
    """Skip to the next track of the queue."""


ScrubCommand = Seek | Silence | EnsurePlaying | Next


def _clamp(ratio: float) -> float:
    return max(0.0, min(1.0, ratio))


class ScrubSession:
    def __init__(
        self,
        width_px: float,
        *,
        seek_interval_ms: int = SEEK_INTERVAL_MS,
        fast_px_per_s: float = FAST_PX_PER_S,
        slow_ms: int = SLOW_MS,
        speed_window_ms: int = SPEED_WINDOW_MS,
    ) -> None:
        if width_px <= 0:
            raise ValueError("width_px must be positive")
        self._seek_interval_ms = seek_interval_ms
        self._fast_ratio_per_s = fast_px_per_s / width_px
        self._slow_ms = slow_ms
        self._window_ms = speed_window_ms
        self._samples: deque[tuple[float, float]] = deque()
        self._pending = 0.0
        self._last_seek: float | None = None
        self._last_seek_ms = 0.0
        self._silent = False
        self._beyond = False
        self._slow_since: float | None = None

    @property
    def silent(self) -> bool:
        return self._silent

    @property
    def beyond_end(self) -> bool:
        return self._beyond

    def press(self, ratio: float, t_ms: float) -> list[ScrubCommand]:
        self._samples.clear()
        self._samples.append((t_ms, ratio))
        self._pending = _clamp(ratio)
        self._slow_since = None
        if ratio > 1.0:
            self._beyond = True
            self._silent = True
            return [Silence(True), EnsurePlaying()]
        return [self._seek(t_ms), EnsurePlaying()]

    def move(self, ratio: float, t_ms: float) -> list[ScrubCommand]:
        self._samples.append((t_ms, ratio))
        self._pending = _clamp(ratio)
        if ratio > 1.0:
            commands: list[ScrubCommand] = []
            if not self._silent:
                self._silent = True
                commands.append(Silence(True))
            self._beyond = True
            self._slow_since = None
            return commands
        self._beyond = False
        return self._evaluate(t_ms)

    def tick(self, t_ms: float) -> list[ScrubCommand]:
        return self._evaluate(t_ms)

    def release(self, ratio: float, t_ms: float) -> list[ScrubCommand]:
        commands: list[ScrubCommand] = []
        if ratio > 1.0:
            if self._silent:
                commands.append(Silence(False))
            commands.append(Next())
        else:
            target = _clamp(ratio)
            if self._last_seek is None or abs(target - self._last_seek) > 1e-9:
                self._pending = target
                commands.append(self._seek(t_ms))
            if self._silent:
                commands.append(Silence(False))
            commands.append(EnsurePlaying())
        self._silent = False
        self._beyond = False
        self._slow_since = None
        self._samples.clear()
        return commands

    # ----------------------------------------------------------------- helpers

    def _seek(self, t_ms: float) -> Seek:
        self._last_seek = self._pending
        self._last_seek_ms = t_ms
        return Seek(self._pending)

    def _speed(self, t_ms: float) -> float:
        """Return the mouse speed in ratio per second over the last few milliseconds."""
        while self._samples and t_ms - self._samples[0][0] > self._window_ms:
            self._samples.popleft()
        if len(self._samples) < 2:
            return 0.0
        first, last = self._samples[0], self._samples[-1]
        if last[0] <= first[0]:
            return 0.0
        return abs(last[1] - first[1]) / (last[0] - first[0]) * 1000.0

    def _evaluate(self, t_ms: float) -> list[ScrubCommand]:
        if self._beyond:
            return []
        fast = self._speed(t_ms) > self._fast_ratio_per_s
        if self._silent:
            if fast:
                self._slow_since = None
                return []
            if self._slow_since is None:
                self._slow_since = t_ms
                return []
            if t_ms - self._slow_since < self._slow_ms:
                return []
            self._slow_since = None
            self._silent = False
            return [self._seek(t_ms), Silence(False)]
        if fast:
            self._silent = True
            self._slow_since = None
            return [Silence(True)]
        due = t_ms - self._last_seek_ms >= self._seek_interval_ms
        if due and (self._last_seek is None or abs(self._pending - self._last_seek) > 1e-9):
            return [self._seek(t_ms)]
        return []
