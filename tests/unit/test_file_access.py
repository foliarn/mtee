"""Serialisation of the accesses to the file of a track."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from mtee.domain.tracks import TrackId
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError


def test_two_writes_never_overlap(tmp_path: Path) -> None:
    coordinator = FileAccessCoordinator()
    track = TrackId.new()
    target = tmp_path / "track.flac"
    target.write_text("", encoding="utf-8")
    overlaps: list[str] = []
    inside = threading.Semaphore(0)

    def write(marker: str) -> None:
        with coordinator.acquire(track, f"write-{marker}"):
            current = target.read_text(encoding="utf-8")
            if current.endswith("<"):
                overlaps.append(marker)
            target.write_text(current + "<", encoding="utf-8")
            inside.release()
            time.sleep(0.05)
            target.write_text(target.read_text(encoding="utf-8") + ">", encoding="utf-8")

    first = threading.Thread(target=write, args=("a",))
    second = threading.Thread(target=write, args=("b",))
    first.start()
    assert inside.acquire(timeout=5)
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)

    assert overlaps == []
    assert target.read_text(encoding="utf-8") == "<><>"


def test_a_failing_operation_releases_the_access() -> None:
    coordinator = FileAccessCoordinator()
    track = TrackId.new()

    with pytest.raises(RuntimeError), coordinator.acquire(track, "write"):
        raise RuntimeError("disk full")

    assert not coordinator.is_busy(track)
    with coordinator.acquire(track, "read"):
        assert coordinator.holder_of(track) == "read"


def test_an_access_held_too_long_times_out_and_names_its_holder() -> None:
    coordinator = FileAccessCoordinator(default_timeout_seconds=0.05)
    track = TrackId.new()
    held = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with coordinator.acquire(track, "playback"):
            held.set()
            release.wait(5)

    worker = threading.Thread(target=hold)
    worker.start()
    assert held.wait(5)

    try:
        with pytest.raises(FileAccessTimeoutError) as failure, coordinator.acquire(track, "move"):
            pass
    finally:
        release.set()
        worker.join(timeout=5)

    assert failure.value.purpose == "move"
    assert failure.value.holder == "playback"


def test_different_tracks_are_not_blocked_by_each_other() -> None:
    coordinator = FileAccessCoordinator(default_timeout_seconds=0.5)
    first = TrackId.new()
    second = TrackId.new()

    with coordinator.acquire(first, "write"), coordinator.acquire(second, "write"):
        assert coordinator.is_busy(first)
        assert coordinator.is_busy(second)


def test_no_entry_is_leaked_after_the_accesses() -> None:
    coordinator = FileAccessCoordinator()
    track = TrackId.new()

    for _ in range(3):
        with coordinator.acquire(track, "read"):
            pass

    assert coordinator.tracked_count() == 0
