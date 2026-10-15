"""Pure calculations and operations for table column preferences and hidden sorts."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from mtee.models.workspace_rows import copy_column_preferences
from mtee.models.workspace_session import COLUMN_KEYS, set_default_sort
from mtee.models.workspace_track_loader import PLAY_COLUMN_KEYS
from mtee.persistence.workspace_repository import DEFAULT_COLUMN_PREFERENCES

__all__ = [
    "find_tabs_with_hidden_sort",
    "move_column",
    "move_column_relative",
    "reset_column_preferences",
    "resize_column",
    "set_show_artwork",
    "toggle_column",
]


def toggle_column(
    prefs: dict[str, Any],
    key: str,
    all_keys: Collection[str] = COLUMN_KEYS,
) -> tuple[dict[str, Any], bool, bool]:
    """Toggle visibility of a column in preferences.

    Returns:
        (updated_prefs, changed, needs_play_stats_refresh)
    """
    if key not in all_keys:
        return prefs, False, False

    updated = copy_column_preferences(prefs)
    hidden = list(updated.get("hidden", []))

    if key in hidden:
        hidden.remove(key)
        updated["hidden"] = hidden
        needs_play_stats = key in PLAY_COLUMN_KEYS
        return updated, True, needs_play_stats

    # Prevent hiding all columns (at least 1 column must remain visible)
    if len(all_keys) - len(hidden) <= 1:
        return prefs, False, False

    hidden.append(key)
    updated["hidden"] = hidden
    return updated, True, False


def resize_column(
    prefs: dict[str, Any],
    key: str,
    width: int,
    all_keys: Collection[str] = COLUMN_KEYS,
    min_width: int = 44,
    max_width: int = 640,
) -> tuple[dict[str, Any], bool]:
    """Resize a column within bounded minimum and maximum width.

    Returns:
        (updated_prefs, changed)
    """
    if key not in all_keys:
        return prefs, False

    clamped_width = min(max(int(width), min_width), max_width)
    widths = dict(prefs.get("widths", {}))
    if widths.get(key) == clamped_width:
        return prefs, False

    updated = copy_column_preferences(prefs)
    widths[key] = clamped_width
    updated["widths"] = widths
    return updated, True


def move_column(
    prefs: dict[str, Any],
    key: str,
    offset: int,
    all_keys: Collection[str] = COLUMN_KEYS,
) -> tuple[dict[str, Any], bool]:
    """Move a column by offset (-1 or +1) in the column order.

    Returns:
        (updated_prefs, changed)
    """
    if key not in all_keys or offset not in {-1, 1}:
        return prefs, False

    order = list(prefs.get("order", []))
    if key not in order:
        return prefs, False

    old_index = order.index(key)
    new_index = min(max(old_index + offset, 0), len(order) - 1)
    if new_index == old_index:
        return prefs, False

    updated = copy_column_preferences(prefs)
    order.insert(new_index, order.pop(old_index))
    updated["order"] = order
    return updated, True


def move_column_relative(
    prefs: dict[str, Any],
    key: str,
    target_key: str,
    after: bool,
    all_keys: Collection[str] = COLUMN_KEYS,
) -> tuple[dict[str, Any], bool]:
    """Move a column adjacent to target_key (before or after).

    Returns:
        (updated_prefs, changed)
    """
    if key not in all_keys or target_key not in all_keys or key == target_key:
        return prefs, False

    order = list(prefs.get("order", []))
    if key not in order or target_key not in order:
        return prefs, False

    order.remove(key)
    target_index = order.index(target_key) + (1 if after else 0)
    order.insert(target_index, key)

    if order == prefs.get("order"):
        return prefs, False

    updated = copy_column_preferences(prefs)
    updated["order"] = order
    return updated, True


def set_show_artwork(prefs: dict[str, Any], visible: bool) -> tuple[dict[str, Any], bool]:
    """Set the showArtwork preference.

    Returns:
        (updated_prefs, changed)
    """
    visible = bool(visible)
    if prefs.get("showArtwork") == visible:
        return prefs, False

    updated = copy_column_preferences(prefs)
    updated["showArtwork"] = visible
    return updated, True


def reset_column_preferences() -> dict[str, Any]:
    """Return a fresh copy of default column preferences."""
    return copy_column_preferences(DEFAULT_COLUMN_PREFERENCES)


def find_tabs_with_hidden_sort(
    tab_states: dict[str, dict[str, Any]],
    hidden: set[str],
) -> list[str]:
    """Reset sort to default for any tab currently sorted by a hidden column.

    Mutates affected tab states in-place and returns list of reset tab IDs.
    """
    reset_tabs: list[str] = []
    for tab_id, state in tab_states.items():
        if state.get("sortMode") == "manual" and state.get("sortKey") in hidden:
            set_default_sort(state)
            reset_tabs.append(tab_id)
    return reset_tabs
