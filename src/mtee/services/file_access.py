"""Coordination of the concurrent accesses to one track.

Editing, moving, decoding and native playback must not touch the same file at
the same time. ``FileAccessCoordinator`` serialises them by ``track_id``, with a
bounded acquisition and a guaranteed release, so a failing operation never
leaves an access locked.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from mtee.domain.tracks import TrackId

__all__ = ["FileAccessCoordinator", "FileAccessTimeoutError", "FileLease"]

DEFAULT_TIMEOUT_SECONDS = 10.0


class FileAccessTimeoutError(TimeoutError):
    """Raised when an access could not be acquired before its deadline."""

    def __init__(self, track_id: TrackId, purpose: str, holder: str | None) -> None:
        held_by = f" held by {holder}" if holder else ""
        super().__init__(f"Access to track {track_id} for {purpose} timed out{held_by}.")
        self.track_id = track_id
        self.purpose = purpose
        self.holder = holder


@dataclass(frozen=True, slots=True)
class FileLease:
    """Proof that the caller currently owns the access to a track."""

    track_id: TrackId
    purpose: str


class _TrackLock:
    """Lock of one track and the purpose currently holding it."""

    __slots__ = ("holder", "lock", "waiters")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.holder: str | None = None
        self.waiters = 0


class FileAccessCoordinator:
    """Serialises the accesses to the file of a track."""

    def __init__(self, *, default_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._default_timeout_seconds = default_timeout_seconds
        self._registry_lock = threading.Lock()
        self._locks: dict[TrackId, _TrackLock] = {}

    @contextmanager
    def acquire(
        self,
        track_id: TrackId,
        purpose: str,
        *,
        timeout_seconds: float | None = None,
    ) -> Iterator[FileLease]:
        """Own the access to ``track_id`` for the duration of the block.

        Raises ``FileAccessTimeoutError`` when the access stays taken longer than the
        timeout. The release happens even when the block raises.
        """
        timeout = self._default_timeout_seconds if timeout_seconds is None else timeout_seconds
        entry = self._entry_for(track_id)
        holder_at_request = entry.holder
        if not entry.lock.acquire(timeout=max(0.0, timeout)):
            self._release_entry(track_id)
            raise FileAccessTimeoutError(track_id, purpose, holder_at_request)
        entry.holder = purpose
        try:
            yield FileLease(track_id=track_id, purpose=purpose)
        finally:
            entry.holder = None
            entry.lock.release()
            self._release_entry(track_id)

    def is_busy(self, track_id: TrackId) -> bool:
        """Return whether an access to ``track_id`` is currently held."""
        with self._registry_lock:
            entry = self._locks.get(track_id)
            return entry is not None and entry.lock.locked()

    def holder_of(self, track_id: TrackId) -> str | None:
        """Return the purpose currently holding ``track_id``, when there is one."""
        with self._registry_lock:
            entry = self._locks.get(track_id)
            return entry.holder if entry is not None else None

    def tracked_count(self) -> int:
        """Return how many tracks still own an entry, to detect a leak in tests."""
        with self._registry_lock:
            return len(self._locks)

    def _entry_for(self, track_id: TrackId) -> _TrackLock:
        with self._registry_lock:
            entry = self._locks.get(track_id)
            if entry is None:
                entry = _TrackLock()
                self._locks[track_id] = entry
            entry.waiters += 1
            return entry

    def _release_entry(self, track_id: TrackId) -> None:
        with self._registry_lock:
            entry = self._locks.get(track_id)
            if entry is None:
                return
            entry.waiters -= 1
            if entry.waiters <= 0 and not entry.lock.locked():
                del self._locks[track_id]
