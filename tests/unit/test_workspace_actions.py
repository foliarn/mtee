"""Unit tests for workspace_actions."""

from __future__ import annotations

from mtee.models.workspace_actions import (
    can_reorder_playlist,
    extract_recycled_affected_folders,
    filter_valid_identities,
    move_playlist_entry,
    resolve_analyze_folder_target,
    resolve_folder_drop_target,
    set_custom_playlist_order,
    should_prepare_track_inspection,
)

UUID_1 = "12345678-1234-1234-1234-123456789abc"
UUID_2 = "87654321-4321-4321-4321-cba987654321"


def test_resolve_folder_drop_target() -> None:
    roots = {
        UUID_1: {"name": "Music Library"},
    }

    # Drop on root
    res_root = resolve_folder_drop_target(f"root:{UUID_1}", roots)
    assert res_root == (UUID_1, "", "Music Library")

    # Drop on subfolder
    res_sub = resolve_folder_drop_target(f"folder:{UUID_1}/Rock/Classic", roots)
    assert res_sub == (UUID_1, "Rock/Classic", "Classic")

    # Invalid folder
    assert resolve_folder_drop_target("invalid_id", roots) is None


def test_extract_recycled_affected_folders() -> None:
    recycled_items = [
        {"rootId": UUID_1, "parentRelative": "Rock", "status": "recycled"},
        {"rootId": UUID_1, "parentRelative": "Rock", "status": "recycled"},
        {"rootId": UUID_1, "parentRelative": "Pop", "status": "recycled"},
        {"rootId": UUID_2, "parentRelative": "", "status": "recycled"},
        {"rootId": UUID_1, "parentRelative": "Jazz", "status": "failed"},
        {"status": "recycled"},  # Missing rootId
        "not_a_dict",
    ]

    affected = extract_recycled_affected_folders(recycled_items)
    assert affected[UUID_1] == {"Rock", "Pop"}
    assert affected[UUID_2] == {""}

    # Non-list input
    assert extract_recycled_affected_folders(None) == {}


def test_should_prepare_track_inspection() -> None:
    assert should_prepare_track_inspection(True, False, "info") is True
    assert should_prepare_track_inspection(False, False, "info") is False
    assert should_prepare_track_inspection(True, True, "info") is False
    assert should_prepare_track_inspection(True, False, "queue") is False
    assert should_prepare_track_inspection(True, False, "history") is False


def test_filter_valid_identities() -> None:
    raw = ["track-1", "", None, 123, "   "]
    result = filter_valid_identities(raw)
    assert result == ["track-1", "None", "123", "   "]

    assert filter_valid_identities(["", 0, ""]) == ["0"]


def test_can_reorder_playlist() -> None:
    # Allowed
    ok, err = can_reorder_playlist({"sortKey": "index", "searchQuery": ""})
    assert ok is True
    assert err is None

    # Disallowed due to sortKey
    ok_sort, err_sort = can_reorder_playlist({"sortKey": "title", "searchQuery": ""})
    assert ok_sort is False
    assert err_sort == "Switch to Custom order and clear search before reordering."

    # Disallowed due to searchQuery
    ok_q, err_q = can_reorder_playlist({"sortKey": "index", "searchQuery": "beatles"})
    assert ok_q is False
    assert err_q == "Switch to Custom order and clear search before reordering."


def test_move_playlist_entry() -> None:
    entries = ["a", "b", "c", "d"]

    # Move down
    moved_down = move_playlist_entry(entries, "b", 1)
    assert moved_down == ["a", "c", "b", "d"]

    # Move up
    moved_up = move_playlist_entry(entries, "c", -1)
    assert moved_up == ["a", "c", "b", "d"]

    # Clamping at top boundary
    at_top = move_playlist_entry(entries, "a", -5)
    assert at_top == ["a", "b", "c", "d"]

    # Clamping at bottom boundary
    at_bottom = move_playlist_entry(entries, "d", 5)
    assert at_bottom == ["a", "b", "c", "d"]

    # Entry not found
    assert move_playlist_entry(entries, "x", 1) == entries

    # Offset 0
    assert move_playlist_entry(entries, "b", 0) == entries


def test_set_custom_playlist_order() -> None:
    state = {
        "sortMode": "manual",
        "sortKey": "title",
        "sortAscending": False,
        "searchQuery": "test",
    }
    set_custom_playlist_order(state)
    assert state["sortMode"] == "default"
    assert state["sortKey"] == "index"
    assert state["sortAscending"] is True
    assert state["searchQuery"] == ""


def test_resolve_analyze_folder_target() -> None:
    target = resolve_analyze_folder_target(f"folder:{UUID_1}/Electronic")
    assert target == (UUID_1, "Electronic")

    assert resolve_analyze_folder_target("invalid") is None
