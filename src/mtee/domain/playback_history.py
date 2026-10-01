"""Pure, bounded history of the tracks that were played."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["HISTORY_LIMIT", "HistoryEntry", "PlaybackHistory"]

HISTORY_LIMIT = 100


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """One listening: the track, where it was played from, and when it was left."""

    history_id: str
    track_id: str
    snapshot: Mapping[str, Any]
    source: str = ""
    source_title: str = ""
    played_at_utc: str = ""


@dataclass(frozen=True, slots=True)
class PlaybackHistory:
    """The latest listenings, most recent first; duplicates are kept."""

    entries: tuple[HistoryEntry, ...] = ()

    def record(self, entry: HistoryEntry) -> PlaybackHistory:
        return PlaybackHistory((entry, *self.entries)[:HISTORY_LIMIT])

    def find(self, history_id: str) -> HistoryEntry | None:
        return next((entry for entry in self.entries if entry.history_id == history_id), None)

    def validate(self) -> None:
        ids = [entry.history_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("History identifiers must be unique")
        if len(ids) > HISTORY_LIMIT:
            raise ValueError("History is longer than its limit")
