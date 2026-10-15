"""Scan coordination, dirty branches/tabs tracking, and folder watching."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mtee.models.workspace_rows import parse_folder_id

__all__ = [
    "FolderBranchTracker",
    "WorkspaceScanCoordinator",
    "compute_folder_watch_targets",
    "format_scan_finished_message",
]


def compute_folder_watch_targets(
    groups: list[dict[str, Any]],
    roots_by_id: dict[str, Any],
) -> tuple[dict[str, tuple[str, str]], list[str], set[tuple[str, str]]]:
    """Compute watch targets mapping, watch paths list, and active folder tabs.

    Args:
        groups: List of workspace split groups containing active tab IDs.
        roots_by_id: Dictionary mapping root_id to root data (containing 'path').

    Returns:
        (targets_by_normcase_path, paths_to_watch, active_folder_tabs)
    """
    active: set[tuple[str, str]] = set()
    for group in groups:
        tab_id = str(group.get("active", ""))
        if not tab_id.startswith("folder:"):
            continue
        try:
            parsed = parse_folder_id(tab_id)
        except ValueError:
            parsed = None
        if parsed is not None:
            active.add(parsed)

    targets: dict[str, tuple[str, str]] = {}
    paths_to_watch: list[str] = []
    for root_id, relative in sorted(active):
        root = roots_by_id.get(root_id)
        if root is not None:
            path = str(Path(str(root["path"])) / relative)
            targets[os.path.normcase(os.path.normpath(path))] = (root_id, relative)
            paths_to_watch.append(path)

    return targets, paths_to_watch, active


def format_scan_finished_message(
    result: dict[str, Any],
    scan_count: int,
    quiet: bool,
) -> str | None:
    """Format user message when a folder indexing scan finishes."""
    if result.get("cancelled"):
        return "Folder indexing cancelled; existing references were kept."
    if not result.get("available", True):
        return "This folder is unavailable. Reconnect it and rescan to continue."
    if result.get("issues"):
        return f"Indexing finished with {len(result['issues'])} folder access issue(s)."
    if not result.get("complete", True):
        return "Indexing did not complete. Existing references were kept; rescan to retry."
    if not quiet:
        return f"Folder indexing complete: {scan_count:,} audio files."
    return None


class WorkspaceScanCoordinator:
    """Coordinates scan requests, folder dirty tracking, and folder watching."""

    def __init__(self) -> None:
        self.dirty_all_branches: bool = False
        self.dirty_root_ids: set[str] = set()
        self.dirty_folder_branches: set[tuple[str, str]] = set()
        self.dirty_tabs: set[str] = set()
        self.dirty_all_tabs: bool = False

        self.requests: dict[str, str] = {}
        self.quiet_requests: set[str] = set()
        self.jobs_by_root: dict[str, str] = {}
        self.scan_counts: dict[str, int] = {}

        self.watch_targets: dict[str, tuple[str, str]] = {}
        self.active_folder_tabs: set[tuple[str, str]] = set()
        self.folder_refresh_jobs: dict[tuple[str, str], str] = {}
        self.folder_refresh_unstable: dict[tuple[str, str], int] = {}
        self.folder_refresh_pending: set[tuple[str, str]] = set()

    # --- Dirty tracking ---

    def mark_tab_dirty(self, tab_id: str) -> None:
        """Mark a single tab as needing reload."""
        self.dirty_tabs.add(tab_id)

    def mark_tabs_dirty(self, tab_ids: set[str] | list[str]) -> None:
        """Mark multiple tabs as needing reload."""
        self.dirty_tabs.update(tab_ids)

    def mark_all_tabs_dirty(self) -> None:
        """Mark all tabs as needing reload."""
        self.dirty_all_tabs = True

    def mark_dirty_library(
        self,
        root_id: str | None = None,
        changed_folders: set[str] | list[str] | None = None,
    ) -> None:
        """Mark library or root/subfolders as dirty."""
        if root_id is None:
            self.dirty_all_branches = True
            self.dirty_all_tabs = True
            self.dirty_root_ids.add("*")
        else:
            self.dirty_root_ids.add(root_id)
            for relative in changed_folders or {""}:
                self.dirty_folder_branches.add((root_id, relative))
                self.dirty_tabs.add(f"folder:{root_id}/{relative}")

    def mark_dirty_batch(self, root_id: str, changed_folders: list[Any]) -> None:
        """Mark dirty folder branches and tabs from a scan batch."""
        for relative in changed_folders:
            folder = str(relative)
            self.dirty_folder_branches.add((root_id, folder))
            self.dirty_tabs.add(f"folder:{root_id}/{folder}")

    def mark_dirty_finished(self, root_id: str, changed_folders: list[Any]) -> None:
        """Mark root and changed folders dirty upon scan completion."""
        self.dirty_root_ids.add(root_id)
        for relative in changed_folders:
            folder = str(relative)
            self.dirty_folder_branches.add((root_id, folder))
            self.dirty_tabs.add(f"folder:{root_id}/{folder}")

    def has_dirty_roots(self) -> bool:
        """Return True if any root IDs need re-requesting."""
        return bool(self.dirty_root_ids)

    def consume_dirty_roots(self) -> set[str]:
        """Consume and clear dirty root IDs."""
        roots = set(self.dirty_root_ids)
        self.dirty_root_ids.clear()
        return roots

    def consume_dirty_branches(self) -> tuple[bool, set[tuple[str, str]]]:
        """Consume and clear dirty branch flags and sets."""
        all_branches = self.dirty_all_branches
        self.dirty_all_branches = False
        branches = self.dirty_folder_branches
        self.dirty_folder_branches = set()
        return all_branches, branches

    def consume_dirty_tabs(self, all_known_tabs: set[str]) -> set[str]:
        """Consume and clear dirty tabs, resolving dirty_all_tabs if set."""
        if self.dirty_all_tabs:
            self.dirty_all_tabs = False
            self.dirty_tabs.clear()
            return set(all_known_tabs)
        tabs = self.dirty_tabs
        self.dirty_tabs = set()
        return tabs

    # --- Scan lifecycle & tracking ---

    def prepare_scan_request(self, root_id: str, request_id: str, *, quiet: bool) -> str | None:
        """Prepare tracking for a new scan request, returning previous job_id to cancel if any."""
        previous_job = self.jobs_by_root.get(root_id)
        if previous_job:
            previous_request = self.requests.get(root_id)
            if previous_request is not None:
                self.quiet_requests.discard(previous_request)
        self.requests[root_id] = request_id
        if quiet:
            self.quiet_requests.add(request_id)
        self.scan_counts[root_id] = 0
        return previous_job

    def record_scan_job(self, root_id: str, job_id: str) -> None:
        """Associate a root scan with its submitted JobId."""
        self.jobs_by_root[root_id] = job_id

    def is_scan_active(self, root_id: str) -> bool:
        """Return True if a scan job is currently active for root_id."""
        return root_id in self.jobs_by_root

    def is_matching_request(self, root_id: str, request_id: str) -> bool:
        """Return True if request_id matches the active scan request for root_id."""
        return self.requests.get(root_id) == request_id

    def is_quiet_request(self, request_id: str) -> bool:
        """Return True if request_id was launched in quiet mode."""
        return request_id in self.quiet_requests

    def record_scan_batch(self, root_id: str, count: int) -> int:
        """Record batch count and return updated total for root_id."""
        total = self.scan_counts.get(root_id, 0) + count
        self.scan_counts[root_id] = total
        return total

    def finish_scan(self, root_id: str, request_id: str) -> tuple[bool, int]:
        """Clean up scan tracking upon completion, returning (quiet, scan_count)."""
        self.requests.pop(root_id, None)
        quiet = request_id in self.quiet_requests
        self.quiet_requests.discard(request_id)
        self.jobs_by_root.pop(root_id, None)
        scan_count = self.scan_counts.get(root_id, 0)
        return quiet, scan_count

    # --- Folder watching and single-folder refresh ---

    def update_watch_targets(
        self, targets: dict[str, tuple[str, str]], active: set[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """Update watch targets and active tabs, returning newly visible folders."""
        self.watch_targets = targets
        newly_visible = sorted(active - self.active_folder_tabs)
        self.active_folder_tabs = set(active)
        return newly_visible

    def resolve_watch_target(self, path: str) -> tuple[str, str] | None:
        """Resolve a filesystem change path to (root_id, relative) if watched."""
        return self.watch_targets.get(os.path.normcase(os.path.normpath(path)))

    def begin_folder_refresh(self, root_id: str, relative: str) -> bool:
        """Check if folder refresh can proceed.

        If already in flight, mark pending and return False.
        """
        key = (root_id, relative)
        if key in self.folder_refresh_jobs:
            self.folder_refresh_pending.add(key)
            return False
        return True

    def record_folder_refresh_job(self, root_id: str, relative: str, job_id: str) -> None:
        """Record job ID for active folder refresh."""
        self.folder_refresh_jobs[(root_id, relative)] = job_id

    def finish_folder_refresh(
        self, root_id: str, relative: str, *, unstable: bool
    ) -> tuple[bool, bool]:
        """Finish folder refresh and return (should_retry_unstable, had_pending)."""
        key = (root_id, relative)
        self.folder_refresh_jobs.pop(key, None)
        should_retry = False
        if unstable:
            retries = self.folder_refresh_unstable.get(key, 0)
            if retries < 15:
                self.folder_refresh_unstable[key] = retries + 1
                should_retry = True
        else:
            self.folder_refresh_unstable.pop(key, None)

        had_pending = key in self.folder_refresh_pending
        if had_pending:
            self.folder_refresh_pending.discard(key)

        return should_retry, had_pending


class FolderBranchTracker:
    """Tracks generation numbers and active job IDs for tree branch expansions."""

    def __init__(self) -> None:
        self.generations: dict[str, int] = {}
        self.job_ids: dict[str, str] = {}

    def is_in_flight(self, folder_id: str) -> bool:
        """Return True if a branch load job is currently running for folder_id."""
        return folder_id in self.job_ids

    def next_generation(self, folder_id: str) -> int:
        """Bump and return the generation number for folder_id."""
        generation = self.generations.get(folder_id, 0) + 1
        self.generations[folder_id] = generation
        return generation

    def record_job(self, folder_id: str, job_id: str) -> None:
        """Record active JobId for folder_id."""
        self.job_ids[folder_id] = job_id

    def is_current_generation(self, folder_id: str, generation: int) -> bool:
        """Return True if generation matches the current generation for folder_id."""
        return self.generations.get(folder_id) == generation

    def finish_job(self, folder_id: str) -> None:
        """Pop active job ID for folder_id when completed."""
        self.job_ids.pop(folder_id, None)

    def cancel_job(self, folder_id: str) -> str | None:
        """Bump generation and pop active job ID if any, returning it for cancellation."""
        self.generations[folder_id] = self.generations.get(folder_id, 0) + 1
        return self.job_ids.pop(folder_id, None)

    def cancel_all_jobs(self) -> list[str]:
        """Bump generation for all branches and return all active job IDs for cancellation."""
        jobs: list[str] = []
        for folder_id, job_id in tuple(self.job_ids.items()):
            self.generations[folder_id] = self.generations.get(folder_id, 0) + 1
            if job_id:
                jobs.append(job_id)
        self.job_ids.clear()
        return jobs
