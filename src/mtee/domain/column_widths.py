"""Bounds of a table column width, shared by the list, the saved layout and the playlists."""

from __future__ import annotations

__all__ = ["MAX_COLUMN_WIDTH", "MAX_TITLE_WIDTH", "MIN_COLUMN_WIDTH", "clamp_column_width"]

MIN_COLUMN_WIDTH = 44
MAX_COLUMN_WIDTH = 640
# The title takes the free space of a wide window, so it needs a larger ceiling than the others.
MAX_TITLE_WIDTH = 2400


def clamp_column_width(key: str, width: int) -> int:
    """Keep a width inside the bounds of its column."""
    ceiling = MAX_TITLE_WIDTH if key == "title" else MAX_COLUMN_WIDTH
    return min(max(width, MIN_COLUMN_WIDTH), ceiling)
