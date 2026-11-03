"""Checks of what a plugin contributes to the interface, before the core draws any of it.

A broken contribution makes the plugin ``Failed`` as a whole, so the user never sees half of
a plugin. The checks cover what the core relies on: identifiers, their uniqueness, the tab
kind names, the QML files that exist, and the activity a section belongs to.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QAbstractItemModel

from mtee.plugins.api import (
    Contribution,
    DeleteChoices,
    LibraryScanned,
    PaneAction,
    PlaylistMeta,
    PluginActivity,
    PluginDialog,
    SettingsPage,
    SidebarSection,
    StartupTask,
    StatusItem,
    TabAction,
    TabKind,
    TrackAction,
    TrackAvailability,
    TrackColumn,
    TrackSource,
    WaitingItems,
)

__all__ = ["CORE_ACTIVITIES", "SECTION_ACTIVITIES", "check_contributions", "is_identifier"]

# The activities of the core. A plugin activity may not take one of these names.
CORE_ACTIVITIES = frozenset({"explorer", "playlists", "convert", "tasks", "artists", "plugins"})
# The core activities whose sidebar lists the sections of plugins.
SECTION_ACTIVITIES = frozenset({"explorer", "playlists"})
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
# The widths a PluginDialog may ask for, in pixels (inclusive).
DIALOG_WIDTH_RANGE = (320, 640)


def is_identifier(value: object) -> bool:
    """Return whether ``value`` is a lowercase snake_case identifier."""
    return isinstance(value, str) and _IDENTIFIER.match(value) is not None


def check_contributions(plugin_id: str, contributions: Sequence[Contribution]) -> None:
    """Raise ``ValueError`` with a readable reason when a contribution cannot be used."""
    activities = [item for item in contributions if isinstance(item, PluginActivity)]
    kinds = [item for item in contributions if isinstance(item, TabKind)]
    for activity in activities:
        _check_activity(activity)
    _unique("activity", [item.activity_id for item in activities])
    for kind in kinds:
        _check_tab_kind(plugin_id, kind)
    _unique("tab kind", [item.kind for item in kinds])
    own_kinds = {item.kind for item in kinds}
    own_activities = {item.activity_id for item in activities}
    sections = [item for item in contributions if isinstance(item, SidebarSection)]
    for section in sections:
        _check_section(section, own_activities)
    _unique("sidebar section", [item.section_id for item in sections])
    tab_actions = [item for item in contributions if isinstance(item, TabAction)]
    for tab_action in tab_actions:
        _check_tab_action(tab_action, own_kinds)
    _unique("tab action", [f"{item.tab_kind}.{item.action_id}" for item in tab_actions])
    columns = [item for item in contributions if isinstance(item, TrackColumn)]
    for column in columns:
        _check_column(column)
    _unique("track column", [item.column_id for item in columns])
    actions = [item for item in contributions if isinstance(item, TrackAction)]
    for action in actions:
        _check_track_action(action)
    _unique("track action", [item.action_id for item in actions])
    pages = [item for item in contributions if isinstance(item, SettingsPage)]
    for page in pages:
        _check_page(page)
    _unique("settings page", [item.page_id for item in pages])
    tasks = [item for item in contributions if isinstance(item, StartupTask)]
    for task in tasks:
        _need_identifier("startup task", task.task_id)
        _need_callable("startup task", task.task_id, task.run)
    _unique("startup task", [item.task_id for item in tasks])
    waiting = [item for item in contributions if isinstance(item, WaitingItems)]
    for group in waiting:
        _check_waiting(group)
    _unique("waiting group", [item.section_id for item in waiting])
    dialogs = [item for item in contributions if isinstance(item, PluginDialog)]
    for dialog in dialogs:
        _check_dialog(dialog)
    _unique("dialog", [item.dialog_id for item in dialogs])
    status_items = [item for item in contributions if isinstance(item, StatusItem)]
    for status in status_items:
        _check_status_item(status)
    if len(status_items) > 1:
        raise ValueError("A plugin declares at most one status item.")
    for meta in (item for item in contributions if isinstance(item, PlaylistMeta)):
        _need_callable("playlist meta", "text", meta.text)
    for hook in (item for item in contributions if isinstance(item, LibraryScanned)):
        _need_callable("library scan hook", "callback", hook.callback)
    track_sources = [item for item in contributions if isinstance(item, TrackSource)]
    if len(track_sources) > 1:
        raise ValueError("A plugin declares at most one track source.")
    for source in track_sources:
        _need_callable("track source", "open", source.open)
        if source.cover is not None:
            _need_callable("track source", "cover", source.cover)
    delete_choices = [item for item in contributions if isinstance(item, DeleteChoices)]
    for choices in delete_choices:
        _need_callable("delete choices", "offer", choices.offer)
        _need_callable("delete choices", "run", choices.run)
    if len(delete_choices) > 1:
        raise ValueError("A plugin declares DeleteChoices once; this one declares it twice.")
    availabilities = [item for item in contributions if isinstance(item, TrackAvailability)]
    for availability in availabilities:
        _need_callable("track availability", "status", availability.status)
    if len(availabilities) > 1:
        raise ValueError("A plugin declares TrackAvailability at most once.")


def _check_activity(activity: PluginActivity) -> None:
    _need_identifier("activity", activity.activity_id)
    if activity.activity_id in CORE_ACTIVITIES:
        raise ValueError(f"The activity name {activity.activity_id!r} is used by MTEE itself.")
    _need_text("activity", activity.activity_id, activity.title, "title")
    _need_text("activity", activity.activity_id, activity.icon, "icon")
    for action in activity.actions:
        _check_pane_action(action)
    if activity.foot is not None and not isinstance(activity.foot, QAbstractItemModel):
        raise ValueError(f"The foot of activity {activity.activity_id} is not a Qt model.")
    if activity.badge is not None:
        _need_callable("activity badge", activity.activity_id, activity.badge)


def _check_pane_action(action: PaneAction) -> None:
    _need_identifier("pane action", action.action_id)
    _need_callable("pane action", action.action_id, action.run)
    if not isinstance(action.label, str):
        raise ValueError(f"The pane action {action.action_id} has a label that is not text.")
    if action.visible is not None:
        _need_callable("pane action visibility", action.action_id, action.visible)


def _check_section(section: SidebarSection, own_activities: set[str]) -> None:
    _need_identifier("sidebar section", section.section_id)
    _need_text("sidebar section", section.section_id, section.title, "title")
    if section.activity not in SECTION_ACTIVITIES and section.activity not in own_activities:
        raise ValueError(
            f"The section {section.section_id} names the activity {section.activity!r}, "
            "which is neither Explorer, Playlists nor an activity of this plugin."
        )
    if not isinstance(section.model, QAbstractItemModel):
        raise ValueError(f"The model of section {section.section_id} is not a Qt model.")
    for action in section.actions:
        _check_pane_action(action)
    if section.activate is not None:
        _need_callable("sidebar section", section.section_id, section.activate)
    if section.on_fold is not None:
        _need_callable("sidebar section", section.section_id, section.on_fold)
    if section.count is not None:
        _need_callable("section count", section.section_id, section.count)
    if not isinstance(section.expanded, bool) and not callable(section.expanded):
        raise ValueError(
            f"The section {section.section_id} has an expanded value that is neither a bool "
            "nor a function."
        )


def _check_waiting(group: WaitingItems) -> None:
    _need_identifier("waiting group", group.section_id)
    _need_text("waiting group", group.section_id, group.title, "title")
    if not isinstance(group.model, QAbstractItemModel):
        raise ValueError(f"The model of waiting group {group.section_id} is not a Qt model.")
    _need_callable("waiting group", group.section_id, group.run)
    _need_callable("waiting group", group.section_id, group.dismiss)


def _check_tab_kind(plugin_id: str, kind: TabKind) -> None:
    prefix, _, name = kind.kind.partition(".")
    if prefix != plugin_id or not is_identifier(name):
        raise ValueError(f"The tab kind {kind.kind!r} must be written {plugin_id}.<name>.")
    _need_callable("tab kind", kind.kind, kind.title_fn)
    if isinstance(kind.content, Path):
        if not kind.content.is_file():
            raise ValueError(f"The QML file of tab kind {kind.kind} does not exist: {kind.content}")
    else:
        _need_callable("tab kind", kind.kind, kind.content)


def _check_tab_action(action: TabAction, own_kinds: set[str]) -> None:
    _need_identifier("tab action", action.action_id)
    if action.tab_kind != "playlist" and action.tab_kind not in own_kinds:
        raise ValueError(
            f"The tab action {action.action_id} is for {action.tab_kind!r}, which is neither "
            "playlist nor a tab kind of this plugin."
        )
    _need_callable("tab action", action.action_id, action.run)
    if action.disabled_reason is not None:
        _need_callable("tab action", action.action_id, action.disabled_reason)
    if action.kind not in ("primary", "neutral", "ghost", "toggle"):
        raise ValueError(f"The tab action {action.action_id} has an unknown kind {action.kind!r}.")


def _check_column(column: TrackColumn) -> None:
    _need_identifier("track column", column.column_id)
    _need_text("track column", column.column_id, column.title, "title")
    _need_callable("track column", column.column_id, column.value_fn)


def _check_track_action(action: TrackAction) -> None:
    _need_identifier("track action", action.action_id)
    _need_text("track action", action.action_id, action.label, "label")
    _need_text("track action", action.action_id, action.group, "group")
    _need_callable("track action", action.action_id, action.run)


def _check_page(page: SettingsPage) -> None:
    _need_identifier("settings page", page.page_id)
    _need_text("settings page", page.page_id, page.label, "label")
    if not page.content.is_file():
        raise ValueError(f"The QML file of settings page {page.page_id} does not exist.")


def _check_dialog(dialog: PluginDialog) -> None:
    _need_identifier("dialog", dialog.dialog_id)
    if not dialog.content.is_file():
        raise ValueError(f"The QML file of dialog {dialog.dialog_id} does not exist.")
    width = dialog.width
    lowest, highest = DIALOG_WIDTH_RANGE
    whole = isinstance(width, int) and not isinstance(width, bool)
    if not whole or not lowest <= width <= highest:
        raise ValueError(
            f"The width of dialog {dialog.dialog_id} must be a whole number of pixels from "
            f"{lowest} to {highest}, not {width!r}."
        )


def _check_status_item(status: StatusItem) -> None:
    _need_identifier("status item", status.item_id)
    _need_text("status item", status.item_id, status.icon, "icon")
    if status.on_click is not None:
        _need_callable("status item", status.item_id, status.on_click)


def _need_identifier(what: str, value: object) -> None:
    if not is_identifier(value):
        raise ValueError(f"The {what} identifier {value!r} must be lowercase snake_case.")


def _need_text(what: str, identifier: str, value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"The {what} {identifier} has no {field}.")


def _need_callable(what: str, identifier: str, value: object) -> None:
    if not callable(value):
        raise ValueError(f"The {what} {identifier} needs a function that is not callable.")


def _unique(what: str, identifiers: list[str]) -> None:
    seen: set[str] = set()
    for identifier in identifiers:
        if identifier in seen:
            raise ValueError(f"The {what} {identifier!r} is declared twice.")
        seen.add(identifier)
