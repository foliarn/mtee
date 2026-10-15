"""Unit tests for workspace_explorer."""

from __future__ import annotations

from mtee.models.workspace_explorer import (
    ExplorerTrackCoordinator,
    find_revealed_track_row,
    resolve_folder_source_exists,
    update_captured_rows,
    validate_explorer_track,
)


def test_resolve_folder_source_exists() -> None:
    root_uuid = "12345678-1234-1234-1234-123456789abc"
    roots = {root_uuid: {"name": "Music"}}
    subfolders = {root_uuid: ["Electronic", "Rock/Classic"]}

    # Valid root
    assert (
        resolve_folder_source_exists(f"root:{root_uuid}", roots, lambda r: subfolders.get(r, []))
        is True
    )

    # Valid subfolder
    assert (
        resolve_folder_source_exists(
            f"folder:{root_uuid}/Electronic", roots, lambda r: subfolders.get(r, [])
        )
        is True
    )

    # Unknown root
    other_uuid = "87654321-4321-4321-4321-cba987654321"
    assert (
        resolve_folder_source_exists(f"root:{other_uuid}", roots, lambda r: subfolders.get(r, []))
        is False
    )

    # Unknown subfolder
    assert (
        resolve_folder_source_exists(
            f"folder:{root_uuid}/Ambient", roots, lambda r: subfolders.get(r, [])
        )
        is False
    )

    # Invalid source format
    assert resolve_folder_source_exists("not_a_folder", roots, lambda r: []) is False


def test_find_revealed_track_row() -> None:
    rows = [
        {"id": "t1", "title": "Track 1"},
        {"id": "row2", "trackId": "t2", "title": "Track 2"},
    ]

    # Find by id
    found1 = find_revealed_track_row(rows, "t1")
    assert found1 is not None and found1["title"] == "Track 1"

    # Find by trackId
    found2 = find_revealed_track_row(rows, "t2")
    assert found2 is not None and found2["title"] == "Track 2"

    # Not found
    assert find_revealed_track_row(rows, "t3") is None
    assert find_revealed_track_row(rows, "") is None


def test_validate_explorer_track() -> None:
    valid_track = {
        "id": "t1",
        "rootId": "r1",
        "relativePath": "Electronic/song.mp3",
        "path": "C:/Music/Electronic/song.mp3",
    }

    # Valid
    ok, err = validate_explorer_track(valid_track, "r1", "Electronic")
    assert ok is True
    assert err is None

    # Empty / None
    ok_empty, err_empty = validate_explorer_track(None, "r1", "Electronic")
    assert ok_empty is False
    assert err_empty == "This file is no longer in the library."

    # Root mismatch
    ok_root, err_root = validate_explorer_track(valid_track, "r2", "Electronic")
    assert ok_root is False
    assert err_root == "This file is no longer in this folder."

    # Subfolder mismatch
    ok_sub, err_sub = validate_explorer_track(valid_track, "r1", "Ambient")
    assert ok_sub is False
    assert err_sub == "This file is no longer in this folder."


def test_update_captured_rows() -> None:
    rows = [
        {"id": "t1", "title": "Old Title 1"},
        {"id": "t2", "title": "Title 2"},
    ]
    updated_track = {"id": "t1", "title": "New Title 1"}

    # Replace existing
    res = update_captured_rows(rows, "t1", updated_track)
    assert res is not None
    assert res[0]["title"] == "New Title 1"
    assert res[1]["title"] == "Title 2"

    # Not in rows
    assert update_captured_rows(rows, "t99", updated_track) is None


def test_explorer_track_coordinator_lifecycle() -> None:
    coord = ExplorerTrackCoordinator()
    assert coord.activation_generation == 0
    assert coord.pending is None
    assert coord.job_id == ""

    # Start a request
    pending, prev_job = coord.start_request(
        track_id="t1",
        source="folder:r1/Rock",
        root_id="r1",
        relative="Rock",
        tab_id="folder:r1/Rock",
        group_index=0,
        play=True,
        rows_generation=1,
    )
    assert prev_job is None
    assert coord.activation_generation == 1
    assert pending["mode"] == "activate"

    coord.set_pending(pending)
    assert coord.pending == pending

    # Check context is current
    groups = [{"active": "folder:r1/Rock"}]
    assert coord.is_context_current(pending, active_group=0, groups=groups) is True
    assert coord.is_context_current(pending, active_group=1, groups=groups) is False

    # Check ignore request for duplicate select
    coord.record_job("job-123")
    assert coord.should_ignore_request("t1", "folder:r1/Rock", active_group=0, play=False) is True
    assert coord.should_ignore_request("t1", "folder:r1/Rock", active_group=0, play=True) is False

    # Matching ready check
    assert coord.is_matching_ready(coord.activation_generation) is False
    pending["stage"] = "source_check"
    assert coord.is_matching_ready(coord.activation_generation) is True

    # Cancel action returns job_id
    cancelled_job = coord.cancel_action()
    assert cancelled_job == "job-123"
    assert coord.pending is None
    assert coord.job_id == ""

    # Cancel action for tab
    coord.set_pending({"tab_id": "folder:r1/Rock"})
    coord.record_job("job-456")
    assert coord.cancel_action_for_tab("other_tab") is None
    assert coord.cancel_action_for_tab("folder:r1/Rock") == "job-456"
    assert coord.pending is None


def test_explorer_pending_reveal() -> None:
    coord = ExplorerTrackCoordinator()
    assert coord.pending_reveal is None

    coord.set_pending_reveal("tab1", "t100")
    assert coord.pending_reveal == ("tab1", "t100")

    # Mismatched tab
    assert coord.consume_pending_reveal_for_tab("other") is None
    assert coord.pending_reveal == ("tab1", "t100")

    # Matching tab consumes
    assert coord.consume_pending_reveal_for_tab("tab1") == "t100"
    assert coord.pending_reveal is None

    # Clear pending reveal
    coord.set_pending_reveal("tab2", "t200")
    coord.clear_pending_reveal()
    assert coord.pending_reveal is None
