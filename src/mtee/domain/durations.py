"""Spoken-style durations for headers."""

from __future__ import annotations

__all__ = ["format_playlist_meta"]


def format_playlist_meta(count: int, seconds: int) -> str:
    """Return ``8 tracks, 34 min 26 sec`` (``1 hr 12 min`` from one hour, no seconds then).

    The duration is left out of an empty playlist and of one whose length is unknown.
    """
    count = max(0, int(count))
    total = max(0, int(seconds))
    noun = "track" if count == 1 else "tracks"
    head = f"{count} {noun}"
    if count == 0 or total == 0:
        return head
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        duration = f"{hours} hr" + (f" {minutes} min" if minutes else "")
    elif minutes:
        duration = f"{minutes} min" + (f" {secs} sec" if secs else "")
    else:
        duration = f"{secs} sec"
    return f"{head}, {duration}"
