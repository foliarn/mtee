from __future__ import annotations

import sqlite3
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from mtee.models.workspace_rows import copy_column_preferences, parse_folder_ref
from mtee.persistence.workspace_repository import (
    COLUMN_OPTIONS,
    DEFAULT_COLUMN_PREFERENCES,
)

__all__ = [
    "COLUMN_KEYS",
    "WorkspaceSessionWriter",
    "build_session_snapshot",
    "ensure_tab_state",
    "extract_view_fields",
    "restore_session_groups",
    "set_default_sort",
]

COLUMN_KEYS = {key for key, _label in COLUMN_OPTIONS}


def extract_view_fields(tab: dict[str, Any]) -> dict[str, Any]:
    """Extract view-related fields from a tab state dictionary."""
    return {
        key: tab[key]
        for key in ("searchQuery", "sortKey", "sortAscending", "sortMode", "view")
        if key in tab
    }


def set_default_sort(state: dict[str, Any]) -> None:
    """Set the default sort mode, key and direction based on tab kind."""
    state["sortMode"] = "default"
    kind = state.get("kind")
    state["sortKey"] = "index" if kind in {"playlist", "artist"} else "fileCreatedAt"
    state["sortAscending"] = kind in {"playlist", "artist"}


def ensure_tab_state(
    tab_id: str,
    tab_states: dict[str, dict[str, Any]],
    roots_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ensure a tab state dictionary exists and contains all required defaults."""
    state = tab_states.setdefault(tab_id, {})
    if not state:
        kind, _, ref = tab_id.partition(":")
        title = {
            "settings": "Settings",
            "profile": "Profile",
            "convert": "Convert",
            "tasks": "Tasks",
        }.get(kind, "Folder")
        if kind == "folder":
            try:
                root_id, relative = parse_folder_ref(ref)
                root = (roots_by_id or {}).get(root_id, {})
                title = relative.rsplit("/", 1)[-1] if relative else str(root.get("name", "Folder"))
            except (ValueError, StopIteration):
                pass
        state.update(
            {
                "id": tab_id,
                "kind": kind,
                "ref": ref,
                "title": title,
                "sortMode": "default",
                # A playlist keeps its order; an artist page is in album and track order.
                "sortKey": "index" if kind in {"playlist", "artist"} else "fileCreatedAt",
                "sortAscending": kind in {"playlist", "artist"},
                "view": "list",
                "searchQuery": "",
                "selectedIds": [],
                "selectionAnchor": "",
            }
        )
    column_order = state.get("columnOrder", DEFAULT_COLUMN_PREFERENCES["order"])
    if not isinstance(column_order, list):
        column_order = list(DEFAULT_COLUMN_PREFERENCES["order"])
    valid_order = [key for key in column_order if isinstance(key, str) and key in COLUMN_KEYS]
    state["columnOrder"] = list(dict.fromkeys(valid_order + DEFAULT_COLUMN_PREFERENCES["order"]))
    hidden = state.get("hiddenColumns", DEFAULT_COLUMN_PREFERENCES["hidden"])
    state["hiddenColumns"] = (
        [key for key in hidden if isinstance(key, str) and key in COLUMN_KEYS]
        if isinstance(hidden, list)
        else list(DEFAULT_COLUMN_PREFERENCES["hidden"])
    )
    widths = dict(DEFAULT_COLUMN_PREFERENCES["widths"])
    saved_widths = state.get("columnWidths", {})
    if isinstance(saved_widths, dict):
        for key in COLUMN_KEYS:
            try:
                value = int(saved_widths.get(key, widths[key]))
            except (TypeError, ValueError, OverflowError):
                continue
            widths[key] = 0 if key == "title" and value <= 0 else min(max(value, 44), 640)
    state["columnWidths"] = widths
    if state.get("sortMode") not in {"default", "manual"}:
        state["sortMode"] = "manual"
    return state


def restore_session_groups(
    raw_groups: list[Any],
    roots_by_id: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Restore up to 2 groups from session data, initializing their tab states.

    Returns:
        (groups, tab_states): the validated groups list and the tab states dictionary.
    """
    tab_states: dict[str, dict[str, Any]] = {}
    groups: list[dict[str, Any]] = []
    for raw_group in raw_groups[:2]:
        if not isinstance(raw_group, dict):
            continue
        tab_ids: list[str] = []
        for raw_tab in raw_group.get("tabs", []):
            if not isinstance(raw_tab, dict) or raw_tab.get("kind") not in {
                "folder",
                "playlist",
            }:
                continue
            ref = str(raw_tab.get("ref", ""))
            if raw_tab.get("kind") == "folder":
                try:
                    parse_folder_ref(ref)
                except ValueError:
                    continue
            tab_id = str(raw_tab.get("id", f"folder:{ref}"))
            tab_states[tab_id] = dict(raw_tab)
            if raw_tab.get("kind") == "folder":
                set_default_sort(tab_states[tab_id])
            ensure_tab_state(tab_id, tab_states, roots_by_id)
            tab_ids.append(tab_id)
        active = str(raw_group.get("active", ""))
        if active not in tab_ids:
            active = tab_ids[0] if tab_ids else ""
        selections = raw_group.get("selections", {})
        if not isinstance(selections, dict):
            selections = {}
        groups.append({"tabs": tab_ids, "active": active, "selections": selections})
    if not groups:
        groups = [{"tabs": [], "active": "", "selections": {}}]
    return groups, tab_states


def build_session_snapshot(
    *,
    expanded: set[str] | list[str],
    groups: list[dict[str, Any]],
    tab_states: dict[str, dict[str, Any]],
    selection_by_tab: dict[tuple[int, str], list[str]],
    anchor_by_tab: dict[tuple[int, str], str],
    active_group: int,
    activity: str,
    sidebar_visible: bool,
    right_visible: bool,
    right_tab: str,
    sidebar_width: int,
    right_panel_width: int,
    island_enabled: bool,
    preview_tabs: bool,
    column_preferences: dict[str, Any],
) -> dict[str, Any]:
    """Produce the complete serializable dictionary representing the workspace session."""
    return {
        "version": 1,
        "expanded": sorted(expanded),
        "groups": [
            {
                "tabs": [dict(tab_states.get(tab_id, {})) for tab_id in group.get("tabs", [])],
                "active": group.get("active", ""),
                "selections": {
                    tab_id: {
                        "ids": list(selection_by_tab.get((group_index, tab_id), [])),
                        "anchor": anchor_by_tab.get((group_index, tab_id), ""),
                    }
                    for tab_id in group.get("tabs", [])
                },
            }
            for group_index, group in enumerate(groups)
        ],
        "activeGroup": active_group,
        "activity": activity,
        "sidebarVisible": sidebar_visible,
        "rightPanelVisible": right_visible,
        "rightPanelTab": right_tab,
        "sidebarWidth": sidebar_width,
        "rightPanelWidth": right_panel_width,
        "islandEnabled": island_enabled,
        "previewTabs": preview_tabs,
        "columnPreferences": copy_column_preferences(column_preferences),
    }


class WorkspaceSessionWriter:
    """Coordinates asynchronous persistence of workspace session snapshots."""

    def __init__(
        self,
        save_fn: Callable[[dict[str, Any]], None],
        on_write_finished: Callable[[Future[None], BaseException | None], None] | None = None,
        max_workers: int = 1,
        thread_name_prefix: str = "mtee-session",
    ) -> None:
        self._save_fn = save_fn
        self._on_write_finished = on_write_finished
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix=thread_name_prefix
        )
        self._future: Future[None] | None = None
        self._pending: dict[str, Any] | None = None
        self._closed: bool = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def has_pending(self) -> bool:
        return self._pending is not None

    @property
    def is_writing(self) -> bool:
        return self._future is not None

    @property
    def future(self) -> Future[None] | None:
        return self._future

    def write_pending(self, state: dict[str, Any]) -> None:
        """Schedule writing this state snapshot; buffers if a write is already in flight."""
        if self._closed:
            return
        if self._future is not None:
            self._pending = state
            return
        self._submit(state)

    def _submit(self, state: dict[str, Any]) -> None:
        future = self._executor.submit(self._save_fn, state)
        self._future = future

        def completed(done: Future[None]) -> None:
            error: BaseException | None = None
            try:
                error = done.exception()
            except Exception as caught:
                error = caught
            if self._on_write_finished is not None:
                self._on_write_finished(done, error)

        future.add_done_callback(completed)

    def handle_write_finished(
        self, future: object, error: object
    ) -> tuple[bool, BaseException | None]:
        """Handle completion of a write job.

        Returns:
            (is_matching_job, exception_if_any)
        """
        if future is not self._future:
            return False, None
        self._future = None
        exc: BaseException | None = (
            error
            if isinstance(error, BaseException)
            else RuntimeError(str(error))
            if error is not None
            else None
        )
        pending = self._pending
        self._pending = None
        if pending is not None and not self._closed:
            self._submit(pending)
        return True, exc

    def flush(self, state: dict[str, Any]) -> BaseException | None:
        """Persist the latest state synchronously, waiting for in-flight writes, and shut down."""
        if self._closed:
            return None
        self._closed = True
        self._pending = None
        current = self._future
        error: BaseException | None = None
        try:
            if current is not None:
                current.result()
            self._future = None
            self._executor.submit(self._save_fn, state).result()
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as caught:
            error = caught
        finally:
            self._executor.shutdown(wait=True)
        return error
