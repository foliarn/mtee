"""Unit tests for workspace_navigation."""

from __future__ import annotations

from mtee.domain.navigation_history import NavigationHistory, NavigationLocation
from mtee.models.workspace_navigation import (
    WorkspaceNavigationTracker,
    build_navigation_location,
    restore_scroll_and_anchor,
)


def _sample_location(tab_id: str, activity: str = "explorer") -> NavigationLocation:
    return NavigationLocation(
        activity,
        tab_id,
        False,
        False,
        "staging",
        "library",
        {"selected": ["track-1"], "anchor": "track-1"},
    )


def test_build_navigation_location() -> None:
    tab_state = {
        "searchQuery": "queen",
        "sortKey": "title",
        "sortAscending": False,
        "sortMode": "custom",
        "view": "artwork",
    }
    scroll = {("g1", "folder:rock", "artwork"): 120.5}
    anchor = {("g1", "folder:rock", "artwork"): ("trk-5", 10.0)}

    loc = build_navigation_location(
        activity="explorer",
        active_tab_id="folder:rock",
        fullscreen=False,
        right_visible=True,
        right_tab="inspector",
        settings_page="general",
        tab_state=tab_state,
        group_tab_state=None,
        group_id="g1",
        selected=["trk-5"],
        anchor="trk-5",
        scroll=scroll,
        navigation_anchor=anchor,
    )
    assert loc.activity == "explorer"
    assert loc.tab_id == "folder:rock"
    assert loc.view["searchQuery"] == "queen"
    assert loc.view["sortKey"] == "title"
    assert loc.view["sortAscending"] is False
    assert loc.view["scrollArtwork"] == 120.5
    assert loc.view["anchorArtwork"] == ("trk-5", 10.0)


def test_restore_scroll_and_anchor() -> None:
    scroll_dict: dict[tuple[str, str, str], float] = {}
    anchor_dict: dict[tuple[str, str, str], tuple[str, float]] = {}

    view_data = {
        "scrollList": 45.0,
        "anchorList": ("trk-1", 12.0),
        "scrollArtwork": 90.0,
        "anchorArtwork": ["trk-2", 15.0],
    }

    restore_scroll_and_anchor(scroll_dict, anchor_dict, "g1", "tab-1", view_data)
    assert scroll_dict[("g1", "tab-1", "list")] == 45.0
    assert anchor_dict[("g1", "tab-1", "list")] == ("trk-1", 12.0)
    assert scroll_dict[("g1", "tab-1", "artwork")] == 90.0
    assert anchor_dict[("g1", "tab-1", "artwork")] == ("trk-2", 15.0)


def test_navigation_tracker_visit_and_step() -> None:
    tracker = WorkspaceNavigationTracker()
    tracker.histories["g1"] = NavigationHistory()

    loc1 = _sample_location("folder:1")
    loc2 = _sample_location("folder:2")
    loc3 = _sample_location("playlist:p1")

    tracker.visit("g1", loc1)
    tracker.visit("g1", loc2)
    tracker.visit("g1", loc3)

    # Step back
    target_loc, msgs = tracker.step("g1", back=True)
    assert target_loc is not None
    assert target_loc.tab_id == "folder:2"
    assert msgs == []

    # Step back again
    target_loc, msgs = tracker.step("g1", back=True)
    assert target_loc is not None
    assert target_loc.tab_id == "folder:1"

    # Step back beyond root
    target_loc, msgs = tracker.step("g1", back=True)
    assert target_loc is None

    # Step forward to playlist when playlist exists
    target_loc, msgs = tracker.step("g1", back=False)
    assert target_loc is not None
    assert target_loc.tab_id == "folder:2"

    target_loc, msgs = tracker.step("g1", back=False, is_playlist_available=lambda pid: pid == "p1")
    assert target_loc is not None
    assert target_loc.tab_id == "playlist:p1"


def test_navigation_tracker_unavailable_playlist() -> None:
    tracker = WorkspaceNavigationTracker()
    tracker.histories["g1"] = NavigationHistory()
    loc1 = _sample_location("folder:1")
    loc2 = _sample_location("playlist:deleted")
    loc3 = _sample_location("folder:3")

    tracker.visit("g1", loc1)
    tracker.visit("g1", loc2)
    tracker.visit("g1", loc3)

    # Step back: playlist is deleted, so it skips to folder:1 and produces a warning
    target_loc, msgs = tracker.step("g1", back=True, is_playlist_available=lambda pid: False)
    assert target_loc is not None
    assert target_loc.tab_id == "folder:1"
    assert msgs == ["This playlist is no longer available."]


def test_navigation_tracker_split_and_close() -> None:
    tracker = WorkspaceNavigationTracker()
    tracker.histories["g1"] = NavigationHistory()
    tracker.set_scroll("g1", "tab-1", "list", 100.0, "trk-1", 5.0)
    tracker.set_scroll("g2", "tab-2", "list", 200.0, "trk-2", 10.0)

    tracker.add_group("g2", _sample_location("tab-2"))
    assert set(tracker.histories) == {"g1", "g2"}

    tracker.remove_group("g2")
    assert set(tracker.histories) == {"g1"}
    assert tracker.get_scroll("g1", "tab-1", "list") == 100.0
    assert tracker.get_scroll("g2", "tab-2", "list") == 0.0


def test_navigation_tracker_pending_selection() -> None:
    tracker = WorkspaceNavigationTracker()
    tracker.pending_selection = ("g1", "folder:test", ["t1", "t2", "t3"])

    tracker.clear_pending_if_matches("g1", "folder:other")
    assert tracker.pending_selection is not None

    consumed = tracker.consume_pending("g1", "folder:test", {"t1", "t3"})
    assert consumed == ["t1", "t3"]
    assert tracker.pending_selection is None
