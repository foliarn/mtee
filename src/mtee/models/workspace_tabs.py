"""Pure tab and group lifecycle, placement, split view and state management."""

from __future__ import annotations

from typing import Any

__all__ = [
    "build_groups_snapshot",
    "close_tab_in_group",
    "create_split_group",
    "is_tab_in_any_group",
    "keep_tab_state",
    "merge_group_tabs_on_close",
    "open_special_tab",
    "place_tab",
    "purge_forgotten_tab_state",
]


def build_groups_snapshot(
    groups: list[dict[str, Any]],
    tab_states: dict[str, dict[str, Any]],
    group_tab_states: dict[tuple[int, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a serialized snapshot of all groups and their tab states."""
    return [
        {
            "tabs": [
                dict(tab_states.get(tab_id, {})) | group_tab_states.get((index, tab_id), {})
                for tab_id in group.get("tabs", [])
            ],
            "active": group.get("active", ""),
        }
        for index, group in enumerate(groups)
    ]


def place_tab(
    group: dict[str, Any],
    tab_states: dict[str, dict[str, Any]],
    tab_id: str,
    *,
    preview: bool,
    preview_enabled: bool,
) -> str | None:
    """Add a tab to a group; a preview tab replaces an existing preview tab in the group.

    Returns:
        The replaced preview tab ID if one was displaced, otherwise None.
    """
    tabs: list[str] = group["tabs"]
    if tab_id in tabs:
        return None
    if not (preview and preview_enabled):
        tabs.append(tab_id)
        return None

    state = tab_states.setdefault(tab_id, {})
    state["preview"] = True
    old = next((item for item in tabs if tab_states.get(item, {}).get("preview")), None)
    if old is None:
        tabs.append(tab_id)
        return None

    tabs.insert(tabs.index(old), tab_id)
    tabs.remove(old)
    return old


def close_tab_in_group(
    groups: list[dict[str, Any]],
    group_index: int,
    tab_id: str,
) -> tuple[bool, str]:
    """Remove a tab from a group and update the active tab if necessary.

    Returns:
        (was_closed, new_active_tab_id)
    """
    if not (0 <= group_index < len(groups)):
        return False, ""
    group = groups[group_index]
    tabs: list[str] = group["tabs"]
    if tab_id not in tabs:
        return False, str(group.get("active", ""))
    old_index = tabs.index(tab_id)
    tabs.remove(tab_id)
    if group.get("active") == tab_id:
        group["active"] = tabs[min(old_index, len(tabs) - 1)] if tabs else ""
    return True, str(group.get("active", ""))


def is_tab_in_any_group(groups: list[dict[str, Any]], tab_id: str) -> bool:
    """Check if a tab ID is present in any group's tab list."""
    return any(tab_id in group.get("tabs", []) for group in groups)


def open_special_tab(
    group: dict[str, Any],
    tab_state: dict[str, Any],
    tab_id: str,
    title: str,
) -> None:
    """Configure a special tab (settings, convert, profile, tasks...) and activate it."""
    kind = tab_id.partition(":")[0]
    tab_state.update({"id": tab_id, "kind": kind, "ref": "", "title": title})
    tabs: list[str] = group["tabs"]
    if tab_id not in tabs:
        tabs.append(tab_id)
    group["active"] = tab_id


def create_split_group(active_tab_id: str) -> dict[str, Any]:
    """Create a new group dictionary for split view initialization."""
    return {
        "tabs": [active_tab_id] if active_tab_id else [],
        "active": active_tab_id,
        "selections": {active_tab_id: {"ids": [], "anchor": ""}} if active_tab_id else {},
    }


def merge_group_tabs_on_close(group0: dict[str, Any], group1: dict[str, Any]) -> None:
    """Merge non-duplicate tabs from group1 into group0 when closing split view."""
    tabs0: list[str] = group0["tabs"]
    for tab_id in group1.get("tabs", []):
        if tab_id not in tabs0:
            tabs0.append(tab_id)
    if not group0.get("active"):
        group0["active"] = group1.get("active", "")


def keep_tab_state(tab_state: dict[str, Any]) -> bool:
    """Turn a preview tab into a permanent tab by removing the preview flag."""
    return bool(tab_state.pop("preview", None))


def purge_forgotten_tab_state(
    tab_id: str,
    tab_states: dict[str, Any],
    group_tab_states: dict[tuple[int, str], Any],
    selection_by_tab: dict[tuple[int, str], Any],
    anchor_by_tab: dict[tuple[int, str], Any],
) -> None:
    """Purge cached tab states, selections and anchors when a tab leaves all groups."""
    tab_states.pop(tab_id, None)
    group_tab_keys = [k for k in group_tab_states if k[1] == tab_id]
    for k in group_tab_keys:
        del group_tab_states[k]
    selection_keys = [k for k in selection_by_tab if k[1] == tab_id]
    for k in selection_keys:
        del selection_by_tab[k]
    anchor_keys = [k for k in anchor_by_tab if k[1] == tab_id]
    for k in anchor_keys:
        del anchor_by_tab[k]
