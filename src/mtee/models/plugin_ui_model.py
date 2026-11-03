"""What the running plugins add to the interface, as the QML reads it.

``PluginUiModel`` holds the contributions of the plugins that run (activities, sidebar
sections, tab kinds, header buttons, columns, menu actions, Settings pages) and answers the
questions of the QML. It runs the plugin's functions inside a guard: a function that raises is
logged, announced once on the message line, and counts as "nothing to show" for that call.
With no plugin running every list is empty and the interface is the one of the core.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QAbstractItemModel, QObject, QUrl, Signal, Slot

from mtee.domain.recycling import RecycleOutcome
from mtee.domain.source_tracks import is_non_file_row, row_is_available
from mtee.models.plugin_columns import (
    PluginColumnStore,
    RegisteredColumn,
    column_options,
    decorate_rows,
    effective_hidden,
    toggled_columns,
)
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import (
    DeleteChoice,
    DeleteChoices,
    DeleteRequest,
    JobContext,
    LibraryScanned,
    PaneAction,
    PlaylistMeta,
    PluginActivity,
    PluginDialog,
    SettingsPage,
    SidebarSection,
    TabAction,
    TabHeader,
    TabKind,
    TrackAction,
    TrackColumn,
    TrackListRow,
    WaitingItems,
)
from mtee.plugins.loader import LoadedPlugin, PluginStatus

__all__ = ["PluginUiModel"]

_LOGGER = logging.getLogger(__name__)
SETTINGS_PAGE_PREFIX = "plugin:"


@dataclass(frozen=True, slots=True)
class _Owned[T]:
    """A contribution with the plugin that made it."""

    plugin_id: str
    plugin_title: str
    item: T


class PluginUiModel(QObject):
    """The contributions of the running plugins; empty until ``register`` is called."""

    changed = Signal()
    tabRequested = Signal(str, str)
    refreshRequested = Signal()
    noticeRaised = Signal(str)
    waitingChanged = Signal()
    dialogRequested = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._activities: dict[str, _Owned[PluginActivity]] = {}
        self._sections: dict[str, _Owned[SidebarSection]] = {}
        self._kinds: dict[str, _Owned[TabKind]] = {}
        self._tab_actions: list[_Owned[TabAction]] = []
        self._columns: list[RegisteredColumn] = []
        self._track_actions: dict[str, _Owned[TrackAction]] = {}
        self._pages: dict[str, _Owned[SettingsPage]] = {}
        self._scan_hooks: list[_Owned[LibraryScanned]] = []
        self._playlist_meta: list[_Owned[PlaylistMeta]] = []
        self._waiting: dict[str, _Owned[WaitingItems]] = {}
        self._dialogs: dict[str, _Owned[PluginDialog]] = {}
        self._delete_choices: dict[str, _Owned[DeleteChoices]] = {}
        self._waiting_count = 0
        self._columns_store = PluginColumnStore(None)
        self._revision = 0
        self._reported: set[str] = set()

    # ------------------------------------------------------------------ registration

    def register(
        self, plugins: Sequence[LoadedPlugin], settings: SettingsRepository | None = None
    ) -> None:
        """Take the contributions of the plugins that run; the others contribute nothing."""
        self._columns_store = PluginColumnStore(settings)
        for record in plugins:
            if record.status is not PluginStatus.RUNNING:
                continue
            plugin_id, title = record.plugin_id, record.title
            for item in record.contributions:
                if isinstance(item, PluginActivity):
                    self._activities[f"{plugin_id}.{item.activity_id}"] = _Owned(
                        plugin_id, title, item
                    )
                elif isinstance(item, SidebarSection):
                    self._sections[f"{plugin_id}.{item.section_id}"] = _Owned(
                        plugin_id, title, item
                    )
                elif isinstance(item, TabKind):
                    self._kinds[item.kind] = _Owned(plugin_id, title, item)
                    self._adopt(item.backend)
                elif isinstance(item, TabAction):
                    self._tab_actions.append(_Owned(plugin_id, title, item))
                elif isinstance(item, TrackColumn):
                    self._columns.append(
                        RegisteredColumn(f"{plugin_id}.{item.column_id}", plugin_id, title, item)
                    )
                elif isinstance(item, TrackAction):
                    self._track_actions[f"{plugin_id}.{item.action_id}"] = _Owned(
                        plugin_id, title, item
                    )
                elif isinstance(item, WaitingItems):
                    self._waiting[f"{plugin_id}.{item.section_id}"] = _Owned(plugin_id, title, item)
                elif isinstance(item, LibraryScanned):
                    self._scan_hooks.append(_Owned(plugin_id, title, item))
                elif isinstance(item, PlaylistMeta):
                    self._playlist_meta.append(_Owned(plugin_id, title, item))
                elif isinstance(item, DeleteChoices):
                    self._delete_choices[plugin_id] = _Owned(plugin_id, title, item)
                elif isinstance(item, PluginDialog):
                    self._dialogs[f"{plugin_id}.{item.dialog_id}"] = _Owned(plugin_id, title, item)
                    self._adopt(item.backend)
                elif isinstance(item, SettingsPage):
                    self._pages[f"{SETTINGS_PAGE_PREFIX}{plugin_id}.{item.page_id}"] = _Owned(
                        plugin_id, title, item
                    )
                    self._adopt(item.backend)
        for section in self._sections.values():
            self._adopt(section.item.model)
        for activity in self._activities.values():
            self._adopt(activity.item.foot)
        for group in self._waiting.values():
            self._adopt(group.item.model)
            self._watch_waiting(group.item.model)
        self._update_waiting()
        self._revision += 1
        self.changed.emit()

    def _adopt(self, model: QObject | None) -> None:
        """Give a plugin object to this model, so the QML never takes ownership of it."""
        if model is not None and model.parent() is None:
            model.setParent(self)

    @Property(int, notify=changed)
    def revision(self) -> int:
        return self._revision

    @Property(bool, notify=changed)
    def active(self) -> bool:
        """Whether any plugin contributes to the interface."""
        return bool(
            self._activities
            or self._sections
            or self._kinds
            or self._tab_actions
            or self._columns
            or self._track_actions
            or self._pages
            or self._waiting
        )

    @Slot()
    def refresh(self) -> None:
        """The data of a plugin changed: header buttons are read again and open lists reload."""
        self._revision += 1
        self.changed.emit()
        self.refreshRequested.emit()

    # ------------------------------------------------------------------ activities

    @Property(list, notify=changed)
    def activities(self) -> list[dict[str, str]]:
        """The activity-bar buttons of the plugins: ``id``, ``tip`` and ``icon``."""
        return [
            {"id": key, "tip": owned.item.title, "icon": owned.item.icon}
            for key, owned in self._activities.items()
        ]

    def has_activity(self, activity: str) -> bool:
        return activity in self._activities

    @Slot(str, result=dict)
    def activityInfo(self, activity: str) -> dict[str, Any]:
        """The header of a plugin activity: its ``title`` and ``actions``."""
        owned = self._activities.get(activity)
        if owned is None:
            return {"title": "", "actions": []}
        return {"title": owned.item.title, "actions": _pane_actions(owned.item.actions)}

    @Slot(str, result=QObject)
    def activityFoot(self, activity: str) -> QObject | None:
        owned = self._activities.get(activity)
        return owned.item.foot if owned is not None else None

    @Slot(str, str)
    def runActivityAction(self, activity: str, action_id: str) -> None:
        owned = self._activities.get(activity)
        if owned is not None:
            self._run_pane_action(owned.plugin_title, owned.item.actions, action_id)

    # ------------------------------------------------------------------ sidebar sections

    @Slot(str, result=list)
    def sections(self, activity: str) -> list[dict[str, Any]]:
        """The sections shown in an activity: ``key``, ``title``, ``actions``, ``plugin``."""
        found: list[dict[str, Any]] = []
        for key, owned in self._sections.items():
            target = owned.item.activity
            wanted = (
                target if target in {"explorer", "playlists"} else f"{owned.plugin_id}.{target}"
            )
            if wanted == activity:
                found.append(
                    {
                        "key": key,
                        "title": owned.item.title,
                        "plugin": owned.plugin_title,
                        "actions": _pane_actions(owned.item.actions),
                    }
                )
        return found

    @Slot(str, result=QObject)
    def sectionModel(self, key: str) -> QObject | None:
        owned = self._sections.get(key)
        return owned.item.model if owned is not None else None

    @Slot(str, str)
    def runSectionAction(self, key: str, action_id: str) -> None:
        owned = self._sections.get(key)
        if owned is not None:
            self._run_pane_action(owned.plugin_title, owned.item.actions, action_id)

    @Slot(str, str)
    def activateRow(self, key: str, row_id: str) -> None:
        """A row of a section was clicked: ask the plugin which tab to open."""
        owned = self._sections.get(key)
        if owned is None or owned.item.activate is None:
            return
        request = self._guard(owned.plugin_title, "opening an item", owned.item.activate, row_id)
        if request is not None and request.kind in self._kinds:
            self.tabRequested.emit(request.kind, request.ref)

    def _run_pane_action(
        self, plugin_title: str, actions: Sequence[PaneAction], action_id: str
    ) -> None:
        for action in actions:
            if action.action_id == action_id:
                self._guard(plugin_title, action.tip, action.run)
                return

    # ------------------------------------------------------------------ tab kinds

    def is_plugin_kind(self, kind: str) -> bool:
        return kind in self._kinds

    @Slot(str, result=bool)
    def isTrackList(self, kind: str) -> bool:
        """Whether ``kind`` is a plugin tab shown with the core track list."""
        return self.is_track_list_kind(kind)

    def is_track_list_kind(self, kind: str) -> bool:
        owned = self._kinds.get(kind)
        return owned is not None and not isinstance(owned.item.content, Path)

    def tab_title(self, kind: str, ref: str) -> str:
        owned = self._kinds.get(kind)
        if owned is None:
            return ref
        title = self._guard(owned.plugin_title, "naming a tab", owned.item.title_fn, ref)
        return str(title) if title else owned.plugin_title

    def tab_icon(self, kind: str) -> str:
        owned = self._kinds.get(kind)
        return owned.item.icon if owned is not None else ""

    @Slot(str, result=str)
    def tabQml(self, kind: str) -> str:
        """The URL of the QML file of a tab kind, or an empty string for a track list."""
        owned = self._kinds.get(kind)
        if owned is None or not isinstance(owned.item.content, Path):
            return ""
        return QUrl.fromLocalFile(str(owned.item.content)).toString()

    @Slot(str, result=QObject)
    def tabBackend(self, kind: str) -> QObject | None:
        owned = self._kinds.get(kind)
        return owned.item.backend if owned is not None else None

    @Slot(str, str, int, result=dict)
    def tabHeader(self, kind: str, ref: str, _revision: int = 0) -> dict[str, str]:
        """The header of a plugin track list: ``title``, ``kindLabel``, ``description``, ..."""
        owned = self._kinds.get(kind)
        header = TabHeader(title=self.tab_title(kind, ref))
        if owned is not None and owned.item.header is not None:
            given = self._guard(owned.plugin_title, "drawing a header", owned.item.header, ref)
            if isinstance(given, TabHeader):
                header = given
        return {
            "name": header.title,
            "kindLabel": header.kind_label,
            "description": header.description,
            "creator": header.creator,
            "metaText": header.meta,
        }

    def track_rows(
        self, kind: str, ref: str, library_track: Callable[[str], dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """The rows of a plugin track list as the list model shows them (job thread).

        A row with a ``track_id`` found in the library takes the library values (path, cover,
        format…) under the title, artist, album and duration of the plugin; a row without
        one, or whose file is not readable, is unavailable.
        """
        owned = self._kinds.get(kind)
        if owned is None or isinstance(owned.item.content, Path):
            return []
        given = self._guard(owned.plugin_title, "reading a list", owned.item.content, ref)
        rows: list[dict[str, Any]] = []
        for item in given or ():
            if isinstance(item, TrackListRow):
                rows.append(_list_row(item, library_track(item.track_id) if item.track_id else {}))
        return rows

    # ------------------------------------------------------------------ header buttons

    @Slot(str, str, int, result=list)
    def headerActions(self, kind: str, ref: str, _revision: int = 0) -> list[dict[str, Any]]:
        """The buttons beside Play and Shuffle of a tab: ``id``, ``label``, ``icon``, ``kind``..."""
        buttons: list[dict[str, Any]] = []
        for owned in self._tab_actions:
            action = owned.item
            if action.tab_kind != kind:
                continue
            label = action.label
            if callable(label):
                label = self._guard(owned.plugin_title, "naming a button", label, ref)
            enabled = True
            if action.enabled is not None:
                enabled = bool(
                    self._guard(owned.plugin_title, "reading a button", action.enabled, ref)
                )
            reason = ""
            if action.disabled_reason is not None:
                reason = str(
                    self._guard(owned.plugin_title, "reading a button", action.disabled_reason, ref)
                    or ""
                )
                enabled = enabled and not reason
            checked = False
            if action.checked is not None:
                checked = bool(
                    self._guard(owned.plugin_title, "reading a button", action.checked, ref)
                )
            buttons.append(
                {
                    "id": f"{owned.plugin_id}.{action.action_id}",
                    "label": str(label or ""),
                    "icon": action.icon,
                    "kind": action.kind,
                    "checked": checked,
                    "enabled": enabled,
                    "reason": reason,
                }
            )
        return buttons

    @Slot(str, int, result=str)
    def playlistMeta(self, playlist_id: str, _revision: int = 0) -> str:
        """The phrases plugins add to the meta line of a local playlist, joined with `` · ``."""
        phrases = [
            str(
                self._guard(
                    owned.plugin_title, "describing a playlist", owned.item.text, playlist_id
                )
                or ""
            )
            for owned in self._playlist_meta
        ]
        return " · ".join(phrase for phrase in phrases if phrase)

    @Slot(str, str)
    def runHeaderAction(self, action_key: str, ref: str) -> None:
        for owned in self._tab_actions:
            if f"{owned.plugin_id}.{owned.item.action_id}" == action_key:
                self._guard(owned.plugin_title, "running a button", owned.item.run, ref)
                self.refresh()
                return

    # ------------------------------------------------------------------ columns

    @Property(list, notify=changed)
    def columnOptions(self) -> list[dict[str, Any]]:
        """The entries the column picker adds: ``key``, ``label``, ``plugin`` and ``width``."""
        return column_options(self._columns)

    def has_column(self, key: str) -> bool:
        return any(item.key == key for item in self._columns)

    def decorate(
        self, rows: list[dict[str, Any]], kind: str = "", ref: str = ""
    ) -> list[dict[str, Any]]:
        """Add the plugin cells to the rows of the list ``kind``/``ref`` (job thread)."""
        return decorate_rows(rows, self._columns, kind, ref)

    def sort_text(self, key: str, row: Mapping[str, Any]) -> str:
        """The text a plugin column shows for a row, to sort by it."""
        cell = (row.get("plugin") or {}).get(key) or {}
        return str(cell.get("text", ""))

    @Slot(str, dict, result=list)
    def hiddenColumns(self, kind: str, preferences: dict[str, Any]) -> list[str]:
        """The hidden columns of a layout, adding the plugin columns that start hidden."""
        return effective_hidden(preferences, self._columns, kind)

    @Slot(str, dict, str, result=dict)
    def toggledColumns(self, kind: str, preferences: dict[str, Any], key: str) -> dict[str, Any]:
        return toggled_columns(preferences, self._columns, kind, key)

    @Slot(str, int, result=dict)
    def tabColumns(self, kind: str, _revision: int = 0) -> dict[str, Any]:
        """The saved column layout of a plugin tab kind."""
        return self._columns_store.preferences(kind)

    @Slot(str, dict)
    def setTabColumns(self, kind: str, preferences: dict[str, Any]) -> None:
        self._columns_store.save(kind, preferences)
        self.changed.emit()

    @Slot(str)
    def resetTabColumns(self, kind: str) -> None:
        self._columns_store.reset(kind)
        self.changed.emit()

    def resize_column(self, kind: str, key: str, width: int) -> None:
        self._columns_store.resize(kind, key, width)
        self.changed.emit()

    def move_column(self, kind: str, key: str, offset: int) -> None:
        self._columns_store.move(kind, key, offset, self._column_keys())
        self.changed.emit()

    def move_column_relative(self, kind: str, key: str, target: str, after: bool) -> None:
        self._columns_store.move_relative(kind, key, target, after, self._column_keys())
        self.changed.emit()

    def _column_keys(self) -> list[str]:
        return [item.key for item in self._columns]

    @Slot(dict)
    def runRowAction(self, row: dict[str, Any]) -> None:
        """The inline button of a row was pressed: the column that named it handles it."""
        key = str(row.get("rowActionColumn", ""))
        for registered in self._columns:
            if registered.key == key and registered.column.run_action is not None:
                self._guard(
                    registered.plugin_title,
                    "running a row button",
                    registered.column.run_action,
                    row,
                )
                self.refresh()
                return

    # ------------------------------------------------------------------ track menu

    def track_action_items(self, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """The menu entries for the selected rows: captions (``header``) and actions (``key``)."""
        groups: dict[str, list[dict[str, Any]]] = {}
        for key, owned in self._track_actions.items():
            action = owned.item
            if action.enabled_fn is not None and not self._guard(
                owned.plugin_title, "reading a menu entry", action.enabled_fn, rows
            ):
                continue
            groups.setdefault(action.group, []).append({"key": key, "label": action.label})
        items: list[dict[str, Any]] = []
        for group, entries in groups.items():
            items.append({"header": True, "label": group, "key": ""})
            items.extend({"header": False, **entry} for entry in entries)
        return items

    def run_track_action(self, key: str, rows: Sequence[Mapping[str, Any]]) -> None:
        owned = self._track_actions.get(key)
        if owned is not None:
            self._guard(owned.plugin_title, owned.item.label, owned.item.run, rows)

    # ------------------------------------------------------------------ settings pages

    @Property(list, notify=changed)
    def settingsPages(self) -> list[dict[str, str]]:
        """The extra pages of Settings: ``key`` and ``label``."""
        return [{"key": key, "label": owned.item.label} for key, owned in self._pages.items()]

    def has_settings_page(self, key: str) -> bool:
        return key in self._pages

    @Slot(str, result=str)
    def settingsPageQml(self, key: str) -> str:
        owned = self._pages.get(key)
        return QUrl.fromLocalFile(str(owned.item.content)).toString() if owned else ""

    @Slot(str, result=QObject)
    def settingsPageBackend(self, key: str) -> QObject | None:
        owned = self._pages.get(key)
        return owned.item.backend if owned is not None else None

    # ------------------------------------------------------------------ waiting for the user

    def _watch_waiting(self, model: QAbstractItemModel) -> None:
        """Count again whenever the plugin changes the rows of a waiting group."""
        for signal in (
            model.modelReset,
            model.rowsInserted,
            model.rowsRemoved,
            model.layoutChanged,
        ):
            signal.connect(self._update_waiting)

    def _update_waiting(self) -> None:
        count = sum(group.item.model.rowCount() for group in self._waiting.values())
        if count != self._waiting_count:
            self._waiting_count = count
            self.waitingChanged.emit()

    @Property(int, notify=waitingChanged)
    def waitingCount(self) -> int:
        """How many items wait for the user in all groups: they count in the Tasks badge."""
        return self._waiting_count

    @Property(list, notify=changed)
    def waitingGroups(self) -> list[dict[str, str]]:
        """The groups of the Tasks page and pane: ``key``, ``title`` and ``plugin``."""
        return [
            {"key": key, "title": owned.item.title, "plugin": owned.plugin_title}
            for key, owned in self._waiting.items()
        ]

    @Slot(str, result=QObject)
    def waitingModel(self, key: str) -> QObject | None:
        """The rows of a group: ``id``, ``title``, ``subtitle`` and ``action``."""
        owned = self._waiting.get(key)
        return owned.item.model if owned is not None else None

    @Slot(str, str)
    def runWaiting(self, key: str, row_id: str) -> None:
        """The primary button of an item was pressed: the plugin may name a tab to open."""
        owned = self._waiting.get(key)
        if owned is None:
            return
        request = self._guard(
            owned.plugin_title, "answering a waiting item", owned.item.run, row_id
        )
        if request is not None and request.kind in self._kinds:
            self.tabRequested.emit(request.kind, request.ref)

    @Slot(str, str)
    def dismissWaiting(self, key: str, row_id: str) -> None:
        owned = self._waiting.get(key)
        if owned is not None:
            self._guard(owned.plugin_title, "dismissing a waiting item", owned.item.dismiss, row_id)

    # ------------------------------------------------------------------ dialogs

    def open_dialog(self, key: str, ref: str) -> None:
        """Ask the window to show the dialog ``key`` (``<plugin_id>.<dialog_id>``)."""
        if key in self._dialogs:
            self.dialogRequested.emit(key, ref)

    @Slot(str, result=str)
    def dialogQml(self, key: str) -> str:
        """The URL of the QML file of a dialog, or an empty text."""
        owned = self._dialogs.get(key)
        return QUrl.fromLocalFile(str(owned.item.content)).toString() if owned else ""

    @Slot(str, result=QObject)
    def dialogBackend(self, key: str) -> QObject | None:
        owned = self._dialogs.get(key)
        return owned.item.backend if owned is not None else None

    @Slot(str, result=int)
    def dialogWidth(self, key: str) -> int:
        """The width in pixels the plugin asked for its dialog ``key`` (480 when unknown)."""
        owned = self._dialogs.get(key)
        return owned.item.width if owned is not None else 480

    # ------------------------------------------------------------------ delete choices

    def delete_choices(self, track_ids: Sequence[str]) -> list[dict[str, Any]]:
        """The choices the running plugins add to the delete confirmation for ``track_ids``.

        One group per plugin that offers something, in the order the plugins were registered:
        ``plugin`` (its title), ``pluginId`` and ``choices``, each ``key``, ``label``,
        ``description``, ``tone`` (``normal`` or ``danger``) and ``replaces``. A plugin whose
        ``offer`` fails, or that returns nothing usable, is left out: the confirmation of the
        core is never held back by a plugin. Graphical thread.
        """
        groups: list[dict[str, Any]] = []
        for owned in self._delete_choices.values():
            offered = self._guard(
                owned.plugin_title, "offering delete choices", owned.item.offer, tuple(track_ids)
            )
            choices: list[dict[str, Any]] = []
            seen: set[str] = set()
            for choice in offered or ():
                if (
                    not isinstance(choice, DeleteChoice)
                    or not choice.choice_id
                    or not choice.label.strip()
                    or choice.choice_id in seen
                ):
                    continue
                seen.add(choice.choice_id)
                choices.append(
                    {
                        "key": f"{owned.plugin_id}.{choice.choice_id}",
                        "label": choice.label,
                        "description": choice.description,
                        "tone": "danger" if choice.tone == "danger" else "normal",
                        "replaces": bool(choice.replaces_recycle),
                    }
                )
            if choices:
                groups.append(
                    {
                        "plugin": owned.plugin_title,
                        "pluginId": owned.plugin_id,
                        "choices": choices,
                    }
                )
        return groups

    def run_delete_choice(
        self,
        key: str,
        track_ids: Sequence[str],
        job: JobContext,
        recycle: Callable[[Sequence[str]], RecycleOutcome],
    ) -> str:
        """Run the choice ``key`` of a plugin and return the sentence to show; job thread.

        ``recycle`` is what the request's ``recycle`` calls: the core's recycle of the files the
        user confirmed. The plugin's exception is not caught here: the caller shows it. Raises
        ``LookupError`` when the plugin or its choices are gone.
        """
        plugin_id, _, choice_id = key.partition(".")
        owned = self._delete_choices.get(plugin_id)
        if owned is None or not choice_id:
            raise LookupError("The plugin that offered this choice is no longer running.")
        request = DeleteRequest(choice_id, tuple(track_ids), job, recycle)
        done = owned.item.run(request)
        return done if isinstance(done, str) and done.strip() else "Done."

    # ------------------------------------------------------------------ library scans

    def library_scanned(self, root: Path) -> None:
        """Tell the running plugins that the scan of the library folder ``root`` finished."""
        for owned in self._scan_hooks:
            self._guard(owned.plugin_title, "reading a scanned folder", owned.item.callback, root)

    # ------------------------------------------------------------------ guard

    def _guard(self, plugin_title: str, what: str, call: Callable[..., Any], *args: Any) -> Any:
        """Run a function of a plugin; a failure is logged, announced once, and gives ``None``."""
        try:
            return call(*args)
        except Exception as error:
            _LOGGER.error("Plugin %s failed while %s.", plugin_title, what, exc_info=error)
            marker = f"{plugin_title}:{what}"
            if marker not in self._reported:
                self._reported.add(marker)
                self.noticeRaised.emit(f"The plugin {plugin_title} failed while {what}: {error}")
            return None


def _pane_actions(actions: Sequence[PaneAction]) -> list[dict[str, str]]:
    return [{"id": item.action_id, "tip": item.tip, "icon": item.icon} for item in actions]


def _list_row(item: TrackListRow, library: dict[str, Any]) -> dict[str, Any]:
    """Build the row dictionary of the track list for one ``TrackListRow``."""
    if library and is_non_file_row(library):
        available = row_is_available(library)  # a track a plugin provides has no file to find
    else:
        available = bool(
            library
            and library.get("rootId")
            and library.get("status") == "readable"
            and library.get("path")
            and Path(str(library["path"])).is_file()
        )
    seconds = round(item.duration_seconds)
    row: dict[str, Any] = dict(library) if available else {}
    row.update(
        {
            "id": item.row_id,
            "trackId": item.track_id if available else "",
            "available": available,
            "title": item.title,
            "artist": item.artist,
            "album": item.album,
            "seconds": seconds,
            "duration": f"{seconds // 60}:{seconds % 60:02d}" if seconds else "",
            "cover": row.get("cover", -1),
            "coverUrl": row.get("coverUrl", "") if available else "",
            "key": row.get("key", ""),
            "data": dict(item.data),
        }
    )
    return row
