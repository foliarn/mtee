"""Coordinate shared reads and exclusive changes to one track at a time."""

from __future__ import annotations

import threading
from collections import Counter
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
    """Proof that the caller currently owns shared read or exclusive access."""

    track_id: TrackId
    purpose: str
    shared: bool = False


class _TrackLock:
    """A writer-preferring read/write lock for a single track."""

    __slots__ = ("condition", "holder", "reader_purposes", "readers", "users", "waiting_writers")

    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.holder: str | None = None
        self.readers = 0
        self.reader_purposes: Counter[str] = Counter()
        self.waiting_writers = 0
        # Counts both holders and waiters, so registry cleanup cannot race a waiter.
        self.users = 0


class FileAccessCoordinator:
    """Allows concurrent playback reads but serialises every exclusive operation."""

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
        """Acquire exclusive access, waiting at most ``timeout_seconds``.

        This remains the mutation API used by editing and move jobs. Passing a zero
        timeout makes it a non-blocking Busy check for callers such as the player.
        """
        timeout = self._timeout(timeout_seconds)
        entry = self._entry_for(track_id)
        acquired = False
        try:
            with entry.condition:
                entry.waiting_writers += 1
                try:
                    acquired = entry.condition.wait_for(
                        lambda: entry.holder is None and entry.readers == 0,
                        timeout=timeout,
                    )
                    if not acquired:
                        holder = self._holder(entry)
                        raise FileAccessTimeoutError(track_id, purpose, holder)
                    entry.holder = purpose
                finally:
                    entry.waiting_writers -= 1
                    entry.condition.notify_all()
            yield FileLease(track_id=track_id, purpose=purpose)
        finally:
            if acquired:
                with entry.condition:
                    entry.holder = None
                    entry.condition.notify_all()
            self._release_entry(track_id, entry)

    @contextmanager
    def acquire_read(
        self,
        track_id: TrackId,
        purpose: str,
        *,
        timeout_seconds: float | None = None,
    ) -> Iterator[FileLease]:
        """Acquire shared read access, yielding to queued writers to prevent starvation."""
        timeout = self._timeout(timeout_seconds)
        entry = self._entry_for(track_id)
        acquired = False
        try:
            with entry.condition:
                acquired = entry.condition.wait_for(
                    lambda: entry.holder is None and entry.waiting_writers == 0,
                    timeout=timeout,
                )
                if not acquired:
                    holder = self._holder(entry)
                    raise FileAccessTimeoutError(track_id, purpose, holder)
                entry.readers += 1
                entry.reader_purposes[purpose] += 1
            yield FileLease(track_id=track_id, purpose=purpose, shared=True)
        finally:
            if acquired:
                with entry.condition:
                    entry.readers -= 1
                    entry.reader_purposes[purpose] -= 1
                    if entry.reader_purposes[purpose] <= 0:
                        del entry.reader_purposes[purpose]
                    entry.condition.notify_all()
            self._release_entry(track_id, entry)

    def is_busy(self, track_id: TrackId) -> bool:
        """Return whether any reader or writer currently owns the track."""
        with self._registry_lock:
            entry = self._locks.get(track_id)
        if entry is None:
            return False
        with entry.condition:
            return entry.holder is not None or entry.readers > 0

    def holder_of(self, track_id: TrackId) -> str | None:
        """Return the exclusive holder or a concise list of shared readers."""
        with self._registry_lock:
            entry = self._locks.get(track_id)
        if entry is None:
            return None
        with entry.condition:
            if entry.holder is not None:
                return entry.holder
            if entry.reader_purposes:
                return ", ".join(sorted(entry.reader_purposes))
            return None

    def tracked_count(self) -> int:
        """Return how many tracks still own an entry, to detect a leak in tests."""
        with self._registry_lock:
            return len(self._locks)

    def _timeout(self, timeout_seconds: float | None) -> float:
        timeout = self._default_timeout_seconds if timeout_seconds is None else timeout_seconds
        return max(0.0, timeout)

    def _entry_for(self, track_id: TrackId) -> _TrackLock:
        with self._registry_lock:
            entry = self._locks.get(track_id)
            if entry is None:
                entry = _TrackLock()
                self._locks[track_id] = entry
            entry.users += 1
            return entry

    @staticmethod
    def _holder(entry: _TrackLock) -> str | None:
        if entry.holder is not None:
            return entry.holder
        if entry.reader_purposes:
            return ", ".join(sorted(entry.reader_purposes))
        return None

    def _release_entry(self, track_id: TrackId, entry: _TrackLock) -> None:
        with self._registry_lock:
            entry.users -= 1
            if entry.users <= 0 and self._locks.get(track_id) is entry:
                del self._locks[track_id]
