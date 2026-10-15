"""Track request tracking, filtering, ordering and play stats query coordination."""

from __future__ import annotations

from typing import Any

from mtee.models.workspace_rows import sort_rows

__all__ = [
    "PLAY_COLUMN_KEYS",
    "TrackRequestTracker",
    "compute_track_request_key",
    "filter_track_rows",
    "needs_play_stats",
    "order_track_rows",
]

PLAY_COLUMN_KEYS: tuple[str, str] = ("playCount", "lastPlayed")


def compute_track_request_key(
    tab_state: dict[str, Any],
    group_tab_state: dict[str, Any] | None,
    kind: str,
    ref: str,
    sort_key: str,
    ascending: bool,
) -> tuple[str, str, str, bool, str]:
    """Compute deduplicating key for a track row request."""
    tab = dict(tab_state)
    if group_tab_state:
        tab.update(group_tab_state)
    query = str(tab.get("searchQuery", "")).casefold().strip()
    return (kind, ref, sort_key, bool(ascending), query)


def filter_track_rows(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Filter track rows matching search query across standard metadata fields."""
    if not query:
        return rows
    folded = query.casefold().strip()
    return [
        row
        for row in rows
        if folded
        in " ".join(
            str(row.get(field, "")) for field in ("title", "artist", "album", "genre", "filename")
        ).casefold()
    ]


def order_track_rows(
    rows: list[dict[str, Any]],
    sort_key: str,
    ascending: bool,
) -> list[dict[str, Any]]:
    """Sort track rows unless sort_key is 'index' with ascending order."""
    if sort_key == "index" and ascending:
        return rows
    return sort_rows(rows, sort_key, ascending)


def needs_play_stats(
    sort_key: str,
    hidden_columns: set[str] | list[str] | tuple[str, ...],
    has_play_log: bool,
) -> bool:
    """Determine if play stats must be queried from the database."""
    if not has_play_log:
        return False
    if sort_key in PLAY_COLUMN_KEYS:
        return True
    hidden_set = set(hidden_columns)
    return any(key not in hidden_set for key in PLAY_COLUMN_KEYS)


class TrackRequestTracker:
    """Tracks generation numbers, active job IDs and query keys for track row models."""

    def __init__(self) -> None:
        self.generations: dict[str, int] = {}
        self.job_ids: dict[str, str] = {}
        self.keys: dict[str, tuple[str, str, str, bool, str]] = {}

    def is_current_request(self, model_key: str, key: tuple[str, str, str, bool, str]) -> bool:
        """Return True if model already holds or is fetching the exact same query."""
        return self.keys.get(model_key) == key

    def has_completed_request(
        self,
        model_key: str,
        key: tuple[str, str, str, bool, str],
    ) -> bool:
        """Return True if model finished fetching the given query and has no pending job."""
        return self.keys.get(model_key) == key and model_key not in self.job_ids

    def next_generation(
        self,
        model_key: str,
        key: tuple[str, str, str, bool, str],
    ) -> tuple[int, str]:
        """Bump generation and set current request key.

        Returns:
            (new_generation, previous_job_id_to_cancel)
        """
        gen = self.generations.get(model_key, 0) + 1
        self.generations[model_key] = gen
        prev_job = self.job_ids.get(model_key, "")
        self.keys[model_key] = key
        return gen, prev_job

    def record_job(self, model_key: str, job_id: str) -> None:
        """Associate active job ID with the model key."""
        self.job_ids[model_key] = job_id

    def is_generation_valid(self, model_key: str, generation: int) -> bool:
        """Check if incoming rows match the latest requested generation."""
        return generation == self.generations.get(model_key)

    def on_rows_ready(self, model_key: str) -> None:
        """Mark active job finished for model_key."""
        self.job_ids.pop(model_key, None)

    def cancel_and_release(self, model_key: str) -> str:
        """Bump generation to invalidate running jobs and release tracker entries.

        Returns:
            job_id_to_cancel
        """
        self.generations[model_key] = self.generations.get(model_key, 0) + 1
        self.keys.pop(model_key, None)
        return self.job_ids.pop(model_key, "")

    def invalidate_key(self, model_key: str) -> None:
        """Invalidate request key so that next request force-reloads."""
        self.keys.pop(model_key, None)
