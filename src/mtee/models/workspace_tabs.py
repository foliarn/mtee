"""Pure tab and group lifecycle, placement and state management.

Groups are keyed by a stable group id (``"g1"``, ``"g2"``...). The reading order of the
groups comes from the layout tree (``window_layout.groups``), not from this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "build_groups_snapshot",
    "close_tab_in_group",
    "is_tab_in_any_group",
    "keep_tab_state",
    "open_special_tab",
    "place_tab",
    "purge_forgotten_tab_state",
]


def build_groups_snapshot(
    order: Sequence[str],
    groups: Mapping[str, dict[str, Any]],
    tab_states: dict[str, dict[str, Any]],
    group_tab_states: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a serialized snapshot of the groups, in reading order, with their tab states."""
    return [
        {
            "id": group_id,
            "tabs": [
                dict(tab_states.get(tab_id, {})) | group_tab_states.get((group_id, tab_id), {})
                for tab_id in groups[group_id].get("tabs", [])
            ],
            "active": groups[group_id].get("active", ""),
        }
        for group_id in order
        if group_id in groups
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
    groups: Mapping[str, dict[str, Any]],
    group_id: str,
    tab_id: str,
) -> tuple[bool, str]:
    """Remove a tab from a group and update the active tab if necessary.

    Returns:
        (was_closed, new_active_tab_id)
    """
    if group_id not in groups:
        return False, ""
    group = groups[group_id]
    tabs: list[str] = group["tabs"]
    if tab_id not in tabs:
        return False, str(group.get("active", ""))
    old_index = tabs.index(tab_id)
    tabs.remove(tab_id)
    if group.get("active") == tab_id:
        group["active"] = tabs[min(old_index, len(tabs) - 1)] if tabs else ""
    return True, str(group.get("active", ""))


def is_tab_in_any_group(groups: Mapping[str, dict[str, Any]], tab_id: str) -> bool:
    """Check if a tab ID is present in any group's tab list."""
    return any(tab_id in group.get("tabs", []) for group in groups.values())


def open_special_tab(
    group: dict[str, Any],
    tab_state: dict[str, Any],
    tab_id: str,
    title: str,
) -> None:
    """Configure a special tab (settings, convert, profile, tasks...) and activate it.

    The ref is what follows the kind, as when the session restores the tab: the plugin id of a
    plugin detail tab, the view of an artists or genre manager tab, empty for the others.
    """
    kind, _, ref = tab_id.partition(":")
    tab_state.update({"id": tab_id, "kind": kind, "ref": ref, "title": title})
    tabs: list[str] = group["tabs"]
    if tab_id not in tabs:
        tabs.append(tab_id)
    group["active"] = tab_id


def keep_tab_state(tab_state: dict[str, Any]) -> bool:
    """Turn a preview tab into a permanent tab by removing the preview flag."""
    return bool(tab_state.pop("preview", None))


def purge_forgotten_tab_state(
    tab_id: str,
    tab_states: dict[str, Any],
    group_tab_states: dict[tuple[str, str], Any],
    selection_by_tab: dict[tuple[str, str], Any],
    anchor_by_tab: dict[tuple[str, str], Any],
) -> None:
    """Purge cached tab states, selections and anchors when a tab leaves all groups."""
    tab_states.pop(tab_id, None)
    for store in (group_tab_states, selection_by_tab, anchor_by_tab):
        for k in [k for k in store if k[1] == tab_id]:
            del store[k]
