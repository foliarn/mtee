"""Unit tests for workspace_columns."""

from __future__ import annotations

from mtee.models.workspace_columns import (
    find_tabs_with_hidden_sort,
    move_column,
    move_column_relative,
    reset_column_preferences,
    resize_column,
    set_show_artwork,
    toggle_column,
)
from mtee.persistence.workspace_repository import DEFAULT_COLUMN_PREFERENCES


def test_toggle_column() -> None:
    prefs = {
        "hidden": ["playCount"],
        "order": ["title", "artist", "album", "playCount"],
        "widths": {},
        "showArtwork": True,
    }

    # Showing hidden playCount -> needs_play_stats is True
    updated, changed, play_stats = toggle_column(prefs, "playCount")
    assert changed is True
    assert play_stats is True
    assert "playCount" not in updated["hidden"]

    # Hiding title -> needs_play_stats is False
    updated2, changed2, play_stats2 = toggle_column(updated, "title")
    assert changed2 is True
    assert play_stats2 is False
    assert "title" in updated2["hidden"]

    # Unknown key -> no change
    _, changed_invalid, _ = toggle_column(prefs, "unknown_col")
    assert changed_invalid is False

    # Prevent hiding all columns
    minimal_prefs = {
        "hidden": ["artist", "album", "playCount"],
        "order": ["title", "artist", "album", "playCount"],
        "widths": {},
        "showArtwork": True,
    }
    _, cant_hide_last, _ = toggle_column(
        minimal_prefs, "title", all_keys=("title", "artist", "album", "playCount")
    )
    assert cant_hide_last is False


def test_resize_column() -> None:
    prefs = {"widths": {"title": 100}, "hidden": [], "order": ["title"]}

    # Valid resize
    updated, changed = resize_column(prefs, "title", 250)
    assert changed is True
    assert updated["widths"]["title"] == 250

    # Clamping below min (44)
    updated_clamped, changed = resize_column(prefs, "title", 10)
    assert changed is True
    assert updated_clamped["widths"]["title"] == 44

    # Clamping above max (640)
    updated_max, changed = resize_column(prefs, "title", 1000)
    assert changed is True
    assert updated_max["widths"]["title"] == 640

    # Same width -> no change
    _, no_change = resize_column(prefs, "title", 100)
    assert no_change is False


def test_move_column() -> None:
    prefs = {"order": ["title", "artist", "album"], "hidden": [], "widths": {}}

    # Move right
    updated, changed = move_column(prefs, "title", 1)
    assert changed is True
    assert updated["order"] == ["artist", "title", "album"]

    # Move left
    updated_left, changed = move_column(updated, "title", -1)
    assert changed is True
    assert updated_left["order"] == ["title", "artist", "album"]

    # Move left at start -> boundary clamp / no change
    _, no_change = move_column(prefs, "title", -1)
    assert no_change is False

    # Invalid offset
    _, invalid_offset = move_column(prefs, "title", 2)
    assert invalid_offset is False


def test_move_column_relative() -> None:
    prefs = {"order": ["title", "artist", "album", "genre"], "hidden": [], "widths": {}}

    # Move genre before artist
    updated, changed = move_column_relative(prefs, "genre", "artist", after=False)
    assert changed is True
    assert updated["order"] == ["title", "genre", "artist", "album"]

    # Move title after album
    updated2, changed2 = move_column_relative(prefs, "title", "album", after=True)
    assert changed2 is True
    assert updated2["order"] == ["artist", "album", "title", "genre"]

    # Self target -> no change
    _, no_change = move_column_relative(prefs, "title", "title", after=True)
    assert no_change is False


def test_set_show_artwork_and_reset() -> None:
    prefs = {"showArtwork": True, "hidden": [], "order": []}

    updated, changed = set_show_artwork(prefs, False)
    assert changed is True
    assert updated["showArtwork"] is False

    _, no_change = set_show_artwork(prefs, True)
    assert no_change is False

    default_prefs = reset_column_preferences()
    assert default_prefs["showArtwork"] == DEFAULT_COLUMN_PREFERENCES["showArtwork"]


def test_find_tabs_with_hidden_sort() -> None:
    tab_states = {
        "tab1": {"sortMode": "manual", "sortKey": "playCount", "sortAscending": True},
        "tab2": {"sortMode": "default", "sortKey": "playCount", "sortAscending": True},
        "tab3": {"sortMode": "manual", "sortKey": "title", "sortAscending": False},
    }

    reset = find_tabs_with_hidden_sort(tab_states, {"playCount"})
    assert reset == ["tab1"]
    assert tab_states["tab1"]["sortMode"] == "default"
    assert tab_states["tab1"]["sortKey"] == "fileCreatedAt"
