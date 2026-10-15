"""Pure unit tests for workspace_session: serialization, restoration, tab defaulting."""

from __future__ import annotations

from mtee.models.workspace_session import (
    WorkspaceSessionWriter,
    build_session_snapshot,
    ensure_tab_state,
    extract_view_fields,
    restore_session_groups,
    set_default_sort,
)

ROOT = "0f8fad5b-d9cb-469f-a165-70867728950e"


def test_extract_view_fields_filters_only_view_properties() -> None:
    tab = {
        "id": "tab-1",
        "title": "Title",
        "searchQuery": "test",
        "sortKey": "bpm",
        "sortAscending": False,
        "sortMode": "manual",
        "view": "artwork",
        "extra": "ignored",
    }
    extracted = extract_view_fields(tab)
    assert extracted == {
        "searchQuery": "test",
        "sortKey": "bpm",
        "sortAscending": False,
        "sortMode": "manual",
        "view": "artwork",
    }


def test_set_default_sort_handles_folders_and_playlists() -> None:
    folder_state: dict[str, object] = {"kind": "folder"}
    set_default_sort(folder_state)
    assert folder_state["sortMode"] == "default"
    assert folder_state["sortKey"] == "fileCreatedAt"
    assert folder_state["sortAscending"] is False

    playlist_state: dict[str, object] = {"kind": "playlist"}
    set_default_sort(playlist_state)
    assert playlist_state["sortMode"] == "default"
    assert playlist_state["sortKey"] == "index"
    assert playlist_state["sortAscending"] is True


def test_ensure_tab_state_initializes_missing_defaults() -> None:
    tab_states: dict[str, dict[str, object]] = {}
    roots_by_id = {ROOT: {"name": "My Music"}}

    state = ensure_tab_state(f"folder:{ROOT}/Techno", tab_states, roots_by_id)
    assert state["id"] == f"folder:{ROOT}/Techno"
    assert state["kind"] == "folder"
    assert state["ref"] == f"{ROOT}/Techno"
    assert state["title"] == "Techno"
    assert state["sortKey"] == "fileCreatedAt"
    assert "columnWidths" in state
    assert "columnOrder" in state


def test_restore_session_groups_normalizes_empty_and_valid_groups() -> None:
    empty_groups, empty_tabs = restore_session_groups([])
    assert empty_groups == [{"tabs": [], "active": "", "selections": {}}]
    assert empty_tabs == {}

    raw = [
        {
            "tabs": [
                {"id": f"folder:{ROOT}/", "kind": "folder", "ref": f"{ROOT}/"},
                {"id": "playlist:abc", "kind": "playlist", "ref": "abc"},
                {"id": "broken", "kind": "unknown"},
            ],
            "active": "playlist:abc",
            "selections": {"playlist:abc": {"ids": ["t1"], "anchor": "t1"}},
        }
    ]
    groups, tab_states = restore_session_groups(raw)
    assert len(groups) == 1
    assert groups[0]["tabs"] == [f"folder:{ROOT}/", "playlist:abc"]
    assert groups[0]["active"] == "playlist:abc"
    assert "playlist:abc" in tab_states
    assert f"folder:{ROOT}/" in tab_states


def test_build_session_snapshot_constructs_valid_dictionary() -> None:
    snapshot = build_session_snapshot(
        expanded={ROOT},
        groups=[{"tabs": ["tab-1"], "active": "tab-1"}],
        tab_states={"tab-1": {"id": "tab-1", "title": "Tab 1"}},
        selection_by_tab={(0, "tab-1"): ["track-1"]},
        anchor_by_tab={(0, "tab-1"): "track-1"},
        active_group=0,
        activity="explorer",
        sidebar_visible=True,
        right_visible=False,
        right_tab="info",
        sidebar_width=240,
        right_panel_width=360,
        island_enabled=True,
        preview_tabs=True,
        column_preferences={"order": ["title"], "hidden": [], "widths": {}, "showArtwork": True},
    )
    assert snapshot["version"] == 1
    assert snapshot["expanded"] == [ROOT]
    assert snapshot["activeGroup"] == 0
    assert snapshot["groups"][0]["tabs"][0]["id"] == "tab-1"
    assert snapshot["groups"][0]["selections"]["tab-1"]["ids"] == ["track-1"]


def test_workspace_session_writer_lifecycle() -> None:
    saved: list[dict[str, object]] = []
    events: list[tuple[object, object]] = []

    def save(state: dict[str, object]) -> None:
        saved.append(state)

    def on_finished(future: object, error: object) -> None:
        events.append((future, error))

    writer = WorkspaceSessionWriter(save_fn=save, on_write_finished=on_finished)
    assert writer.is_closed is False
    assert writer.has_pending is False
    assert writer.is_writing is False

    # Submit first write
    state1 = {"version": 1, "test": "a"}
    writer.write_pending(state1)
    assert writer.is_writing is True

    # Buffer second write while in flight
    state2 = {"version": 1, "test": "b"}
    writer.write_pending(state2)
    assert writer.has_pending is True

    # Wait for first write to complete
    future1 = writer.future
    assert future1 is not None
    future1.result(timeout=2.0)

    # Handle completion -> triggers pending write
    matched, err = writer.handle_write_finished(future1, None)
    assert matched is True
    assert err is None
    assert writer.has_pending is False
    assert writer.is_writing is True

    # Wait for second write
    future2 = writer.future
    assert future2 is not None
    future2.result(timeout=2.0)
    matched2, err2 = writer.handle_write_finished(future2, None)
    assert matched2 is True
    assert err2 is None
    assert writer.is_writing is False

    assert len(saved) == 2
    assert saved[0]["test"] == "a"
    assert saved[1]["test"] == "b"

    # Flush
    final_state = {"version": 1, "test": "final"}
    flush_err = writer.flush(final_state)
    assert flush_err is None
    assert writer.is_closed is True
    assert len(saved) == 3
    assert saved[2]["test"] == "final"

    # Subsequent writes ignored when closed
    writer.write_pending({"ignored": True})
    assert len(saved) == 3


def test_workspace_session_writer_mismatched_future() -> None:
    writer = WorkspaceSessionWriter(save_fn=lambda _: None)
    matched, err = writer.handle_write_finished(object(), None)
    assert matched is False
    assert err is None
    writer.flush({})
