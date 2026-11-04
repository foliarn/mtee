"""Pure unit tests for workspace_session: serialization, restoration, tab defaulting."""

from __future__ import annotations

from mtee.models import window_layout as layout
from mtee.models.window_layout import Leaf, Split
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
    empty_groups, empty_tree, empty_tabs, _next = restore_session_groups([])
    assert empty_groups == {"g1": {"tabs": [], "active": "", "selections": {}}}
    assert empty_tree == Leaf("g1")
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
    groups, tree, tab_states, _next = restore_session_groups(raw)
    assert list(groups) == ["g1"]
    assert tree == Leaf("g1")
    assert groups["g1"]["tabs"] == [f"folder:{ROOT}/", "playlist:abc"]
    assert groups["g1"]["active"] == "playlist:abc"
    assert "playlist:abc" in tab_states
    assert f"folder:{ROOT}/" in tab_states


def test_restore_session_groups_two_groups_sit_side_by_side() -> None:
    raw = [
        {"tabs": [{"id": "playlist:a", "kind": "playlist", "ref": "a"}], "active": "playlist:a"},
        {"tabs": [{"id": "playlist:b", "kind": "playlist", "ref": "b"}], "active": "playlist:b"},
    ]
    groups, tree, _tabs, next_group = restore_session_groups(raw)
    assert list(groups) == ["g1", "g2"]
    assert tree == Split("row", (Leaf("g1"), Leaf("g2")), (0.5, 0.5))
    assert next_group == 3


def test_restore_session_groups_keeps_a_saved_center_tree_and_three_groups() -> None:
    raw = [
        {"id": "g1", "tabs": [], "active": ""},
        {"id": "g7", "tabs": [], "active": ""},
        {"id": "g3", "tabs": [], "active": ""},
    ]
    center = {
        "type": "split",
        "orientation": "column",
        "children": [
            {"type": "leaf", "group": "g1"},
            {
                "type": "split",
                "orientation": "row",
                "children": [
                    {"type": "leaf", "group": "g7"},
                    {"type": "leaf", "group": "g3"},
                ],
                "ratios": [0.5, 0.5],
            },
        ],
        "ratios": [0.6, 0.4],
    }
    groups, tree, _tabs, _next = restore_session_groups(raw, None, center)
    assert list(groups) == ["g1", "g7", "g3"]
    assert tree == layout.node_from_dict(center)
    # A tree that does not place exactly these groups is replaced by a side-by-side layout.
    groups, tree, _tabs, _next = restore_session_groups(raw, None, {"type": "leaf", "group": "zz"})
    assert layout.groups(tree) == ("g1", "g7", "g3")


def test_build_session_snapshot_constructs_valid_dictionary() -> None:
    snapshot = build_session_snapshot(
        expanded={ROOT},
        groups={"g1": {"tabs": ["tab-1"], "active": "tab-1"}},
        layout_tree=Leaf("g1"),
        tab_states={"tab-1": {"id": "tab-1", "title": "Tab 1"}},
        selection_by_tab={("g1", "tab-1"): ["track-1"]},
        anchor_by_tab={("g1", "tab-1"): "track-1"},
        active_group="g1",
        activity="explorer",
        sidebar_visible=True,
        right_visible=False,
        right_tab="info",
        sidebar_width=240,
        right_panel_width=360,
        preview_tabs=True,
        column_preferences={"order": ["title"], "hidden": [], "widths": {}, "showArtwork": True},
    )
    assert snapshot["version"] == 2
    assert snapshot["expanded"] == [ROOT]
    assert snapshot["activeGroup"] == "g1"
    assert snapshot["center"] == {"type": "leaf", "group": "g1"}
    assert snapshot["groups"][0]["id"] == "g1"
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


# --- Saved layout version 2 (plan 131.3) -------------------------------------------------------

from pathlib import Path  # noqa: E402

from mtee.persistence import workspace_repository as repo  # noqa: E402


def _v1_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "version": 1,
        "roots": [],
        "expanded": [],
        "groups": [{"tabs": [], "active": ""}],
        "activeGroup": 0,
        "activity": "explorer",
        "sidebarVisible": True,
        "sidebarWidth": 300,
        "rightPanelVisible": True,
        "rightPanelTab": "queue",
        "rightPanelWidth": 400,
        "previewTabs": True,
    }
    state.update(overrides)
    return state


def test_v1_state_with_one_group_converts_to_v2_docks() -> None:
    converted = repo.convert_v1_state(_v1_state())
    assert converted["version"] == 2
    assert converted["center"] == {"type": "leaf", "group": "g1"}
    assert converted["activeGroup"] == "g1"
    assert converted["groups"][0]["id"] == "g1"
    assert converted["docks"]["left"] == {
        "open": True,
        "width": 300,
        "windows": ["explorer"],
        "ratio": 0.5,
    }
    assert converted["docks"]["right"]["open"] is True
    assert converted["docks"]["right"]["windows"] == ["queue"]
    assert converted["docks"]["right"]["width"] == 400
    assert "islandEnabled" not in converted
    assert "activity" not in converted


def test_v1_state_with_two_groups_becomes_a_row_split() -> None:
    state = _v1_state(
        groups=[
            {"tabs": [], "active": ""},
            {"tabs": [], "active": ""},
        ],
        activeGroup=1,
    )
    converted = repo.convert_v1_state(state)
    assert converted["center"] == {
        "type": "split",
        "orientation": "row",
        "children": [{"type": "leaf", "group": "g1"}, {"type": "leaf", "group": "g2"}],
        "ratios": [0.5, 0.5],
    }
    assert converted["activeGroup"] == "g2"
    validated = repo._validated(converted)
    assert [group["id"] for group in validated["groups"]] == ["g1", "g2"]


def test_v1_state_with_unknown_activity_falls_back_to_explorer() -> None:
    converted = repo.convert_v1_state(_v1_state(activity="removed_window"))
    assert converted["docks"]["left"]["windows"] == ["explorer"]
    plugin = repo.convert_v1_state(_v1_state(activity="sample.panel"))
    assert plugin["docks"]["left"]["windows"] == ["sample.panel"]


def test_v2_state_round_trips_through_snapshot_and_validation() -> None:
    tree = Split("row", (Leaf("g1"), Leaf("g2")), (0.4, 0.6))
    snapshot = build_session_snapshot(
        expanded=set(),
        groups={"g1": {"tabs": [], "active": ""}, "g2": {"tabs": [], "active": ""}},
        layout_tree=tree,
        tab_states={},
        selection_by_tab={},
        anchor_by_tab={},
        active_group="g2",
        activity="playlists",
        sidebar_visible=False,
        right_visible=True,
        right_tab="history",
        sidebar_width=260,
        right_panel_width=320,
        preview_tabs=False,
        column_preferences={"order": ["title"], "hidden": [], "widths": {}, "showArtwork": True},
        next_group=3,
    )
    assert snapshot["version"] == 2
    assert snapshot["activeGroup"] == "g2"
    assert snapshot["nextGroup"] == 3
    assert snapshot["docks"]["left"]["open"] is False
    assert snapshot["docks"]["right"]["windows"] == ["history"]
    validated = repo._validated(snapshot)
    assert validated["center"] == layout.node_to_dict(tree)
    assert validated["activeGroup"] == "g2"
    assert validated["nextGroup"] == 3
    assert validated["docks"]["left"]["windows"] == ["playlists"]
    assert validated["docks"]["right"]["width"] == 320
    assert validated["previewTabs"] is False


def test_corrupt_v2_docks_fall_back_to_defaults() -> None:
    corrupt = repo.DEFAULT_WORKSPACE | {
        "docks": {
            "left": {"open": "yes", "width": "wide", "windows": [7, "explorer"], "ratio": 9},
            "right": {"width": 99999, "windows": ["info", "nope", "queue", "history"]},
        },
        "nextGroup": "many",
    }
    validated = repo._validated(corrupt)
    assert validated["docks"]["left"]["open"] is True
    assert validated["docks"]["left"]["width"] == 260
    assert validated["docks"]["left"]["windows"] == ["explorer"]
    assert validated["docks"]["left"]["ratio"] == 0.9
    assert validated["docks"]["right"]["width"] == 480
    assert validated["docks"]["right"]["windows"] == ["info"]
    assert validated["nextGroup"] == 1
    assert repo._has_valid_session_structure(corrupt) is True
    assert repo._has_valid_session_structure("not a dict") is False
    assert (
        repo._validated({"version": 2, "docks": "broken"})["docks"]
        == repo.DEFAULT_WORKSPACE["docks"]
    )


class _FakeDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path


def test_v1_backup_is_written_once_and_never_overwritten(tmp_path: Path) -> None:
    database_file = tmp_path / "mtee.sqlite"
    database_file.write_bytes(b"")
    repository = repo.WorkspaceRepository(_FakeDatabase(database_file))  # type: ignore[arg-type]
    repository._backup_v1('{"version": 1, "first": true}')
    backup = tmp_path / repo.V1_BACKUP_NAME
    assert backup.read_text(encoding="utf-8") == '{"version": 1, "first": true}'
    repository._backup_v1('{"version": 1, "second": true}')
    assert backup.read_text(encoding="utf-8") == '{"version": 1, "first": true}'


def test_a_saved_tasks_window_is_dropped_when_the_layout_loads() -> None:
    # The Tasks tool window was removed (plan 134.6): a dock that held it keeps its other windows,
    # and a dock that held only it closes.
    state = repo._validated(None)
    state["docks"]["left"]["windows"] = ["tasks", "explorer"]
    assert repo._validated(state)["docks"]["left"]["windows"] == ["explorer"]

    state["docks"]["left"]["windows"] = ["tasks"]
    left = repo._validated(state)["docks"]["left"]
    assert left["windows"] == []
    assert left["open"] is False


def test_the_snapshot_keeps_both_docks_and_the_window_and_restores_special_tabs() -> None:
    docks = {
        "left": layout.DockState("left", True, 300, ("explorer", "playlists"), 0.4),
        "right": layout.DockState("right", False, 410, ("queue", "info"), 0.7),
    }
    snapshot = build_session_snapshot(
        expanded=set(),
        groups={"g1": {"tabs": ["settings:"], "active": "settings:"}},
        layout_tree=Leaf("g1"),
        tab_states={"settings:": {"id": "settings:", "kind": "settings", "ref": "", "title": "S"}},
        selection_by_tab={},
        anchor_by_tab={},
        active_group="g1",
        activity="explorer",
        sidebar_visible=True,
        right_visible=False,
        right_tab="info",
        sidebar_width=240,
        right_panel_width=360,
        preview_tabs=True,
        column_preferences={},
        docks=docks,
        window={"x": 1, "y": 2, "width": 900, "height": 700, "maximized": True},
    )
    assert snapshot["docks"]["left"]["windows"] == ["explorer", "playlists"]
    assert snapshot["docks"]["right"]["ratio"] == 0.7
    assert snapshot["window"]["maximized"] is True
    groups, _tree, tab_states, _next = restore_session_groups(snapshot["groups"])
    assert groups["g1"]["tabs"] == ["settings:"]
    assert tab_states["settings:"]["kind"] == "settings"
