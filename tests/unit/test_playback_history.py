"""The bounded listening history is a pure value."""

from __future__ import annotations

import pytest

from mtee.domain.playback_history import HISTORY_LIMIT, HistoryEntry, PlaybackHistory


def _entry(index: int, track_id: str = "") -> HistoryEntry:
    return HistoryEntry(f"h{index}", track_id or f"t{index}", {"title": f"T{index}"})


def test_most_recent_first_and_truncated_at_the_limit() -> None:
    history = PlaybackHistory()
    for index in range(HISTORY_LIMIT + 5):
        history = history.record(_entry(index))

    assert len(history.entries) == HISTORY_LIMIT
    assert history.entries[0].history_id == f"h{HISTORY_LIMIT + 4}"
    assert history.entries[-1].history_id == "h5"
    history.validate()


def test_the_same_track_can_appear_twice() -> None:
    history = PlaybackHistory().record(_entry(1, "same")).record(_entry(2, "same"))

    assert [entry.track_id for entry in history.entries] == ["same", "same"]
    assert history.find("h1") is history.entries[1]
    assert history.find("missing") is None


def test_validate_rejects_duplicate_identifiers_and_overflow() -> None:
    with pytest.raises(ValueError, match="unique"):
        PlaybackHistory((_entry(1), _entry(1))).validate()
    with pytest.raises(ValueError, match="limit"):
        PlaybackHistory(tuple(_entry(i) for i in range(HISTORY_LIMIT + 1))).validate()
