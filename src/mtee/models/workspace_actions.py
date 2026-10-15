"""Pure helpers and validations for workspace actions across submodels."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from mtee.models.workspace_rows import parse_folder_id

__all__ = [
    "can_reorder_playlist",
    "extract_recycled_affected_folders",
    "filter_valid_identities",
    "move_playlist_entry",
    "resolve_analyze_folder_target",
    "resolve_folder_drop_target",
    "set_custom_playlist_order",
    "should_prepare_track_inspection",
]


def resolve_folder_drop_target(
    folder_id: str,
    roots_by_id: dict[str, Any],
) -> tuple[str, str, str] | None:
    """Parse folder_id and resolve (root_id, relative_path, folder_display_name).

    Returns:
        (root_id, relative_path, folder_name) or None if invalid folder.
    """
    try:
        parsed = parse_folder_id(str(folder_id))
    except ValueError:
        return None
    if parsed is None:
        return None
    root_id, relative = parsed
    root = roots_by_id.get(root_id, {})
    name = relative.rpartition("/")[2] if relative else str(root.get("name", "this folder"))
    return root_id, relative, name


def extract_recycled_affected_folders(recycled: object) -> dict[str, set[str]]:
    """Group successfully recycled items by rootId -> set of parentRelative paths."""
    if not isinstance(recycled, list):
        return {}
    affected: dict[str, set[str]] = {}
    for item in recycled:
        if not isinstance(item, dict) or item.get("status") != "recycled":
            continue
        root_id = str(item.get("rootId", ""))
        if root_id:
            affected.setdefault(root_id, set()).add(str(item.get("parentRelative", "")))
    return affected


def should_prepare_track_inspection(
    right_visible: bool,
    fullscreen: bool,
    right_tab: str,
) -> bool:
    """Return True if the right info panel is currently open and active."""
    return bool(right_visible and not fullscreen and right_tab == "info")


def filter_valid_identities(identities: Iterable[Any]) -> list[str]:
    """Filter and return non-empty string representations of track identities."""
    return [str(identity) for identity in identities if str(identity)]


def can_reorder_playlist(tab_state: dict[str, Any]) -> tuple[bool, str | None]:
    """Check if the playlist tab is in a reorderable state (custom sort, no search)."""
    if tab_state.get("searchQuery") or tab_state.get("sortKey") != "index":
        return False, "Switch to Custom order and clear search before reordering."
    return True, None


def move_playlist_entry(entries: list[str], entry: str, offset: int) -> list[str]:
    """Move a single entry in the list by offset (-1 or +1) without mutating input.

    Returns:
        New reordered list, or unchanged copy if entry not found or offset invalid.
    """
    if entry not in entries or offset == 0:
        return list(entries)
    result = list(entries)
    index = result.index(entry)
    target = min(max(index + offset, 0), len(result) - 1)
    if target == index:
        return result
    result.insert(target, result.pop(index))
    return result


def set_custom_playlist_order(state: dict[str, Any]) -> None:
    """Mutate state in-place to reset playlist to default custom sort and clear search."""
    state.update(
        {
            "sortMode": "default",
            "sortKey": "index",
            "sortAscending": True,
            "searchQuery": "",
        }
    )


def resolve_analyze_folder_target(folder_id: str) -> tuple[str, str] | None:
    """Parse folder_id for folder analysis. Returns (root_id, relative) or None."""
    try:
        parsed = parse_folder_id(str(folder_id))
    except ValueError:
        return None
    return parsed
