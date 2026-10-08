"""Commands for the genre domain; callers run database work outside the GUI thread."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from mtee.persistence.genre_repository import GenreRepository


class GenreService:
    def __init__(self, repository: GenreRepository) -> None:
        self.repository = repository

    def taxonomy_snapshot(self) -> list[dict[str, Any]]:
        return self.repository.taxonomy_snapshot()

    def track_assignments(self, track_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        return self.repository.track_assignments(track_ids)

    def set_brush_membership(
        self,
        track_ids: Sequence[str],
        genre_id: str,
        enabled: bool,
        *,
        expected_revisions: dict[str, int] | None = None,
        cancel: Callable[[], None] | None = None,
    ) -> str:
        return self.repository.change_membership(
            track_ids,
            [genre_id],
            enabled=enabled,
            expected_revisions=expected_revisions,
            cancel=cancel,
        )

    def undo(self, operation_id: str) -> str:
        return self.repository.undo(operation_id)
