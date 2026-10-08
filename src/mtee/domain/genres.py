"""Local genre trees, independent from file metadata and artist profiles."""

from __future__ import annotations

import json
import math
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RESOURCES = Path(__file__).resolve().parents[1] / "resources" / "genres"


class GenreError(ValueError):
    """An invalid taxonomy or a conflicting genre operation."""


def name_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@dataclass(frozen=True, slots=True)
class Genre:
    genre_id: str
    parent_id: str | None
    name: str
    position: int = 0
    archived: bool = False
    revision: int = 0


class Taxonomy:
    def __init__(self, genres: Iterable[Genre]) -> None:
        items = list(genres)
        self.nodes = {genre.genre_id: genre for genre in items}
        if len(items) != len(self.nodes):
            raise GenreError("Duplicate genre UUID")
        keys: set[tuple[str | None, str]] = set()
        for node in items:
            key = (node.parent_id, name_key(node.name))
            if not key[1] or key in keys:
                raise GenreError("Empty or duplicate genre name at the same level")
            keys.add(key)
            self.ancestors(node.genre_id)

    def ancestors(self, genre_id: str) -> tuple[str, ...]:
        seen: list[str] = []
        current: str | None = genre_id
        while current is not None:
            if current in seen:
                raise GenreError("Genre tree contains a cycle")
            if current not in self.nodes:
                raise GenreError(f"Unknown genre: {current}")
            seen.append(current)
            current = self.nodes[current].parent_id
        return tuple(seen[1:])

    def path(self, genre_id: str) -> str:
        ids = (genre_id, *self.ancestors(genre_id))
        return " \u203a ".join(self.nodes[identity].name for identity in reversed(ids))

    def normalize(self, genre_ids: Iterable[str]) -> set[str]:
        values = set(genre_ids)
        redundant = {ancestor for value in values for ancestor in self.ancestors(value)}
        return values - redundant

    def remove(self, assigned: Iterable[str], removed: Iterable[str]) -> set[str]:
        """Ordinary removal falls back to the root of an otherwise emptied family."""
        before = self.normalize(assigned)
        removed_ids = set(removed)
        removed_values = {
            value
            for value in before
            if value in removed_ids or set(self.ancestors(value)) & removed_ids
        }
        remaining = before - removed_values
        for identity in removed_values:
            ancestors = self.ancestors(identity)
            if not ancestors:  # Removing an explicit root can leave a track unassigned.
                continue
            family = ancestors[-1]
            if family in removed_ids:
                continue
            if not any(value == family or family in self.ancestors(value) for value in remaining):
                remaining.add(family)
        return self.normalize(remaining)

    def families(self, assigned: Iterable[str]) -> set[str]:
        return {self.ancestors(value)[-1] if self.ancestors(value) else value for value in assigned}


def jungle_or_breaks(bpm: float | None) -> str | None:
    if bpm is None or not math.isfinite(bpm) or bpm <= 0:
        return None
    effective = bpm * 2 if bpm < 90 else bpm
    return "Drum & Bass \u203a Jungle" if effective >= 160 else "Breaks"


def initial_config() -> dict[str, Any]:
    return json.loads((RESOURCES / "initial_taxonomy.json").read_text(encoding="utf-8"))


def initial_taxonomy() -> Taxonomy:
    return Taxonomy(Genre(**node) for node in initial_config()["genres"])
