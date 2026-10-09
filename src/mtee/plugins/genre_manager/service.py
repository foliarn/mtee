"""Small command boundary for Genre Manager decisions."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from mtee.plugins.genre_manager.domain import add_genre, make_primary, remove_genre
from mtee.plugins.genre_manager.repository import GenreManagerRepository


class GenreManagerService:
    """Translate user intentions to explicit, revision-checked assignments."""

    def __init__(self, repository: GenreManagerRepository) -> None:
        self._repository = repository

    def ensure_catalogue(self) -> None:
        """Seed once on plugin opening, never during ordinary library loading."""
        self._repository.ensure_catalogue()

    def assign_genre(
        self,
        track_id: str,
        genre_id: str,
        *,
        expected_revision: int,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        parents = {row["genre_id"]: row["parent_id"] for row in self._repository.genres()}
        current = self._repository.track(track_id)
        ordered = add_genre(current["genres"], genre_id, parents)
        return self._repository.set_genres(
            track_id,
            ordered,
            expected_revision=expected_revision,
            operation_id=operation_id or str(uuid.uuid4()),
        )

    def remove_genre(
        self,
        track_id: str,
        genre_id: str,
        *,
        expected_revision: int,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        current = self._repository.track(track_id)
        ordered = remove_genre(current["genres"], genre_id)
        return self._repository.set_genres(
            track_id,
            ordered,
            expected_revision=expected_revision,
            operation_id=operation_id or str(uuid.uuid4()),
        )

    def make_primary(
        self,
        track_id: str,
        genre_id: str,
        *,
        expected_revision: int,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        current = self._repository.track(track_id)
        ordered = make_primary(current["genres"], genre_id)
        return self._repository.set_genres(
            track_id,
            ordered,
            expected_revision=expected_revision,
            operation_id=operation_id or str(uuid.uuid4()),
        )

    def assign_folder_genre(self, track_ids: Iterable[str], genre_id: str) -> list[dict[str, Any]]:
        """Apply only after the user confirms the previewed list and genre."""
        results = []
        for track_id in dict.fromkeys(track_ids):
            current = self._repository.track(track_id)
            results.append(
                self.assign_genre(track_id, genre_id, expected_revision=current["genre_revision"])
            )
        return results
