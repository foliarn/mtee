"""Local playlist identity, independent of physical file format and path."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

LIKED_PLAYLIST_ID = "liked"
PLAYLIST_COLUMNS = ("title", "artist", "album", "bpm", "key", "duration")


def normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def musical_identity(track: dict[str, Any]) -> tuple[str, tuple[str, ...]] | None:
    """Use tagged title including version, and unordered credited artists.

    Filename fallbacks and absent credits cannot establish musical equality.
    Explicit mix/live/remix words remain part of the title.
    """
    title = str(track.get("title", ""))
    artist = str(track.get("artist", ""))
    if not title.strip() or not artist.strip() or track.get("identityUncertain", False):
        return None
    artists = tuple(sorted({normalized(a) for a in re.split(r",|;", artist) if a.strip()}))
    clean_title = re.sub(r"\s*[([]original (?:mix|version)[)\]]", "", title, flags=re.I)
    return normalized(clean_title), artists


def portable_snapshot(track: dict[str, Any]) -> dict[str, Any]:
    """Keep display metadata without exporting machine paths or catalogue UUIDs."""
    keys = (
        "title",
        "artist",
        "album",
        "genre",
        "bpm",
        "bpmText",
        "key",
        "keyCamelot",
        "seconds",
        "durationUs",
        "duration",
        "filename",
        "format",
        "identityUncertain",
    )
    return {key: track[key] for key in keys if key in track}


def playlist_name(value: str) -> str:
    name = value.strip()
    if not name or len(name) > 240:
        raise ValueError("Use a name between 1 and 240 characters.")
    return name
