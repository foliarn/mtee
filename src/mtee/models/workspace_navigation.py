"""Pure navigation tracker, history state and scroll/anchor persistence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mtee.domain.navigation_history import NavigationHistory, NavigationLocation

__all__ = [
    "WorkspaceNavigationTracker",
    "build_navigation_location",
    "restore_scroll_and_anchor",
]


def build_navigation_location(
    *,
    activity: str,
    active_tab_id: str,
    fullscreen: bool,
    right_visible: bool,
    right_tab: str,
    settings_page: str,
    tab_state: dict[str, Any],
    group_tab_state: dict[str, Any] | None,
    group_id: str,
    selected: list[str],
    anchor: str,
    scroll: dict[tuple[str, str, str], float],
    navigation_anchor: dict[tuple[str, str, str], tuple[str, float]],
) -> NavigationLocation:
    """Build a NavigationLocation snapshot for the given group."""
    tab = dict(tab_state)
    if group_tab_state:
        tab.update(group_tab_state)
    return NavigationLocation(
        activity,
        active_tab_id,
        fullscreen,
        right_visible,
        right_tab,
        settings_page,
        {
            "searchQuery": str(tab.get("searchQuery", "")),
            "sortKey": str(tab.get("sortKey", "index")),
            "sortAscending": bool(tab.get("sortAscending", True)),
            "sortMode": str(tab.get("sortMode", "default")),
            "view": str(tab.get("view", "list")),
            "selected": list(selected),
            "anchor": anchor,
            "scrollList": scroll.get((group_id, active_tab_id, "list"), 0.0),
            "scrollArtwork": scroll.get((group_id, active_tab_id, "artwork"), 0.0),
            "anchorList": navigation_anchor.get((group_id, active_tab_id, "list"), ("", 0.0)),
            "anchorArtwork": navigation_anchor.get((group_id, active_tab_id, "artwork"), ("", 0.0)),
        },
    )


def restore_scroll_and_anchor(
    scroll_dict: dict[tuple[str, str, str], float],
    anchor_dict: dict[tuple[str, str, str], tuple[str, float]],
    group_id: str,
    tab_id: str,
    view_data: dict[str, Any],
) -> None:
    """Extract and restore list/artwork scroll positions and anchors from view data."""
    for view in ("list", "artwork"):
        key = (group_id, tab_id, view)
        scroll_dict[key] = float(view_data.get("scroll" + view.title(), 0.0))
        anchor = view_data.get("anchor" + view.title(), ("", 0.0))
        if isinstance(anchor, (list, tuple)) and len(anchor) == 2:
            anchor_dict[key] = (str(anchor[0]), float(anchor[1]))


class WorkspaceNavigationTracker:
    """Manages navigation histories, scroll positions and anchor points, per group id."""

    def __init__(self) -> None:
        self.histories: dict[str, NavigationHistory] = {}
        self.scroll: dict[tuple[str, str, str], float] = {}
        self.anchor: dict[tuple[str, str, str], tuple[str, float]] = {}
        self.pending_selection: tuple[str, str, list[str]] | None = None
        self.replaying: bool = False

    def add_group(self, group_id: str, initial_location: NavigationLocation) -> None:
        """Start the navigation stack of a new group at ``initial_location``."""
        self.histories[group_id] = NavigationHistory().visit(initial_location)

    def remove_group(self, group_id: str) -> None:
        """Drop the navigation stack and the scroll and anchor positions of a closed group."""
        self.histories.pop(group_id, None)
        self.scroll = {k: v for k, v in self.scroll.items() if k[0] != group_id}
        self.anchor = {k: v for k, v in self.anchor.items() if k[0] != group_id}

    def capture(self, group: str, location: NavigationLocation) -> None:
        """Capture the current state at the current position in history."""
        if self.replaying or group not in self.histories:
            return
        self.pending_selection = None
        self.histories[group] = self.histories[group].capture(location)

    def visit(self, group: str, location: NavigationLocation) -> None:
        """Push a newly visited location to history."""
        if self.replaying or group not in self.histories:
            return
        self.histories[group] = self.histories[group].visit(location)

    def can_back(self, group: str) -> bool:
        """Return True if backward navigation is possible for group."""
        return bool(group in self.histories and self.histories[group].can_back)

    def can_forward(self, group: str) -> bool:
        """Return True if forward navigation is possible for group."""
        return bool(group in self.histories and self.histories[group].can_forward)

    def step(
        self,
        group: str,
        *,
        back: bool,
        is_playlist_available: Callable[[str], bool] | None = None,
    ) -> tuple[NavigationLocation | None, list[str]]:
        """Advance or rewind history for group.

        Returns:
            (location_to_replay_or_none, list_of_warning_messages)
        """
        if group not in self.histories:
            return None, []
        history = self.histories[group]
        messages: list[str] = []
        while True:
            next_history = history.back() if back else history.forward()
            if next_history is history or next_history.current is None:
                return None, messages
            history = next_history
            location = history.current
            assert location is not None
            if location.tab_id.startswith("playlist:") and is_playlist_available is not None:
                playlist_id = location.tab_id.partition(":")[2]
                if not is_playlist_available(playlist_id):
                    messages.append("This playlist is no longer available.")
                    self.histories[group] = history
                    continue
            self.histories[group] = history
            return location, messages

    def set_scroll(
        self,
        group_id: str,
        tab_id: str,
        view: str,
        content_y: float,
        anchor_id: str = "",
        anchor_offset: float = 0.0,
    ) -> None:
        """Store scroll and anchor position for a view."""
        if view in {"list", "artwork"}:
            key = (group_id, tab_id, view)
            self.scroll[key] = max(0.0, content_y)
            self.anchor[key] = (anchor_id, anchor_offset)

    def get_scroll(self, group_id: str, tab_id: str, view: str) -> float:
        """Retrieve stored scroll offset for a view."""
        return self.scroll.get((group_id, tab_id, view), 0.0)

    def get_anchor(self, group_id: str, tab_id: str, view: str) -> dict[str, Any]:
        """Retrieve stored anchor dict for a view."""
        track_id, offset = self.anchor.get((group_id, tab_id, view), ("", 0.0))
        return {"id": track_id, "offset": offset}

    def clear_pending_if_matches(self, group_id: str, tab_id: str) -> None:
        """Clear pending selection if it matches the current group and tab."""
        if self.pending_selection is not None and self.pending_selection[:2] == (
            group_id,
            tab_id,
        ):
            self.pending_selection = None

    def consume_pending(
        self,
        group_id: str,
        tab_id: str,
        available_ids: set[str],
    ) -> list[str] | None:
        """Consume pending navigation selection if matching (group, tab).

        Filters resolved selection by available IDs.
        """
        if self.pending_selection is not None and self.pending_selection[:2] == (
            group_id,
            tab_id,
        ):
            resolved = [
                identity for identity in self.pending_selection[2] if identity in available_ids
            ]
            self.pending_selection = None
            return resolved
        return None
