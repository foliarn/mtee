"""Unit tests for workspace_track_loader."""

from __future__ import annotations

from mtee.models.workspace_track_loader import (
    TrackRequestTracker,
    compute_track_request_key,
    filter_track_rows,
    needs_play_stats,
    order_track_rows,
)


def test_compute_track_request_key() -> None:
    tab_state = {"searchQuery": "  Daft  "}
    key = compute_track_request_key(tab_state, None, "folder", "root/dir", "title", True)
    assert key == ("folder", "root/dir", "title", True, "daft")


def test_filter_track_rows() -> None:
    rows = [
        {"title": "Around the World", "artist": "Daft Punk", "album": "Homework"},
        {"title": "Bohemian Rhapsody", "artist": "Queen", "album": "A Night at the Opera"},
        {"title": "Get Lucky", "artist": "Daft Punk", "album": "RAM"},
    ]
    filtered = filter_track_rows(rows, "daft")
    assert len(filtered) == 2
    assert filtered[0]["title"] == "Around the World"
    assert filtered[1]["title"] == "Get Lucky"

    assert filter_track_rows(rows, "") == rows


def test_order_track_rows() -> None:
    rows = [
        {"id": "t1", "title": "B"},
        {"id": "t2", "title": "A"},
    ]
    # index + ascending keeps original order
    assert order_track_rows(rows, "index", True) == rows

    # title sort
    sorted_rows = order_track_rows(rows, "title", True)
    assert sorted_rows[0]["title"] == "A"
    assert sorted_rows[1]["title"] == "B"


def test_needs_play_stats() -> None:
    # No play log -> False
    assert needs_play_stats("title", ["playCount", "lastPlayed"], False) is False

    # Has play log, sorted by playCount -> True
    assert needs_play_stats("playCount", ["playCount", "lastPlayed"], True) is True

    # Has play log, playCount visible (not in hidden) -> True
    assert needs_play_stats("title", ["lastPlayed"], True) is True

    # Has play log, all play columns hidden, sort not by play stats -> False
    assert needs_play_stats("title", ["playCount", "lastPlayed"], True) is False


def test_track_request_tracker() -> None:
    tracker = TrackRequestTracker()
    key = ("folder", "dir", "title", True, "")

    assert tracker.is_current_request("m1", key) is False
    gen1, prev = tracker.next_generation("m1", key)
    assert gen1 == 1
    assert prev == ""
    assert tracker.is_current_request("m1", key) is True
    assert tracker.is_generation_valid("m1", 1) is True
    assert tracker.is_generation_valid("m1", 2) is False

    tracker.record_job("m1", "job-123")
    assert tracker.has_completed_request("m1", key) is False

    tracker.on_rows_ready("m1")
    assert tracker.has_completed_request("m1", key) is True

    # Cancel and release
    tracker.record_job("m1", "job-456")
    job_to_cancel = tracker.cancel_and_release("m1")
    assert job_to_cancel == "job-456"
    assert tracker.is_generation_valid("m1", 1) is False  # bumped to 2
    assert tracker.is_current_request("m1", key) is False
