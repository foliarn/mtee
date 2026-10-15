"""Unit tests for workspace_scan_coordinator."""

from __future__ import annotations

import os

from mtee.models.workspace_scan_coordinator import (
    FolderBranchTracker,
    WorkspaceScanCoordinator,
    compute_folder_watch_targets,
    format_scan_finished_message,
)


def test_compute_folder_watch_targets() -> None:
    r1 = "00000000-0000-0000-0000-000000000001"
    r2 = "00000000-0000-0000-0000-000000000002"
    groups = [
        {"active": f"folder:{r1}/album1"},
        {"active": "playlist:p1"},
        {"active": f"folder:{r2}"},
        {"active": "invalid_folder_id"},
    ]
    roots = {
        r1: {"path": "C:/music/r1"},
        r2: {"path": "C:/music/r2"},
    }
    targets, paths, active = compute_folder_watch_targets(groups, roots)

    assert (r1, "album1") in active
    assert (r2, "") in active
    assert len(paths) == 2

    # Check targets resolution by normalized path
    norm_path1 = os.path.normcase(os.path.normpath("C:/music/r1/album1"))
    norm_path2 = os.path.normcase(os.path.normpath("C:/music/r2"))
    assert targets[norm_path1] == (r1, "album1")
    assert targets[norm_path2] == (r2, "")


def test_format_scan_finished_message() -> None:
    # Cancelled
    assert "cancelled" in format_scan_finished_message({"cancelled": True}, 10, False)  # type: ignore

    # Unavailable
    res_unavail = {"cancelled": False, "available": False}
    assert "unavailable" in format_scan_finished_message(res_unavail, 10, False)  # type: ignore

    # Issues
    res_issues = {"cancelled": False, "available": True, "issues": ["error1", "error2"]}
    assert "2 folder access issue(s)" in format_scan_finished_message(res_issues, 10, False)  # type: ignore

    # Incomplete
    res_incomp = {"cancelled": False, "available": True, "issues": [], "complete": False}
    assert "did not complete" in format_scan_finished_message(res_incomp, 10, False)  # type: ignore

    # Complete & not quiet
    res_comp = {"cancelled": False, "available": True, "issues": [], "complete": True}
    assert (
        format_scan_finished_message(res_comp, 1250, False)
        == "Folder indexing complete: 1,250 audio files."
    )

    # Complete & quiet -> None
    assert format_scan_finished_message(res_comp, 1250, True) is None


def test_scan_coordinator_dirty_tracking() -> None:
    coord = WorkspaceScanCoordinator()

    # Initial state
    assert not coord.has_dirty_roots()
    assert coord.consume_dirty_roots() == set()

    # Global library dirty mark
    coord.mark_dirty_library(None)
    assert coord.has_dirty_roots()
    assert coord.consume_dirty_roots() == {"*"}
    assert not coord.has_dirty_roots()

    all_branches, branches = coord.consume_dirty_branches()
    assert all_branches is True
    assert branches == set()

    # consume_dirty_tabs with all_tabs set
    all_known = {"tab1", "tab2"}
    assert coord.consume_dirty_tabs(all_known) == all_known

    # Specific root and folders
    coord.mark_dirty_library("r1", ["sub1", "sub2"])
    assert coord.consume_dirty_roots() == {"r1"}
    all_b, branches = coord.consume_dirty_branches()
    assert all_b is False
    assert branches == {("r1", "sub1"), ("r1", "sub2")}
    assert coord.consume_dirty_tabs(all_known) == {"folder:r1/sub1", "folder:r1/sub2"}

    # Tabs dirty
    coord.mark_tab_dirty("custom_tab")
    coord.mark_tabs_dirty({"tab_a", "tab_b"})
    assert coord.consume_dirty_tabs(all_known) == {"custom_tab", "tab_a", "tab_b"}


def test_scan_coordinator_scan_lifecycle() -> None:
    coord = WorkspaceScanCoordinator()

    # Start first scan
    prev_job = coord.prepare_scan_request("r1", "req1", quiet=True)
    assert prev_job is None
    coord.record_scan_job("r1", "job1")

    assert coord.is_scan_active("r1")
    assert not coord.is_scan_active("r2")
    assert coord.is_matching_request("r1", "req1")
    assert not coord.is_matching_request("r1", "wrong_req")
    assert coord.is_quiet_request("req1")

    # Record batches
    assert coord.record_scan_batch("r1", 50) == 50
    assert coord.record_scan_batch("r1", 25) == 75

    # Start new scan replacing the old one
    prev_job2 = coord.prepare_scan_request("r1", "req2", quiet=False)
    assert prev_job2 == "job1"
    assert not coord.is_quiet_request("req1")  # discarded from quiet
    assert not coord.is_quiet_request("req2")

    coord.record_scan_job("r1", "job2")
    coord.record_scan_batch("r1", 100)

    # Finish scan
    quiet, count = coord.finish_scan("r1", "req2")
    assert quiet is False
    assert count == 100
    assert not coord.is_scan_active("r1")


def test_scan_coordinator_folder_watch_and_refresh() -> None:
    coord = WorkspaceScanCoordinator()

    norm_path = os.path.normcase(os.path.normpath("C:/music/r1/a"))
    targets = {norm_path: ("r1", "a")}
    active = {("r1", "a")}

    # Update targets
    newly_visible = coord.update_watch_targets(targets, active)
    assert newly_visible == [("r1", "a")]
    assert coord.resolve_watch_target(norm_path) == ("r1", "a")
    assert coord.resolve_watch_target("C:/unwatched") is None

    # Folder refresh
    assert coord.begin_folder_refresh("r1", "a") is True
    coord.record_folder_refresh_job("r1", "a", "job_ref_1")

    # While in flight, next begin marks pending and returns False
    assert coord.begin_folder_refresh("r1", "a") is False

    # Finish with unstable=True
    retry, had_pending = coord.finish_folder_refresh("r1", "a", unstable=True)
    assert retry is True
    assert had_pending is True

    # Finish with unstable=False resets counter
    retry2, had_pending2 = coord.finish_folder_refresh("r1", "a", unstable=False)
    assert retry2 is False
    assert had_pending2 is False


def test_folder_branch_tracker() -> None:
    tracker = FolderBranchTracker()
    folder_id = "folder:r1/album"

    assert not tracker.is_in_flight(folder_id)

    gen = tracker.next_generation(folder_id)
    assert gen == 1
    assert tracker.is_current_generation(folder_id, 1)
    assert not tracker.is_current_generation(folder_id, 0)

    tracker.record_job(folder_id, "job_branch_1")
    assert tracker.is_in_flight(folder_id)

    cancelled_job = tracker.cancel_job(folder_id)
    assert cancelled_job == "job_branch_1"
    assert not tracker.is_in_flight(folder_id)
    assert tracker.is_current_generation(folder_id, 1) is False  # generation bumped

    # Cancel all jobs
    tracker.record_job("f1", "job1")
    tracker.record_job("f2", "job2")
    cancelled_all = tracker.cancel_all_jobs()
    assert set(cancelled_all) == {"job1", "job2"}
    assert not tracker.is_in_flight("f1")
    assert not tracker.is_in_flight("f2")
