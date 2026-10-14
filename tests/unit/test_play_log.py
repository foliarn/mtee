"""Counting rule and heard-time tracker of the permanent listening log, on a fake clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from mtee.domain.play_log import (
    COUNTING_THRESHOLD_US,
    ClockReading,
    ListeningPeriod,
    PlayedTrack,
    PlayTracker,
    is_counted_play,
)

BASE_WALL = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
LONG_TRACK_US = 180_000_000
SHORT_TRACK_US = 20_000_000


def at(seconds: float) -> ClockReading:
    """A fake clock reading ``seconds`` after the start of the test."""
    return ClockReading(round(seconds * 1_000_000), BASE_WALL + timedelta(seconds=seconds))


def track(track_id: str = "track-a", duration_us: int = LONG_TRACK_US) -> PlayedTrack:
    return PlayedTrack(
        track_id=track_id,
        path=f"C:/music/{track_id}.flac",
        artist="Artist A; Artist B",
        title=f"Title {track_id}",
        album="Album",
        duration_us=duration_us,
    )


def test_a_play_counts_from_thirty_heard_seconds() -> None:
    assert COUNTING_THRESHOLD_US == 30_000_000
    assert not is_counted_play(29_999_999, LONG_TRACK_US, completed=False)
    assert is_counted_play(30_000_000, LONG_TRACK_US, completed=False)
    assert is_counted_play(30_000_000, LONG_TRACK_US, completed=True)


def test_a_short_track_counts_only_when_played_to_its_end() -> None:
    assert not is_counted_play(SHORT_TRACK_US - 1, SHORT_TRACK_US, completed=False)
    assert is_counted_play(SHORT_TRACK_US, SHORT_TRACK_US, completed=True)
    # A track of unknown duration is not treated as short.
    assert not is_counted_play(10_000_000, 0, completed=True)


def test_pauses_and_loading_add_no_heard_time() -> None:
    tracker = PlayTracker(new_event_id=lambda: "event-1")
    assert tracker.open(track(), at(0), playing=False) is None
    # Loading takes 20 s before the first audible instant.
    tracker.set_playing(True, at(20))
    tracker.set_playing(False, at(30))  # 10 s heard
    tracker.set_playing(True, at(90))  # the pause lasted 60 s
    event = tracker.close(at(95), completed=False)  # 5 s more
    assert event is not None
    assert event.event_id == "event-1"
    assert event.heard_ms == 15_000
    assert event.started_at == BASE_WALL + timedelta(seconds=20)
    assert event.ended_at == BASE_WALL + timedelta(seconds=95)
    assert event.counted is False


def test_a_seek_never_adds_the_skipped_span() -> None:
    tracker = PlayTracker()
    tracker.open(track(), at(0), playing=True)
    # Five seconds heard, then a jump from 0:05 to 2:00 at the seek instant.
    tracker.checkpoint(at(5))
    # Five more seconds heard from 2:00 on.
    event = tracker.close(at(10), completed=False)
    assert event is not None
    assert event.heard_ms == 10_000


def test_an_event_never_audible_is_dropped() -> None:
    tracker = PlayTracker()
    tracker.open(track(), at(0), playing=False)
    assert tracker.close(at(60), completed=False) is None
    assert not tracker.is_open


def test_opening_a_track_closes_the_previous_listening() -> None:
    ids = iter(["first", "second"])
    tracker = PlayTracker(new_event_id=lambda: next(ids))
    tracker.open(track("track-a"), at(0), playing=True)
    closed = tracker.open(track("track-b"), at(12), playing=True)
    assert closed is not None
    assert closed.event_id == "first"
    assert closed.heard_ms == 12_000
    assert closed.track.track_id == "track-a"
    final = tracker.close(at(20), completed=False)
    assert final is not None
    assert final.event_id == "second"
    assert final.heard_ms == 8_000


def test_a_restart_of_the_same_track_is_a_new_event() -> None:
    ids = iter(["first", "second"])
    tracker = PlayTracker(new_event_id=lambda: next(ids))
    tracker.open(track(), at(0), playing=True)
    closed = tracker.open(track(), at(45), playing=True)
    assert closed is not None and closed.event_id == "first"
    final = tracker.close(at(50), completed=True)
    assert final is not None
    assert final.event_id == "second"
    assert final.heard_ms == 5_000


def test_shutdown_flush_keeps_the_heard_time_so_far() -> None:
    tracker = PlayTracker()
    tracker.open(track(), at(0), playing=True)
    event = tracker.close(at(12), completed=False)
    assert event is not None
    assert event.heard_ms == 12_000
    assert event.counted is False
    assert tracker.close(at(13), completed=False) is None


def test_a_listening_that_reaches_the_end_of_a_short_track_counts() -> None:
    tracker = PlayTracker()
    tracker.open(track(duration_us=SHORT_TRACK_US), at(0), playing=True)
    event = tracker.close(at(20), completed=True)
    assert event is not None
    assert event.counted is True
    assert event.heard_ms == 20_000


def test_heard_time_is_rounded_down_to_milliseconds() -> None:
    tracker = PlayTracker()
    tracker.open(track(), ClockReading(0, BASE_WALL), playing=True)
    event = tracker.close(ClockReading(1_999_999, BASE_WALL), completed=False)
    assert event is not None
    assert event.heard_ms == 1_999


def test_clock_readings_and_periods_are_validated() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ClockReading(0, datetime(2026, 10, 14, 10, 0))
    with pytest.raises(TypeError):
        ClockReading(1.5, BASE_WALL)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="after its start"):
        ListeningPeriod(BASE_WALL, BASE_WALL)
    with pytest.raises(ValueError, match="timezone-aware"):
        ListeningPeriod(datetime(2026, 10, 1), None)
    assert ListeningPeriod().start is None
