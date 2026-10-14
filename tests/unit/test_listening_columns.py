"""Plays and Last played: row figures, their sort, the details rows and the saved layouts."""

from __future__ import annotations

from datetime import UTC, datetime

from mtee.domain.play_log import format_listened_at
from mtee.models.workspace_model import _listening_details, _sort_rows, _with_play_stats
from mtee.persistence.play_log_repository import TrackPlayStats
from mtee.persistence.workspace_repository import (
    DEFAULT_COLUMN_PREFERENCES,
    _validated_column_preferences,
)

EARLY = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
LATE = datetime(2026, 10, 14, 18, 30, tzinfo=UTC)
NEW_KEYS = ("playCount", "lastPlayed")


def _stats(track_id: str, plays: int, last: datetime) -> TrackPlayStats:
    return TrackPlayStats(track_id=track_id, counted_plays=plays, sessions=plays, last_played=last)


def test_the_listened_at_text_is_the_local_date_and_time() -> None:
    assert format_listened_at(LATE) == LATE.astimezone().strftime("%d %b %Y, %H:%M")
    assert format_listened_at(None) == "—"


def test_rows_carry_their_counts_and_a_dash_when_never_played() -> None:
    rows = _with_play_stats(
        [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}],
        {"a": _stats("a", 3, LATE)},
    )

    assert rows[0]["playCount"] == 3
    assert rows[0]["lastPlayedText"] == format_listened_at(LATE)
    assert rows[0]["lastPlayedNs"] == int(LATE.timestamp() * 1_000_000_000)
    assert rows[1]["playCount"] == 0
    assert rows[1]["lastPlayedNs"] is None
    assert rows[1]["lastPlayedText"] == "—"


def test_the_source_rows_are_not_modified() -> None:
    source = [{"id": "a"}]

    _with_play_stats(source, {"a": _stats("a", 1, LATE)})

    assert source == [{"id": "a"}]


def test_plays_sort_by_count_and_last_played_by_time() -> None:
    rows = _with_play_stats(
        [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}, {"id": "c", "title": "C"}],
        {"a": _stats("a", 1, EARLY), "b": _stats("b", 5, LATE)},
    )

    by_plays = [row["id"] for row in _sort_rows(rows, "playCount", False)]
    assert by_plays == ["b", "a", "c"]

    by_last = [row["id"] for row in _sort_rows(rows, "lastPlayed", False)]
    assert by_last == ["b", "a", "c"]  # the track never played goes last, as other blanks do


def test_the_details_rows_show_plays_and_last_played() -> None:
    assert _listening_details(_stats("a", 2, LATE)) == [
        {"label": "Plays", "value": "2"},
        {"label": "Last played", "value": format_listened_at(LATE)},
    ]
    assert _listening_details(None) == [
        {"label": "Plays", "value": "0"},
        {"label": "Last played", "value": "—"},
    ]


def test_the_new_columns_are_hidden_by_default() -> None:
    preferences = _validated_column_preferences(None)

    assert set(NEW_KEYS) <= set(preferences["hidden"])
    assert set(NEW_KEYS) <= set(preferences["order"])


def test_a_layout_saved_before_the_columns_existed_keeps_them_hidden() -> None:
    saved_order = [key for key in DEFAULT_COLUMN_PREFERENCES["order"] if key not in NEW_KEYS]
    saved_hidden = [key for key in DEFAULT_COLUMN_PREFERENCES["hidden"] if key not in NEW_KEYS]

    preferences = _validated_column_preferences({"order": saved_order, "hidden": saved_hidden})

    assert set(NEW_KEYS) <= set(preferences["hidden"])
    assert "title" not in preferences["hidden"]


def test_a_layout_that_shows_a_listening_column_keeps_it_visible() -> None:
    saved_order = list(DEFAULT_COLUMN_PREFERENCES["order"])
    saved_hidden = [key for key in DEFAULT_COLUMN_PREFERENCES["hidden"] if key not in NEW_KEYS]

    preferences = _validated_column_preferences({"order": saved_order, "hidden": saved_hidden})

    assert "playCount" not in preferences["hidden"]
    assert "lastPlayed" not in preferences["hidden"]
