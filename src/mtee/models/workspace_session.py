from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from mtee.domain.artist_index import ARTIST_SORT_KEYS, DEFAULT_ARTIST_SORT
from mtee.domain.column_widths import clamp_column_width
from mtee.models import window_layout as layout
from mtee.models.window_layout import Leaf, Node, Split, node_from_dict
from mtee.models.workspace_rows import copy_column_preferences, parse_folder_ref
from mtee.persistence.workspace_repository import (
    COLUMN_OPTIONS,
    DEFAULT_COLUMN_PREFERENCES,
    RESTORED_TAB_KINDS,
)

__all__ = [
    "COLUMN_KEYS",
    "WorkspaceSessionWriter",
    "build_session_snapshot",
    "ensure_tab_state",
    "extract_view_fields",
    "keeps_order",
    "restore_session_groups",
    "set_default_sort",
]

COLUMN_KEYS = {key for key, _label in COLUMN_OPTIONS}


def keeps_order(kind: object) -> bool:
    """Whether a tab of this kind lists its rows in their own order by default.

    A playlist and an artist page do; so does a tab kind of a plugin, whose name has a dot.
    """
    return kind in {"playlist", "artist"} or (isinstance(kind, str) and "." in kind)


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
    state["sortKey"] = "index" if keeps_order(kind) else "fileCreatedAt"
    state["sortAscending"] = keeps_order(kind)


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
                "sortKey": "index" if keeps_order(kind) else "fileCreatedAt",
                "sortAscending": keeps_order(kind),
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
            widths[key] = 0 if key == "title" and value <= 0 else clamp_column_width(key, value)
    state["columnWidths"] = widths
    if state.get("sortMode") not in {"default", "manual"}:
        state["sortMode"] = "manual"
    return state


def restore_session_groups(
    raw_groups: list[Any],
    roots_by_id: dict[str, dict[str, Any]] | None = None,
    center: Any = None,
) -> tuple[dict[str, dict[str, Any]], Node, dict[str, dict[str, Any]], int]:
    """Restore the groups and the center layout from session data.

    Each saved group keeps its ``id`` when it is a unique, non-empty string; otherwise it gets
    the next free id. The saved ``center`` tree is used when it places exactly these groups;
    otherwise the groups sit side by side, or one window is shown when there is one group.

    Returns:
        (groups, layout, tab_states, next_group_number): groups keyed by id, the layout tree,
        the tab states, and the number the next new group id takes.
    """
    tab_states: dict[str, dict[str, Any]] = {}
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    counter = 0
    for raw_group in raw_groups:
        if not isinstance(raw_group, dict):
            continue
        tab_ids: list[str] = []
        for raw_tab in raw_group.get("tabs", []):
            if not isinstance(raw_tab, dict) or raw_tab.get("kind") not in RESTORED_TAB_KINDS:
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
        counter += 1
        saved_id = raw_group.get("id")
        group_id = (
            saved_id
            if isinstance(saved_id, str) and saved_id and saved_id not in groups
            else f"g{counter}"
        )
        while group_id in groups:
            counter += 1
            group_id = f"g{counter}"
        groups[group_id] = {"tabs": tab_ids, "active": active, "selections": selections}
        order.append(group_id)
    if not groups:
        groups = {"g1": {"tabs": [], "active": "", "selections": {}}}
        order = ["g1"]
        counter = 1
    return groups, restore_layout(center, order), tab_states, counter + 1


def restore_layout(center: Any, group_ids: list[str]) -> Node:
    """The saved tree when it places exactly ``group_ids``; else a default arrangement."""
    if center is not None:
        tree = node_from_dict(center)
        if set(layout.groups(tree)) == set(group_ids) and len(layout.groups(tree)) == len(
            group_ids
        ):
            return tree
    if len(group_ids) == 1:
        return Leaf(group_ids[0])
    if len(group_ids) == 2:
        return Split("row", (Leaf(group_ids[0]), Leaf(group_ids[1])), (0.5, 0.5))
    tree: Node = Leaf(group_ids[0])
    for group_id in group_ids[1:]:
        tree = layout.split(tree, layout.groups(tree)[-1], "right", group_id)
    return tree


def build_session_snapshot(
    *,
    expanded: set[str] | list[str],
    groups: Mapping[str, dict[str, Any]],
    layout_tree: Node,
    tab_states: dict[str, dict[str, Any]],
    selection_by_tab: dict[tuple[str, str], list[str]],
    anchor_by_tab: dict[tuple[str, str], str],
    active_group: str,
    activity: str,
    sidebar_visible: bool,
    right_visible: bool,
    right_tab: str,
    sidebar_width: int,
    right_panel_width: int,
    preview_tabs: bool,
    column_preferences: dict[str, Any],
    next_group: int = 1,
    artist_sort: str = DEFAULT_ARTIST_SORT,
    docks: Mapping[str, layout.DockState] | None = None,
    window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce the complete serializable dictionary representing the workspace session (v2).

    ``docks`` holds both docks as they are (open, width, both tool windows, split); without it
    each dock is rebuilt from the sizes and the first window. ``window`` is the main window's
    geometry.
    """
    order = list(layout.groups(layout_tree))
    saved_docks = (
        {side: dock.to_dict() for side, dock in docks.items()}
        if docks is not None
        else {
            "left": layout.DockState("left", sidebar_visible, sidebar_width, (activity,)).to_dict(),
            "right": layout.DockState(
                "right", right_visible, right_panel_width, (right_tab,)
            ).to_dict(),
        }
    )
    return {
        "version": 2,
        "expanded": sorted(expanded),
        "groups": [
            {
                "id": group_id,
                "tabs": [
                    dict(tab_states.get(tab_id, {})) for tab_id in groups[group_id].get("tabs", [])
                ],
                "active": groups[group_id].get("active", ""),
                "selections": {
                    tab_id: {
                        "ids": list(selection_by_tab.get((group_id, tab_id), [])),
                        "anchor": anchor_by_tab.get((group_id, tab_id), ""),
                    }
                    for tab_id in groups[group_id].get("tabs", [])
                },
            }
            for group_id in order
        ],
        "center": layout.node_to_dict(layout_tree),
        "activeGroup": active_group if active_group in order else order[0],
        "nextGroup": max(next_group, 1),
        "docks": saved_docks,
        "window": dict(window) if window else None,
        "previewTabs": preview_tabs,
        "columnPreferences": copy_column_preferences(column_preferences),
        "artistSort": artist_sort if artist_sort in ARTIST_SORT_KEYS else DEFAULT_ARTIST_SORT,
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
