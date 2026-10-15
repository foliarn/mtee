"""Explorer navigation, tree track selection/activation coordination, and reveal logic."""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from typing import Any

from mtee.models.workspace_rows import folder_from_track, parse_folder_id

__all__ = [
    "ExplorerTrackCoordinator",
    "find_revealed_track_row",
    "resolve_folder_source_exists",
    "update_captured_rows",
    "validate_explorer_track",
]


def resolve_folder_source_exists(
    source: str,
    roots_by_id: dict[str, Any],
    library_folders_fn: Callable[[str], Collection[str]],
) -> bool:
    """Check if a folder source string corresponds to an existing root or subfolder."""
    try:
        parsed = parse_folder_id(source)
    except ValueError:
        return False
    if parsed is None:
        return False
    root_id, relative = parsed
    if root_id not in roots_by_id:
        return False
    return not relative or relative in set(library_folders_fn(root_id))


def find_revealed_track_row(
    rows: Iterable[dict[str, Any]],
    track_id: str,
) -> dict[str, Any] | None:
    """Find the first row matching the given track identity."""
    identity = str(track_id)
    if not identity:
        return None
    for row in rows:
        if str(row.get("trackId", row.get("id", ""))) == identity:
            return row
    return None


def validate_explorer_track(
    track: dict[str, Any] | None,
    expected_root_id: str,
    expected_relative: str,
) -> tuple[bool, str | None]:
    """Validate that a track dictionary belongs to the expected library folder.

    Returns:
        (is_valid, error_message_if_invalid)
    """
    if not isinstance(track, dict) or not track:
        return False, "This file is no longer in the library."
    if str(track.get("rootId", "")) != str(expected_root_id) or folder_from_track(track) != str(
        expected_relative
    ):
        return False, "This file is no longer in this folder."
    return True, None


def update_captured_rows(
    queue_rows: list[Any],
    track_id: str,
    track: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Replace the matching track row in captured queue rows with updated track info.

    Returns:
        New list with replaced row if found, or None if track_id is not in queue_rows.
    """
    captured_rows = [dict(row) for row in queue_rows if isinstance(row, dict)]
    for index, row in enumerate(captured_rows):
        if str(row.get("id", "")) == track_id:
            captured_rows[index] = track
            return captured_rows
    return None


class ExplorerTrackCoordinator:
    """Coordinates tree track selection, activation stages, and pending reveals."""

    def __init__(self) -> None:
        self._activation_generation: int = 0
        self._pending: dict[str, Any] | None = None
        self._job_id: str = ""
        self._pending_reveal: tuple[str, str] | None = None

    @property
    def activation_generation(self) -> int:
        return self._activation_generation

    @property
    def pending(self) -> dict[str, Any] | None:
        return self._pending

    @property
    def job_id(self) -> str:
        return self._job_id

    @property
    def pending_reveal(self) -> tuple[str, str] | None:
        return self._pending_reveal

    def should_ignore_request(
        self,
        track_id: str,
        source: str,
        active_group: int,
        play: bool,
    ) -> bool:
        """Return True if an identical selection request is already active."""
        pending = self._pending
        return (
            not play
            and pending is not None
            and pending.get("mode") == "activate"
            and pending.get("group") == active_group
            and pending.get("track_id") == track_id
            and pending.get("source") == source
        )

    def start_request(
        self,
        track_id: str,
        source: str,
        root_id: str,
        relative: str,
        tab_id: str,
        group_index: int,
        play: bool,
        rows_generation: int,
    ) -> tuple[dict[str, Any], str | None]:
        """Cancel any previous action and create a new pending explorer track dict.

        Returns:
            (pending_dict, previous_job_id_to_cancel)
        """
        previous_job = self.cancel_action()
        pending = {
            "generation": self._activation_generation,
            "group": group_index,
            "tab_id": tab_id,
            "track_id": str(track_id),
            "source": source,
            "root_id": root_id,
            "relative": relative,
            "mode": "activate" if play else "select",
            "stage": "rows",
            "rows_generation": rows_generation,
        }
        return pending, previous_job

    def set_pending(self, pending: dict[str, Any] | None) -> None:
        self._pending = pending

    def clear_pending(self) -> None:
        self._pending = None

    def record_job(self, job_id: str) -> None:
        self._job_id = str(job_id)

    def finish_job(self) -> None:
        self._job_id = ""

    def cancel_action(self) -> str | None:
        """Cancel current explorer action, returning any running job_id to cancel."""
        self._activation_generation += 1
        self._pending = None
        job_id = self._job_id
        self._job_id = ""
        return job_id or None

    def cancel_action_for_tab(self, tab_id: str) -> str | None:
        """Cancel action only if it matches the specified tab."""
        if self._pending is not None and self._pending.get("tab_id") == tab_id:
            return self.cancel_action()
        return None

    def is_context_current(
        self,
        pending: dict[str, Any],
        active_group: int,
        groups: list[dict[str, Any]],
    ) -> bool:
        """Check if the pending action matches the currently active group and tab."""
        group_index = int(pending.get("group", -1))
        return (
            0 <= group_index < len(groups)
            and active_group == group_index
            and groups[group_index].get("active") == pending.get("tab_id")
        )

    def is_matching_ready(self, generation: int) -> bool:
        """Check if ready response matches current pending generation and stage."""
        pending = self._pending
        return (
            pending is not None
            and pending.get("generation") == generation
            and pending.get("stage") == "source_check"
        )

    def set_pending_reveal(self, tab_id: str, track_id: str) -> None:
        self._pending_reveal = (str(tab_id), str(track_id))

    def clear_pending_reveal(self) -> None:
        self._pending_reveal = None

    def consume_pending_reveal_for_tab(self, tab_id: str) -> str | None:
        """If a pending reveal matches tab_id, clear and return the track_id."""
        reveal = self._pending_reveal
        if reveal is not None and reveal[0] == tab_id:
            self._pending_reveal = None
            return reveal[1]
        return None
