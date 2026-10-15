"""Unit tests for workspace_tabs."""

from __future__ import annotations

from mtee.models.workspace_tabs import (
    build_groups_snapshot,
    close_tab_in_group,
    create_split_group,
    is_tab_in_any_group,
    keep_tab_state,
    merge_group_tabs_on_close,
    open_special_tab,
    place_tab,
    purge_forgotten_tab_state,
)


def test_build_groups_snapshot() -> None:
    groups = [
        {"tabs": ["tab-1", "tab-2"], "active": "tab-1"},
    ]
    tab_states = {
        "tab-1": {"title": "Folder 1", "view": "list"},
        "tab-2": {"title": "Folder 2", "view": "artwork"},
    }
    group_tab_states = {
        (0, "tab-1"): {"searchQuery": "test"},
    }

    snapshot = build_groups_snapshot(groups, tab_states, group_tab_states)
    assert len(snapshot) == 1
    assert snapshot[0]["active"] == "tab-1"
    assert len(snapshot[0]["tabs"]) == 2
    assert snapshot[0]["tabs"][0]["searchQuery"] == "test"
    assert snapshot[0]["tabs"][0]["title"] == "Folder 1"


def test_place_tab_permanent() -> None:
    group = {"tabs": ["tab-1"], "active": "tab-1"}
    tab_states: dict[str, dict[str, object]] = {}

    displaced = place_tab(group, tab_states, "tab-2", preview=False, preview_enabled=True)
    assert displaced is None
    assert group["tabs"] == ["tab-1", "tab-2"]


def test_place_tab_preview_replacement() -> None:
    group = {"tabs": ["tab-1", "tab-prev1"], "active": "tab-prev1"}
    tab_states: dict[str, dict[str, object]] = {
        "tab-prev1": {"preview": True},
    }

    displaced = place_tab(group, tab_states, "tab-prev2", preview=True, preview_enabled=True)
    assert displaced == "tab-prev1"
    assert group["tabs"] == ["tab-1", "tab-prev2"]
    assert tab_states["tab-prev2"]["preview"] is True


def test_close_tab_in_group() -> None:
    groups = [
        {"tabs": ["t1", "t2", "t3"], "active": "t2"},
    ]
    closed, new_active = close_tab_in_group(groups, 0, "t2")
    assert closed is True
    assert new_active == "t3"
    assert groups[0]["tabs"] == ["t1", "t3"]

    # Close last tab
    closed, new_active = close_tab_in_group(groups, 0, "t3")
    assert closed is True
    assert new_active == "t1"

    # Close only tab
    closed, new_active = close_tab_in_group(groups, 0, "t1")
    assert closed is True
    assert new_active == ""
    assert groups[0]["tabs"] == []


def test_is_tab_in_any_group() -> None:
    groups = [
        {"tabs": ["t1", "t2"]},
        {"tabs": ["t3"]},
    ]
    assert is_tab_in_any_group(groups, "t1") is True
    assert is_tab_in_any_group(groups, "t3") is True
    assert is_tab_in_any_group(groups, "t4") is False


def test_open_special_tab() -> None:
    group = {"tabs": ["t1"], "active": "t1"}
    state: dict[str, object] = {}

    open_special_tab(group, state, "settings:", "Settings")
    assert group["tabs"] == ["t1", "settings:"]
    assert group["active"] == "settings:"
    assert state["kind"] == "settings"
    assert state["title"] == "Settings"


def test_create_split_and_merge() -> None:
    split = create_split_group("t1")
    assert split["tabs"] == ["t1"]
    assert split["active"] == "t1"

    group0 = {"tabs": ["t1"], "active": "t1"}
    group1 = {"tabs": ["t1", "t2", "t3"], "active": "t2"}
    merge_group_tabs_on_close(group0, group1)
    assert group0["tabs"] == ["t1", "t2", "t3"]


def test_keep_tab_state() -> None:
    state = {"preview": True, "title": "Test"}
    assert keep_tab_state(state) is True
    assert "preview" not in state
    assert keep_tab_state(state) is False


def test_purge_forgotten_tab_state() -> None:
    tab_states = {"t1": {}, "t2": {}}
    group_tab_states = {(0, "t1"): {}, (1, "t2"): {}}
    selection = {(0, "t1"): ["a"], (0, "t2"): ["b"]}
    anchor = {(0, "t1"): "a", (0, "t2"): "b"}

    purge_forgotten_tab_state("t1", tab_states, group_tab_states, selection, anchor)
    assert "t1" not in tab_states
    assert (0, "t1") not in group_tab_states
    assert (0, "t1") not in selection
    assert (0, "t1") not in anchor
    assert "t2" in tab_states
