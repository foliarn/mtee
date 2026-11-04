"""Live Explorer state, folder browsing and navigation actions for QML."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import Property, QEvent, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication, QMouseEvent, QWindow

from mtee.domain.artist_index import DEFAULT_ARTIST_SORT
from mtee.domain.job_summaries import fixed, scan_summary
from mtee.domain.jobs import JobCancelledError, JobId
from mtee.domain.navigation_history import NavigationLocation
from mtee.models import window_layout as layout
from mtee.models.analysis_model import AnalysisModel
from mtee.models.analysis_settings_model import AnalysisSettingsModel
from mtee.models.artist_index_model import ArtistListModel
from mtee.models.availability_filter import AvailabilityFilter
from mtee.models.file_move_model import FileMoveModel
from mtee.models.folder_tree_model import FolderTreeModel
from mtee.models.metadata_editor_model import MetadataEditorModel
from mtee.models.playback_settings_model import PlaybackSettingsModel
from mtee.models.player_model import PlayerModel
from mtee.models.playlists_model import PlaylistsModel
from mtee.models.plugin_ui_model import PluginUiModel
from mtee.models.plugins_view_model import PluginsViewModel
from mtee.models.status_bar_model import StatusBarModel
from mtee.models.tag_conflicts_model import TagConflictsModel
from mtee.models.tool_windows import ToolWindowRegistry
from mtee.models.track_list_model import TrackListModel
from mtee.models.trash_model import TrashModel
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
from mtee.models.workspace_artists import (
    decide_artist_index_effects,
    format_artist_decision_message,
    prepare_artist_playback_rows,
    sort_artist_tracks,
)
from mtee.models.workspace_clipboard import (
    PastePlan,
    TrackClipboard,
    plan_drop,
    plan_paste,
)
from mtee.models.workspace_columns import (
    find_tabs_with_hidden_sort,
    move_column,
    move_column_relative,
    reset_column_preferences,
    resize_column,
    resize_columns,
    set_show_artwork,
    toggle_column,
)
from mtee.models.workspace_explorer import (
    ExplorerTrackCoordinator,
    find_revealed_track_row,
    resolve_folder_source_exists,
    update_captured_rows,
    validate_explorer_track,
)
from mtee.models.workspace_navigation import (
    WorkspaceNavigationTracker,
    build_navigation_location,
    restore_scroll_and_anchor,
)
from mtee.models.workspace_playback import (
    EnqueueTracker,
    build_playlist_track_playback,
    filter_enqueue_targets,
    format_playback_source_title,
    prepare_playlist_playback_rows,
    reorder_playlist_items,
    resolve_folder_playback_rows,
)
from mtee.models.workspace_rows import (
    copy_column_preferences,
    folder_from_track,
    listening_details,
    local_path,
    parse_folder_id,
    parse_folder_ref,
    with_play_stats,
)
from mtee.models.workspace_scan_coordinator import (
    FolderBranchTracker,
    WorkspaceScanCoordinator,
    compute_folder_watch_targets,
    format_scan_finished_message,
)
from mtee.models.workspace_selection import (
    calculate_selection,
    format_info_fields_read_only,
    format_info_file_fields,
    resolve_local_track_ids,
)
from mtee.models.workspace_session import (
    COLUMN_KEYS as _COLUMN_KEYS,
)
from mtee.models.workspace_session import (
    WorkspaceSessionWriter,
    build_session_snapshot,
    ensure_tab_state,
    extract_view_fields,
    restore_session_groups,
    set_default_sort,
)
from mtee.models.workspace_tabs import (
    build_groups_snapshot,
    close_tab_in_group,
    is_tab_in_any_group,
    keep_tab_state,
    open_special_tab,
    place_tab,
    purge_forgotten_tab_state,
)
from mtee.models.workspace_track_loader import (
    PLAY_COLUMN_KEYS,
    TrackRequestTracker,
    compute_track_request_key,
    filter_track_rows,
    needs_play_stats,
    order_track_rows,
)
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.play_log_repository import PlayLogRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.workspace_repository import (
    COLUMN_OPTIONS,
    DEFAULT_COLUMN_PREFERENCES,
    WorkspaceRepository,
)
from mtee.plugins.availability_registry import TrackAvailabilityRegistry
from mtee.plugins.context import PluginHost
from mtee.plugins.loader import LoadedPlugin
from mtee.plugins.registry import plugin_ui_enabled
from mtee.services.folder_refresh import refresh_folder
from mtee.services.folder_watch import FolderWatchService
from mtee.services.jobs import JobContext, JobService
from mtee.services.library_scanner import LibraryScanner
from mtee.services.metadata_reader import MetadataReader
from mtee.services.platform.shell_reveal import WindowsShellReveal

if TYPE_CHECKING:
    from mtee.domain.artist_index import ArtistEntry, ArtistIndex
    from mtee.services.artist_index_service import ArtistIndexService

__all__ = ["WorkspaceModel"]

# Listening columns: their values come from the play log, read off the graphical thread.
_PLAY_COLUMN_KEYS = PLAY_COLUMN_KEYS
# The pages of the Settings tab, in the order of its category list.
# The smallest share of a split that a center window may take (the model holds no pixels).
MIN_CENTER_WINDOW_SHARE = 0.1

SETTINGS_PAGES = (
    "general",
    "library",
    "playback",
    "analysis",
    "shortcuts",
    "privacy",
    "plugins",
    "about",
)
# The Profile page is a tab opened from the activity bar, not an activity of the sidebar.
# The Tasks window is a center tab (plan 134.5), not a tool window: it is not an activity.
_ACTIVITIES = {"explorer", "playlists", "convert", "artists", "plugins"}
_SIDES = ("left", "right")
_RIGHT_TABS = {"info", "queue", "history"}


def _known_activity(activity: str) -> str:
    """Return ``activity`` when this build offers it, otherwise the Explorer.

    A saved state can name an activity that was removed or hidden in the meantime.
    """
    if "." in activity:
        return activity  # a plugin activity: kept until the plugins are loaded and can be asked
    # The Plugins activity is always offered (plan 123, placement B); Convert is a plugin's.
    if activity == "convert" and not plugin_ui_enabled():
        return "explorer"
    return activity if activity in _ACTIVITIES else "explorer"


class WorkspaceModel(QObject):
    """Own live root, tab, selection and scan state; all file work is asynchronous."""

    layoutChanged = Signal()
    clipboardChanged = Signal()
    # A folder just made without a name: the Explorer starts renaming its row (the folder id).
    folderRenameRequested = Signal(str)
    explorerChanged = Signal()
    libraryChanged = Signal()
    selectionChanged = Signal()
    metadataChanged = Signal()
    messageChanged = Signal()
    trackRevealRequested = Signal(str, str, str)
    batchReady = Signal(str, str, object)
    scanFinished = Signal(str, str, object)
    folderRefreshed = Signal(str, str, object)
    activationRequested = Signal(str, list)
    playbackChanged = Signal()
    positionChanged = Signal()
    folderRootsReady = Signal(int, object, object)
    folderBranchReady = Signal(str, int, object, object)
    trackRowsReady = Signal(str, int, object)
    explorerTrackReady = Signal(int, object, object)
    sessionWriteFinished = Signal(object, object)
    playlistCreationRequested = Signal(list)
    renameFileRequested = Signal(str, str)
    enqueuePrepared = Signal(int, object)
    artistsChanged = Signal()
    availabilityFilterChanged = Signal()
    taskFocusRequested = Signal(str)

    def __init__(
        self,
        *,
        library: LibraryRepository,
        session: WorkspaceRepository,
        jobs: JobService,
        player: PlayerModel | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._library = library
        self._session = session
        self._jobs = jobs
        self._player = player
        self._playlists_model: PlaylistsModel | None = None
        self._genre_manager_factory: Callable[[], QObject] | None = None
        self._genre_manager_model: QObject | None = None
        self._enqueue_tracker = EnqueueTracker()
        self._metadata_editor: MetadataEditorModel | None = None
        # The conversion queue is a plugin service: attached only when the plugin is enabled.
        self._conversion_model: Any | None = None
        # What the running plugins add to the interface: empty without a plugin.
        self._plugin_ui = PluginUiModel(self)
        # The status bar under the player bar (plan 125.5): the items of the plugins, if any.
        self._status_bar = StatusBarModel(self)
        self._plugins_view: PluginsViewModel | None = None
        self._trash_model: TrashModel | None = None
        self._file_move_model: FileMoveModel | None = None
        self._analysis_model: AnalysisModel | None = None
        self._analysis_settings: AnalysisSettingsModel | None = None
        self._playback_settings: PlaybackSettingsModel | None = None
        self._play_log: PlayLogRepository | None = None
        self._tag_conflicts: TagConflictsModel | None = None
        self._artist_manager: Any = None
        # The core artist index: the Artists view, the artist links and the artist tabs.
        self._artist_index: ArtistIndexService | None = None
        self._artist_list: ArtistListModel | None = None
        self._artist_revision = 0
        self._artist_index_seen: ArtistIndex | None = None
        # An artist action in progress: the artist it was made on and the credits it changes.
        self._pending_artist_choice: tuple[str, frozenset[str]] | None = None
        self._scanner = LibraryScanner()
        self._reader = MetadataReader()
        self._shell_reveal = WindowsShellReveal()
        self._roots_by_id: dict[str, dict[str, Any]] = {}
        self._resume_roots_requested = False
        self._state = session.load()
        # The order of the Artists list, saved with the workspace (plan 132.5).
        self._artist_sort = str(self._state.get("artistSort", DEFAULT_ARTIST_SORT))
        saved_column_preferences = self._state.get("columnPreferences", DEFAULT_COLUMN_PREFERENCES)
        self._column_preferences = copy_column_preferences(saved_column_preferences)
        self._expanded = set(self._state.get("expanded", []))
        self._window_geometry: dict[str, Any] | None = self._state.get("window")
        self._track_clipboard = TrackClipboard()
        self._folder_tabs_checked = False
        self._groups, self._layout, self._tab_states, self._next_group = self._restore_groups(
            self._state.get("groups", []), self._state.get("center")
        )
        order = self._group_order()
        saved_active = self._state.get("activeGroup", "")
        self._active_group = saved_active if saved_active in order else order[0]
        with suppress(TypeError, ValueError, OverflowError):
            self._next_group = max(self._next_group, int(self._state.get("nextGroup", 1)))
        self._selection_by_tab: dict[tuple[str, str], list[str]] = {}
        self._anchor_by_tab: dict[tuple[str, str], str] = {}
        # Song rows of the Explorer tree may be selected across folders (U14). While the source
        # is "explorer" the selection is this list, not the one of the active tab.
        self._selection_source = ""
        self._explorer_selection: list[str] = []
        self._explorer_anchor = ""
        for group_id in order:
            group = self._groups[group_id]
            saved = group.get("selections", {})
            for tab_id in group["tabs"]:
                tab_state = self._tab_state(tab_id)
                selected = saved.get(tab_id, {})
                if not isinstance(selected, dict):
                    selected = {}
                key = (group_id, tab_id)
                self._selection_by_tab[key] = list(
                    selected.get("ids", tab_state.get("selectedIds", []))
                )
                self._anchor_by_tab[key] = str(
                    selected.get("anchor", tab_state.get("selectionAnchor", ""))
                )
        # The docks hold the tool windows; until 131.4 the first window of each dock is the
        # one the model shows.
        docks = self._state.get("docks", {})
        self._docks: dict[str, layout.DockState] = {
            "left": layout.DockState.from_dict("left", docks.get("left")),
            "right": layout.DockState.from_dict("right", docks.get("right")),
        }
        self._tool_windows = ToolWindowRegistry(self._plugin_ui)
        self._activity = _known_activity(self._activity)
        self._fullscreen = False
        self._fullscreen_page = 0
        self._preview_tabs = bool(self._state.get("previewTabs", True))
        self._settings_pages: dict[str, str] = {group_id: "general" for group_id in order}
        self._group_tab_states: dict[tuple[str, str], dict[str, Any]] = {
            (group_id, tab_id): self._view_fields(self._tab_states.get(tab_id, {}))
            for group_id in order
            for tab_id in self._groups[group_id]["tabs"]
        }
        self._nav = WorkspaceNavigationTracker()
        for group_id in order:
            self._nav.add_group(group_id, self._navigation_location(group_id))
        self._message = (
            "The saved workspace was invalid. MTEE restored a safe default layout."
            if session.load_recovered
            else ""
        )
        self._revision = 0
        self._scan_coordinator = WorkspaceScanCoordinator()
        self._branch_tracker = FolderBranchTracker()
        self._track_models: dict[str, TrackListModel] = {}
        # "Hide tracks not on this device": the stored choice and the plugin that answers (125.3).
        self._availability = AvailabilityFilter()
        self._track_tracker = TrackRequestTracker()
        self._explorer_coordinator = ExplorerTrackCoordinator()
        self._folder_root_generation = 0
        self._folder_root_job_id = ""
        self._folder_model = FolderTreeModel(self)
        self._session_writer = WorkspaceSessionWriter(
            save_fn=self._session.save,
            on_write_finished=self.sessionWriteFinished.emit,
        )
        self._session_timer = QTimer(self)
        self._session_timer.setSingleShot(True)
        self._session_timer.setInterval(300)
        self._session_timer.timeout.connect(self._write_pending_session)
        self.sessionWriteFinished.connect(self._on_session_write_finished)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(90)
        self._refresh_timer.timeout.connect(self._refresh_models)
        self._folder_watch = FolderWatchService(self)
        self._folder_watch.folderChanged.connect(self._on_folder_watch_changed)
        self.layoutChanged.connect(self._sync_folder_watches)
        self.folderRefreshed.connect(self._on_folder_refreshed)
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.applicationStateChanged.connect(self._on_application_state_changed)
        self.batchReady.connect(self._on_scan_batch)
        self.scanFinished.connect(self._on_scan_finished)
        self.folderRootsReady.connect(self._on_folder_roots_ready)
        self.folderBranchReady.connect(self._on_folder_branch_ready)
        self.trackRowsReady.connect(self._on_track_rows_ready)
        self.explorerTrackReady.connect(self._on_explorer_track_ready)
        self.enqueuePrepared.connect(self._on_enqueue_prepared)
        self._plugin_ui.tabRequested.connect(self.openPluginTab)
        self._plugin_ui.refreshRequested.connect(self._refresh_plugin_lists)
        self._plugin_ui.noticeRaised.connect(self._set_message)
        self._status_bar.noticeRaised.connect(self._set_message)
        if player is not None:
            player.playbackChanged.connect(self.playbackChanged.emit)
            player.positionChanged.connect(self.positionChanged.emit)
        self._persist()
        self._request_folder_roots()

    # ---------------------------------------------------------------- properties

    @Property(str, constant=True)
    def scenarioName(self) -> str:
        return "local-library"

    @Property(int, notify=libraryChanged)
    def revision(self) -> int:
        return self._revision

    @Property(str, notify=layoutChanged)
    def activity(self) -> str:
        return self._activity

    @Property(bool, notify=layoutChanged)
    def sidebarVisible(self) -> bool:
        return self._sidebar_visible

    def groups_snapshot(self) -> list[dict[str, Any]]:
        return build_groups_snapshot(
            self._group_order(),
            self._groups,
            self._tab_states,
            self._group_tab_states,
        )

    @Property(list, notify=layoutChanged)
    def groups(self) -> list[dict[str, Any]]:
        """The center windows in reading order: id, tabs and active tab of each."""
        return self.groups_snapshot()

    @Property(dict, notify=layoutChanged)
    def centerLayout(self) -> dict[str, Any]:
        """The center layout tree (see ``mtee.models.window_layout.node_to_dict``)."""
        return layout.node_to_dict(self._layout)

    @Property(str, notify=layoutChanged)
    def activeTabId(self) -> str:
        return str(self._groups[self._active_group]["active"])

    @Property(dict, notify=layoutChanged)
    def columnPreferences(self) -> dict[str, Any]:
        return copy_column_preferences(self._column_preferences)

    @Property(list, constant=True)
    def columnOptions(self) -> list[dict[str, str]]:
        return [{"key": key, "label": label} for key, label in COLUMN_OPTIONS]

    @Property(str, notify=layoutChanged)
    def activeGroup(self) -> str:
        return self._active_group

    @Property(bool, notify=layoutChanged)
    def canNavigateBack(self) -> bool:
        return self._nav.can_back(self._active_group)

    @Property(bool, notify=layoutChanged)
    def canNavigateForward(self) -> bool:
        return self._nav.can_forward(self._active_group)

    @Property(str, notify=layoutChanged)
    def settingsPage(self) -> str:
        return self._settings_pages[self._active_group]

    @Slot(str, result=str)
    def settingsPageForGroup(self, group_id: str) -> str:
        if group_id in self._groups:
            return self._settings_pages[group_id]
        return "general"

    @staticmethod
    def _view_fields(tab: dict[str, Any]) -> dict[str, Any]:
        return extract_view_fields(tab)

    def _save_group_view(self, group_id: str) -> None:
        tab_id = str(self._groups[group_id]["active"])
        if tab_id:
            self._group_tab_states[(group_id, tab_id)] = self._view_fields(
                self._tab_states.get(tab_id, {})
            )

    def _load_group_view(self, group_id: str) -> None:
        tab_id = str(self._groups[group_id]["active"])
        saved = self._group_tab_states.get((group_id, tab_id))
        if saved is not None:
            self._tab_state(tab_id).update(saved)
            self._scan_coordinator.mark_tab_dirty(tab_id)
            self._refresh_timer.start()

    @staticmethod
    def _model_key(group_id: str, tab_id: str) -> str:
        return tab_id if group_id == layout.DEFAULT_GROUP_ID else f"@{group_id}|{tab_id}"

    @staticmethod
    def _model_identity(model_key: str) -> tuple[str, str]:
        if model_key.startswith("@") and "|" in model_key:
            group, _, tab_id = model_key[1:].partition("|")
            if group:
                return group, tab_id
        return layout.DEFAULT_GROUP_ID, model_key

    def _group_order(self) -> list[str]:
        """The group ids in reading order."""
        return list(layout.groups(self._layout))

    def _new_group_id(self) -> str:
        group_id = f"g{self._next_group}"
        while group_id in self._groups:
            self._next_group += 1
            group_id = f"g{self._next_group}"
        self._next_group += 1
        return group_id

    def _active_track_model(self, tab_id: str) -> TrackListModel | None:
        return self._track_models.get(self._model_key(self._active_group, tab_id))

    def _navigation_location(self, group_id: str) -> NavigationLocation:
        tab_id = str(self._groups[group_id]["active"])
        return build_navigation_location(
            activity=self._activity,
            active_tab_id=tab_id,
            fullscreen=self._fullscreen,
            right_visible=self._right_visible,
            right_tab=self._right_tab,
            settings_page=self._settings_pages[group_id],
            tab_state=self._tab_states.get(tab_id, {}),
            group_tab_state=self._group_tab_states.get((group_id, tab_id)),
            group_id=group_id,
            selected=self._selection_by_tab.get((group_id, tab_id), []),
            anchor=self._anchor_by_tab.get((group_id, tab_id), ""),
            scroll=self._nav.scroll,
            navigation_anchor=self._nav.anchor,
        )

    def _capture_navigation(self) -> None:
        if self._nav.replaying:
            return
        group = self._active_group
        self._save_group_view(group)
        self._nav.capture(group, self._navigation_location(group))

    def _record_navigation(self) -> None:
        if self._nav.replaying:
            return
        group = self._active_group
        self._save_group_view(group)
        self._nav.visit(group, self._navigation_location(group))

    @Slot(str, str, str, float)
    @Slot(str, str, str, float, str, float)
    def setNavigationScroll(
        self,
        group_id: str,
        tab_id: str,
        view: str,
        content_y: float,
        anchor_id: str = "",
        anchor_offset: float = 0.0,
    ) -> None:
        if group_id in self._groups:
            self._nav.set_scroll(group_id, tab_id, view, content_y, anchor_id, anchor_offset)

    @Slot(str, str, str, result=float)
    def navigationScroll(self, group_id: str, tab_id: str, view: str) -> float:
        return self._nav.get_scroll(group_id, tab_id, view)

    @Slot(str, str, str, result=dict)
    def navigationAnchor(self, group_id: str, tab_id: str, view: str) -> dict[str, Any]:
        return self._nav.get_anchor(group_id, tab_id, view)

    @Slot(str)
    def setSettingsPage(self, page: str) -> None:
        self.setSettingsPageForGroup(self._active_group, page)

    def _settings_page_known(self, page: str) -> bool:
        """The core pages and the pages of running plugins."""
        return page in SETTINGS_PAGES or self._plugin_ui.has_settings_page(page)

    @Slot(str, str)
    def setSettingsPageForGroup(self, group_id: str, page: str) -> None:
        if (
            group_id not in self._groups
            or not self._settings_page_known(page)
            or page == self._settings_pages[group_id]
        ):
            return
        if group_id != self._active_group:
            self.focusGroup(group_id)
        self._capture_navigation()
        self._settings_pages[group_id] = page
        self._record_navigation()
        self.layoutChanged.emit()

    @Slot()
    def navigateBack(self) -> None:
        self._navigate_history(back=True)

    @Slot()
    def navigateForward(self) -> None:
        self._navigate_history(back=False)

    def _navigate_history(self, *, back: bool) -> None:
        group = self._active_group
        self._capture_navigation()
        playlists_model = self._playlists_model
        location, messages = self._nav.step(
            group,
            back=back,
            is_playlist_available=(
                (lambda pid: bool(playlists_model.details(pid)))
                if playlists_model is not None
                else None
            ),
        )
        for msg in messages:
            self._set_message(msg)
        if location is not None:
            self._replay_navigation(location)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            isinstance(watched, QWindow)
            and watched.isActive()
            and event.type() == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
        ):
            if event.button() == Qt.MouseButton.BackButton:
                self.navigateBack()
                return True
            if event.button() == Qt.MouseButton.ForwardButton:
                self.navigateForward()
                return True
        return super().eventFilter(watched, event)

    def _replay_navigation(self, location: NavigationLocation) -> None:
        self._nav.replaying = True
        try:
            self._cancel_explorer_track_action()
            group = self._groups[self._active_group]
            tab_id = location.tab_id
            if (
                tab_id.startswith("playlist:")
                and self._playlists_model is not None
                and not self._playlists_model.details(tab_id.partition(":")[2])
            ):
                self._set_message("This playlist is no longer available.")
                return
            if tab_id:
                self._ensure_tab(tab_id)
                if tab_id not in group["tabs"]:
                    group["tabs"].append(tab_id)
            group["active"] = tab_id
            self._activity = _known_activity(location.activity)
            self._fullscreen = location.fullscreen
            self._right_visible = location.right_visible
            self._right_tab = location.right_tab
            self._settings_pages[self._active_group] = location.settings_page
            tab = self._tab_states.get(tab_id)
            if tab is not None:
                for key in ("searchQuery", "sortKey", "sortAscending", "sortMode", "view"):
                    if key in location.view:
                        tab[key] = location.view[key]
                self._group_tab_states[(self._active_group, tab_id)] = self._view_fields(tab)
                self._scan_coordinator.mark_tab_dirty(tab_id)
                self._revision += 1
                self.libraryChanged.emit()
                self._refresh_timer.start()
            self._selection_by_tab[(self._active_group, tab_id)] = list(
                location.view.get("selected", [])
            )
            if tab_id.startswith(("folder:", "playlist:")):
                self._nav.pending_selection = (
                    self._active_group,
                    tab_id,
                    list(self._selection_by_tab[(self._active_group, tab_id)]),
                )
            self._anchor_by_tab[(self._active_group, tab_id)] = str(location.view.get("anchor", ""))
            restore_scroll_and_anchor(
                self._nav.scroll,
                self._nav.anchor,
                self._active_group,
                tab_id,
                location.view,
            )
            self.layoutChanged.emit()
            self.selectionChanged.emit()
            self._persist()
        finally:
            self._nav.replaying = False

    @Property(int, notify=layoutChanged)
    def sidebarWidth(self) -> int:
        return self._sidebar_width

    @Property(int, notify=layoutChanged)
    def rightPanelWidth(self) -> int:
        return self._right_panel_width

    @Property(str, notify=layoutChanged)
    def activeFolder(self) -> str:
        active = str(self._groups[self._active_group]["active"])
        return f"folder:{active.partition(':')[2]}" if active.startswith("folder:") else ""

    @Property(bool, notify=layoutChanged)
    def rightPanelVisible(self) -> bool:
        return self._right_visible

    @Property(str, notify=layoutChanged)
    def rightPanelTab(self) -> str:
        return self._right_tab

    @Property(bool, notify=layoutChanged)
    def fullscreen(self) -> bool:
        return self._fullscreen

    @Property(int, notify=layoutChanged)
    def fullscreenPage(self) -> int:
        """Page of the fullscreen player: 0 for the card, 1 for queue and track details."""
        return self._fullscreen_page

    @Property(bool, notify=layoutChanged)
    def previewTabs(self) -> bool:
        return self._preview_tabs

    @Property(QObject, constant=True)
    def playerModel(self) -> QObject:
        return self._player if self._player is not None else self

    @Property(QObject, constant=True)
    def folderTreeModel(self) -> QObject:
        return self._folder_model

    @Property(list, notify=explorerChanged)
    def explorerRows(self) -> list[dict[str, Any]]:
        return self._folder_model.rows_snapshot()

    @Property(list, notify=selectionChanged)
    def selectedIds(self) -> list[str]:
        return self._current_selection()

    def _current_selection(self) -> list[str]:
        if self._selection_source == "explorer":
            return list(self._explorer_selection)
        tab_id = str(self._groups[self._active_group]["active"])
        return list(self._selection_by_tab.get((self._active_group, tab_id), []))

    def _leave_explorer_selection(self) -> None:
        """Drop the tree selection; the selection of the active tab shows again."""
        self._selection_source = ""
        self._explorer_selection = []

    def _explorer_track_order(self) -> list[str]:
        """Song rows of the tree in the order they are shown (the basis of Shift-click)."""
        return [
            str(row["id"])
            for row in self._folder_model.rows_snapshot()
            if row.get("kind") not in ("folder", "loading")
        ]

    @Slot(str)
    def pickExplorerTrack(self, track_id: str) -> None:
        """Select one song of the tree on its own (right click or drag of an unselected row)."""
        self._explorer_selection = [str(track_id)]
        self._explorer_anchor = str(track_id)
        self._selection_source = "explorer"
        self.selectionChanged.emit()

    @Slot(str, bool)
    def extendExplorerSelection(self, track_id: str, shift: bool) -> None:
        """Ctrl-click toggles a song of the tree, Shift-click selects the rows from the anchor."""
        order = self._explorer_track_order()
        track_id = str(track_id)
        if track_id not in order:
            return
        current = self._current_selection()
        anchor = self._explorer_anchor if self._explorer_anchor in order else track_id
        if shift:
            first, last = sorted((order.index(anchor), order.index(track_id)))
            selection = order[first : last + 1]
        else:
            selection = (
                [value for value in current if value != track_id]
                if track_id in current
                else [*current, track_id]
            )
            anchor = track_id
        self._explorer_selection = selection
        self._explorer_anchor = anchor
        self._selection_source = "explorer"
        self.selectionChanged.emit()

    @Slot(str, result=list)
    def selectedIdsForGroup(self, group_id: str) -> list[str]:
        if group_id not in self._groups:
            return []
        tab_id = str(self._groups[group_id]["active"])
        return list(self._selection_by_tab.get((group_id, tab_id), []))

    def selected_ids_snapshot(self) -> list[str]:
        tab_id = str(self._groups[self._active_group]["active"])
        identities = list(self._selection_by_tab.get((self._active_group, tab_id), []))
        return self.localTrackIds(identities)

    @Property(str, notify=playbackChanged)
    def playingId(self) -> str:
        return self._player.playing_id_value() if self._player is not None else ""

    @Property(dict, notify=playbackChanged)
    def playingTrack(self) -> dict[str, Any]:
        return self._player.playing_track_value() if self._player is not None else {}

    @Property(str, notify=playbackChanged)
    def playingSourceTitle(self) -> str:
        return self._player.playing_source_title_value() if self._player is not None else ""

    @Property(str, notify=playbackChanged)
    def playingSource(self) -> str:
        return self._player.playing_source_value() if self._player is not None else ""

    @Property(str, notify=playbackChanged)
    def playingSourceKind(self) -> str:
        return self._player.playing_source_kind_value() if self._player is not None else ""

    @Property(bool, notify=playbackChanged)
    def isPlaying(self) -> bool:
        return self._player.is_playing_value() if self._player is not None else False

    @Property(float, notify=positionChanged)
    def position(self) -> float:
        return self._player.position_value() if self._player is not None else 0.0

    @Property(int, notify=playbackChanged)
    def volume(self) -> int:
        return self._player.volume_value() if self._player is not None else 72

    @Property(bool, notify=playbackChanged)
    def muted(self) -> bool:
        return self._player.muted_value() if self._player is not None else False

    @Property(bool, notify=playbackChanged)
    def shuffle(self) -> bool:
        return self._player.shuffle_value() if self._player is not None else False

    @Property(str, notify=playbackChanged)
    def repeat(self) -> str:
        return self._player.repeat_value() if self._player is not None else "off"

    @Property(list, notify=playbackChanged)
    def upNext(self) -> list[dict[str, Any]]:
        return self._player.up_next_value() if self._player is not None else []

    @Property(list, notify=playbackChanged)
    def history(self) -> list[dict[str, Any]]:
        return self._player.history_value() if self._player is not None else []

    @Property(str, notify=metadataChanged)
    def saveState(self) -> str:
        if self._metadata_editor is None:
            return "idle"
        return cast(str, self._metadata_editor.saveState)

    @Property(str, notify=metadataChanged)
    def saveMessage(self) -> str:
        if self._metadata_editor is None:
            return ""
        return cast(str, self._metadata_editor.saveMessage)

    @Property(bool, notify=metadataChanged)
    def canStopPlaybackAndSave(self) -> bool:
        return (
            cast(bool, self._metadata_editor.canStopPlaybackAndSave)
            if self._metadata_editor is not None
            else False
        )

    @Property(bool, notify=metadataChanged)
    def canUndoSave(self) -> bool:
        if self._metadata_editor is None:
            return False
        return cast(bool, self._metadata_editor.canUndo)

    @Property(bool, constant=True)
    def metadataEditable(self) -> bool:
        return self._metadata_editor is not None

    @Property(bool, constant=True)
    def conversionError(self) -> bool:
        if self._conversion_model is None:
            return False
        return cast(bool, self._conversion_model.error)

    @Property(list, notify=libraryChanged)
    def convertInputs(self) -> list[dict[str, Any]]:
        return (
            cast(list[dict[str, Any]], self._conversion_model.inputs)
            if self._conversion_model is not None
            else []
        )

    @Property(QObject, constant=True)
    def conversionModel(self) -> QObject:
        return self._conversion_model if self._conversion_model is not None else self

    def attach_conversion_model(self, model: Any) -> None:
        self._conversion_model = model
        model.changed.connect(self.libraryChanged.emit)
        model.recoveryNotice.connect(self._set_message)
        model.outputCatalogued.connect(self._on_conversion_output_catalogued)

    @Slot(str, str)
    def _on_conversion_output_catalogued(self, root_id: str, relative_path: str) -> None:
        self._refresh_library(root_id, {relative_path.rpartition("/")[0]})

    @Property(list, notify=libraryChanged)
    def convertBatches(self) -> list[dict[str, Any]]:
        return []

    @Property(list, notify=libraryChanged)
    def playlists(self) -> list[dict[str, Any]]:
        return (
            cast(list[dict[str, Any]], self._playlists_model.playlists)
            if self._playlists_model is not None
            else []
        )

    @Property(QObject, notify=libraryChanged)
    def playlistModel(self) -> QObject:
        return self._playlists_model if self._playlists_model is not None else self

    def attach_playlists(self, model: PlaylistsModel) -> None:
        self._playlists_model = model
        model.setParent(self)
        model.changed.connect(self._on_playlists_changed)
        model.noticeRaised.connect(self._set_message)
        model.playlistCreated.connect(self.openPlaylist)
        model.playlistDeleted.connect(self._on_playlist_deleted)
        model.playRequested.connect(self.playPlaylistRows)
        model.libraryImported.connect(self._refresh_library)

    @Slot()
    def _on_playlists_changed(self) -> None:
        if self._playlists_model is not None:
            if self._playlists_model.loaded:
                self._drop_missing_playlist_tabs()
            for state in self._tab_states.values():
                if state.get("kind") == "playlist":
                    detail = self._playlists_model.details(str(state.get("ref", "")))
                    if detail:
                        state["title"] = detail["name"]
        self._revision += 1
        self._scan_coordinator.mark_all_tabs_dirty()
        self.libraryChanged.emit()
        self.layoutChanged.emit()
        self._refresh_timer.start()

    def _drop_missing_playlist_tabs(self) -> None:
        """Close, without a word, the restored playlist tabs whose playlist no longer exists."""
        if self._playlists_model is None:
            return
        for group_id in self._group_order():
            for tab_id in tuple(self._groups.get(group_id, {}).get("tabs", [])):
                if tab_id.startswith("playlist:") and not self._playlists_model.details(
                    tab_id.partition(":")[2]
                ):
                    self.closeTab(group_id, tab_id)

    def _drop_missing_folder_tabs(self) -> None:
        """Close, without a word, the folder tabs of a source that is no longer in the library."""
        known = {str(root["id"]) for root in self._library.roots()}
        for group_id in self._group_order():
            for tab_id in tuple(self._groups.get(group_id, {}).get("tabs", [])):
                if not tab_id.startswith("folder:"):
                    continue
                parsed = parse_folder_id(tab_id)
                if parsed is None or parsed[0] not in known:
                    self.closeTab(group_id, tab_id)

    @Slot(str)
    def _on_playlist_deleted(self, identity: str) -> None:
        for group_id in self._group_order():
            self.closeTab(group_id, "playlist:" + identity)

    @Slot(list, result=list)
    def localTrackIds(self, identities: list) -> list[str]:
        model = self._current_track_model()
        return resolve_local_track_ids(
            identities,
            model.rows_snapshot() if model else None,
        )

    @Slot(str, result=bool)
    def isLiked(self, track_id: str) -> bool:
        return bool(self._playlists_model and self._playlists_model.isLiked(track_id))

    @Slot(str)
    def toggleLike(self, track_id: str) -> None:
        if self._playlists_model is not None:
            self._playlists_model.toggleLike(track_id)

    @Slot(str, str)
    def revealTrack(self, track_id: str, source: str) -> None:
        """Leave fullscreen and show the track in the folder or playlist it was played from.

        When that source no longer exists, the folder of the file is shown instead. Nothing
        is played and the previous selection is replaced by this track.
        """
        identity = str(track_id)
        if not identity:
            return
        if self._fullscreen:
            self.setFullscreen(False)
        kind, _, reference = str(source).partition(":")
        playlist_exists = bool(
            kind == "playlist"
            and self._playlists_model
            and self._playlists_model.details(reference)
        )
        if playlist_exists:
            self.openPlaylist(reference)
            self._select_revealed_row("playlist:" + reference, identity)
            return
        if kind == "artist" and (
            self._artist_entry(reference) is not None or self._is_plugin_artist(reference)
        ):
            self.openArtistPage(reference, "")
            self._select_revealed_row("artist:" + reference, identity)
            return
        if kind == "folder" and self._folder_source_exists(str(source)):
            self.selectExplorerTrack(identity, str(source))
            return
        located = self._library.track_folder(identity)
        if located is None:
            self._set_message("This file is no longer in the library.")
            return
        root_id, relative = located
        folder_id = f"folder:{root_id}/{relative}" if relative else f"root:{root_id}"
        self.selectExplorerTrack(identity, folder_id)

    @Slot(str, str)
    def revealTrackForEdit(self, track_id: str, source: str) -> None:
        """Show the track as ``revealTrack`` does, then open the Info panel on it."""
        self.revealTrack(track_id, source)
        self.showRightPanel("info")

    @Slot(str, result=list)
    def trackArtists(self, track_id: str) -> list[dict[str, str]]:
        """The artists credited on a track by the core index, as {"id", "name"} in credit order."""
        if self._artist_index is None or not track_id:
            return []
        index = self._artist_index.index
        found = []
        for key in index.artists_by_track.get(str(track_id), ()):
            entry = index.entry(key)
            if entry is not None:
                found.append({"id": entry.key, "name": entry.name})
        return found

    @Slot(list)
    def addTracksToConvert(self, track_ids: list) -> None:
        """Queue these tracks, given by their library identity, for conversion and open it."""
        identities = filter_valid_identities(track_ids)
        if self._conversion_model is not None and identities:
            self._conversion_model.add_tracks(identities)
        if self._fullscreen:
            self.setFullscreen(False)
        self.openConvert()

    @Slot()
    def openPlayingSource(self) -> None:
        """Leave fullscreen and open the folder or playlist the playing track comes from."""
        source = self._player.playing_source_value() if self._player is not None else ""
        kind, _, reference = source.partition(":")
        if self._fullscreen:
            self.setFullscreen(False)
        if kind == "playlist" and reference:
            self.openPlaylist(reference)
        elif kind == "artist" and (
            self._artist_entry(reference) is not None or self._is_plugin_artist(reference)
        ):
            self.openArtistPage(reference, "")
        elif kind == "folder" and self._folder_source_exists(source):
            self.openFolder(source)

    def _folder_source_exists(self, source: str) -> bool:
        return resolve_folder_source_exists(
            source=source,
            roots_by_id=self._roots_by_id,
            library_folders_fn=self._library.folders,
        )

    def _select_revealed_row(self, tab_id: str, track_id: str) -> None:
        """Select the first row of the tab that shows this track, now or when rows arrive."""
        model = self._active_track_model(tab_id)
        if model is not None:
            found_row = find_revealed_track_row(model.rows_snapshot(), track_id)
            if found_row is not None:
                self._explorer_coordinator.clear_pending_reveal()
                self.selectTrack(str(found_row["id"]), "single", [])
                return
        self._explorer_coordinator.set_pending_reveal(tab_id, track_id)

    @Slot(str, str, int)
    def movePlaylistEntry(self, source: str, entry: str, offset: int) -> None:
        can_reorder, err = can_reorder_playlist(self._tab_state(source))
        if not can_reorder:
            if err:
                self._set_message(err)
            return
        model = self._active_track_model(source)
        if model is None or self._playlists_model is None or source == "playlist:liked":
            return
        entries = model.track_ids_snapshot()
        reordered = move_playlist_entry(entries, entry, offset)
        if reordered == entries:
            return
        identity = source.partition(":")[2]
        version = self._playlists_model.details(identity).get("version", -1)
        self._playlists_model.reorder(identity, reordered, version)

    @Slot(str, str, str)
    def reorderPlaylistBefore(self, source: str, entry: str, before: str) -> None:
        version = (
            self._playlists_model.details(source.partition(":")[2]).get("version", -1)
            if self._playlists_model is not None
            else -1
        )
        self.reorderPlaylistEntries(source, [entry], before, version)

    @Slot(str, list, str, int)
    def reorderPlaylistEntries(
        self, source: str, entry_ids: list, before: str, expected_version: int
    ) -> None:
        can_reorder, err = can_reorder_playlist(self._tab_state(source))
        if not can_reorder:
            if err:
                self._set_message(err)
            return
        model = self._active_track_model(source)
        if (
            model is None
            or self._playlists_model is None
            or not source.startswith("playlist:")
            or source == "playlist:liked"
        ):
            return
        entries = model.track_ids_snapshot()
        identity = source.partition(":")[2]
        if self._playlists_model.details(identity).get("version", -1) != expected_version:
            self._set_message("This playlist changed. Refresh before reordering.")
            return
        try:
            next_entries = reorder_playlist_items(entries, [str(i) for i in entry_ids], before)
        except ValueError as error:
            self._set_message(str(error))
            return
        if next_entries != entries:
            self._playlists_model.reorder(identity, next_entries, expected_version)

    @Slot(str)
    def customPlaylistOrder(self, tab_id: str) -> None:
        state = self._tab_state(tab_id)
        set_custom_playlist_order(state)
        self._capture_navigation()
        self._scan_coordinator.mark_tab_dirty(tab_id)
        self._revision += 1
        self.libraryChanged.emit()
        self.layoutChanged.emit()
        self._refresh_timer.start()
        self._persist()

    @Slot(str, bool)
    def playPlaylist(self, identity: str, shuffled: bool) -> None:
        """Play a whole playlist (or Liked tracks) from the Playlists window (plan 132.4)."""
        if self._playlists_model is not None:
            self._playlists_model.play(identity, shuffled)

    @Slot(str, list, bool)
    def playPlaylistRows(self, identity: str, rows: list, shuffled: bool) -> None:
        available = prepare_playlist_playback_rows(rows, shuffled=shuffled)
        if available and self._player is not None:
            ids = [str(r["id"]) for r in available]
            detail = self._playlists_model.details(identity) if self._playlists_model else {}
            self._player.playQueueWithRows(
                ids, 0, "playlist:" + identity, str(detail.get("name", "Playlist")), available
            )
        elif not available:
            self._set_message("There are no available tracks in these results.")

    @Slot(list, str, list)
    def enqueueTracks(self, identities: list, source: str, rows: list) -> None:
        """Capture visible identities and prepare local rows outside the UI thread."""
        self._request_enqueue([str(value) for value in identities], source, rows, False)

    @Slot(str)
    def enqueuePlaylist(self, identity: str) -> None:
        """Add the full playlist in its own order, regardless of the active filter."""
        self._request_enqueue([], "playlist:" + identity, [], True)

    def _request_enqueue(
        self, identities: list[str], source: str, rows: list, entire_playlist: bool
    ) -> None:
        if self._player is None:
            self._set_message("The audio runtime is unavailable.")
            return
        sequence = self._enqueue_tracker.next_sequence()
        captured_rows = [dict(row) for row in rows if isinstance(row, dict)]
        playlist_service = self._playlists_model.service if self._playlists_model else None
        playlist_id = source.partition(":")[2] if source.startswith("playlist:") else ""
        detail = (
            self._playlists_model.details(playlist_id)
            if playlist_id and self._playlists_model
            else {}
        )
        source_title = str(detail.get("name", "Playlist")) if playlist_id else source
        plugin_kind, _, plugin_ref = source.partition(":")
        if self._plugin_ui.is_track_list_kind(plugin_kind):
            # The rows of a plugin list are not library tracks: the open list says which ones play.
            source_title = self._plugin_ui.tab_title(plugin_kind, plugin_ref)
            model = self._active_track_model(source)
            captured_rows = model.rows_snapshot() if model is not None else []

        def prepare(context: JobContext) -> None:
            try:
                if playlist_id and playlist_service is not None:
                    playlist_rows = playlist_service.rows(playlist_id)
                    if entire_playlist:
                        targets = playlist_rows
                    else:
                        lookup = {str(row.get("id", "")): row for row in playlist_rows}
                        targets = [lookup.get(identity, {}) for identity in identities]
                else:
                    supplied = {str(row.get("id", "")): row for row in captured_rows}
                    targets = [
                        supplied.get(identity) or self._library.track(identity)
                        for identity in identities
                    ]
                result = filter_enqueue_targets(
                    targets,
                    source=source,
                    source_title=source_title,
                    check_cancelled=context.raise_if_cancelled,
                )
                self.enqueuePrepared.emit(sequence, result)
            except Exception as error:
                self.enqueuePrepared.emit(sequence, {"error": str(error)})

        try:
            self._jobs.submit(
                prepare,
                label="Add playlist to queue" if entire_playlist else "Add tracks to queue",
                visible=entire_playlist or len(identities) > 100,
                summary=fixed(
                    "Playlist added to the queue"
                    if entire_playlist
                    else "Tracks added to the queue"
                ),
            )
        except RuntimeError as error:
            self.enqueuePrepared.emit(sequence, {"error": str(error)})

    @Slot(int, object)
    def _on_enqueue_prepared(self, sequence: int, result: object) -> None:
        ready_batches = self._enqueue_tracker.record_ready(sequence, result)
        for ready in ready_batches:
            if "error" in ready:
                self._set_message("Could not add to queue: " + str(ready["error"]))
                continue
            accepted = [dict(row) for row in ready.get("rows", [])]
            if accepted and self._player is not None:
                self._player.enqueue_tracks(
                    [str(row["id"]) for row in accepted],
                    source=str(ready.get("source", "")),
                    source_title=str(ready.get("source_title", "")),
                    tracks=accepted,
                )
            rejected = int(ready.get("rejected", 0))
            if rejected:
                self._set_message(
                    f"Added {len(accepted)} tracks; {rejected} unavailable tracks skipped."
                )
            elif not accepted:
                self._set_message("There are no available tracks to add to the queue.")

    @Property(list, notify=metadataChanged)
    def infoFields(self) -> list[dict[str, Any]]:
        return (
            cast(list[dict[str, Any]], self._metadata_editor.infoFields)
            if self._metadata_editor is not None
            else []
        )

    @Property(QObject, constant=True)
    def metadataEditor(self) -> QObject:
        return self._metadata_editor if self._metadata_editor is not None else self

    @Property(QObject, constant=True)
    def trashModel(self) -> QObject:
        return self._trash_model if self._trash_model is not None else self

    @Property(QObject, constant=True)
    def analysisSettings(self) -> QObject:
        return self._analysis_settings if self._analysis_settings is not None else self

    @Property(QObject, constant=True)
    def playbackSettings(self) -> QObject:
        return self._playback_settings if self._playback_settings is not None else self

    def attach_playback_settings(self, settings: PlaybackSettingsModel) -> None:
        """Show the loudness normalization choices of the Playback settings."""
        self._playback_settings = settings
        settings.setParent(self)

    def attach_play_log(self, play_log: PlayLogRepository) -> None:
        """Read the listening figures of the Plays and Last played columns and the details."""
        self._play_log = play_log

    @Slot()
    def refreshPlayStats(self) -> None:
        """Re-read the listening figures shown by the columns and the details, after a listening."""
        if self._play_log is None:
            return
        self.selectionChanged.emit()
        if not self._play_columns_visible() or not self._jobs.accepting:
            return
        self._scan_coordinator.mark_all_tabs_dirty()
        self._refresh_timer.start()

    @Property(QObject, notify=layoutChanged)
    def artistManager(self) -> QObject | None:
        """The artist manager plugin, absent in v0.1 until a plugin attaches it."""
        return self._artist_manager

    @Property(bool, constant=True)
    def pluginUiEnabled(self) -> bool:
        """Whether the Plugins entry and the plugin services exist in this build."""
        return plugin_ui_enabled()

    @Property(QObject, constant=True)
    def pluginUi(self) -> QObject:
        """What the running plugins contribute; every list is empty without a plugin."""
        return self._plugin_ui

    @Property(QObject, constant=True)
    def statusBar(self) -> QObject:
        """The items the plugins show in the status bar; empty without a plugin."""
        return self._status_bar

    @Property(QObject, notify=layoutChanged)
    def pluginsView(self) -> QObject | None:
        """The Plugins activity: installed plugins, the Marketplace and installs; ``None``."""
        return self._plugins_view

    @Property(QObject, constant=True)
    def tagConflicts(self) -> QObject:
        return self._tag_conflicts if self._tag_conflicts is not None else self

    @Property(list, notify=selectionChanged)
    def infoFieldsReadOnly(self) -> list[dict[str, str]]:
        ids = self.selected_ids_snapshot()
        if len(ids) != 1:
            return []
        return format_info_fields_read_only(self.track(ids[0]))

    @Property(list, notify=selectionChanged)
    def infoFile(self) -> list[dict[str, str]]:
        ids = self.selected_ids_snapshot()
        if len(ids) != 1:
            return []
        return format_info_file_fields(self.track(ids[0]))

    @Property(list, notify=selectionChanged)
    def infoListening(self) -> list[dict[str, str]]:
        """Plays and Last played of the single selected track, from the play log."""
        ids = self.selected_ids_snapshot()
        if len(ids) != 1 or self._play_log is None:
            return []
        return listening_details(self._play_log.track_play_stats([ids[0]]).get(ids[0]))

    @Property(str, notify=messageChanged)
    def message(self) -> str:
        return self._message

    @Property(list, constant=True)
    def expandedFolders(self) -> list[str]:
        return sorted(self._expanded)

    # -------------------------------------------------------------- queries

    @Slot(str, result=dict)
    def track(self, track_id: str) -> dict[str, Any]:
        return self._library.track(track_id)

    @Slot(str)
    def showInExplorer(self, track_id: str) -> None:
        """Ask Windows Explorer to select the track's current source file."""
        source = self._library.source_record(track_id)
        if source is None:
            self._set_message(
                self._library.non_file_refusal(track_id, "shown in Windows Explorer")
                or "This file is no longer in the library."
            )
            return
        try:
            self._shell_reveal.reveal(source.path)
        except (OSError, RuntimeError, ValueError) as error:
            self._set_message(f"Could not open this file in Windows Explorer: {error}")
            return
        self._set_message("Asked Windows Explorer to show this file.")

    def attach_metadata_editor(self, editor: MetadataEditorModel) -> None:
        """Attach the single editor shared by the inspector and Fullscreen player."""
        if self._metadata_editor is not None:
            raise RuntimeError("A metadata editor is already attached to this workspace.")
        self._metadata_editor = editor
        editor.setParent(self)
        editor.changed.connect(self.metadataChanged.emit)
        editor.sourceChanged.connect(self._on_metadata_changed)
        editor.noticeRaised.connect(self._set_message)
        self.selectionChanged.connect(editor.refresh_selection)
        self.selectionChanged.connect(self._prepare_visible_metadata)
        editor.refresh_selection()
        self._prepare_visible_metadata()

    # ---------------------------------------------------------------- core artists

    def attach_artist_index(self, service: ArtistIndexService) -> None:
        """Attach the core artist index: the Artists view, the artist links and artist tabs."""
        if self._artist_index is not None:
            raise RuntimeError("An artist index is already attached to this workspace.")
        self._artist_index = service
        self._artist_list = ArtistListModel(service, self, self._artist_sort)
        self._artist_list.sortChanged.connect(self._on_artist_sort_changed)
        service.indexChanged.connect(self._on_artist_index_changed)

    def _on_artist_sort_changed(self) -> None:
        """Keep the chosen order of the Artists list and save the workspace with it."""
        if self._artist_list is not None:
            self._artist_sort = str(self._artist_list.sortMode)
            self._persist()

    @Property(QObject, notify=layoutChanged)
    def artistList(self) -> QObject | None:
        """The artists of the library, filtered by the Artists sidebar; absent in the demo."""
        return self._artist_list

    @Property(int, notify=artistsChanged)
    def artistRevision(self) -> int:
        """Counts the finished index builds; a binding that reads artist facts depends on it."""
        return self._artist_revision

    @Slot(str, result=dict)
    def artistInfo(self, key: str) -> dict[str, Any]:
        """Header facts of an artist page: name, track count and the credits of each action."""
        service = self._artist_index
        entry = self._artist_entry(str(key))
        if service is None or entry is None:
            return {
                "key": str(key),
                "name": "",
                "trackCount": 0,
                "oneArtistCredits": [],
                "splitCredits": [],
            }
        return {
            "key": entry.key,
            "name": entry.name,
            "trackCount": entry.track_count,
            "oneArtistCredits": service.one_artist_credits(entry.key),
            "splitCredits": service.split_credits(entry.key),
        }

    @Slot(str)
    def makeArtistOneArtist(self, key: str) -> None:
        """ "This is one artist": keep the credits of this artist whole."""
        self._apply_artist_choice(str(key), one_artist=True)

    @Slot(str)
    def splitArtist(self, key: str) -> None:
        """ "Split into separate artists": cut the credits of this artist at every junction."""
        self._apply_artist_choice(str(key), one_artist=False)

    def _apply_artist_choice(self, key: str, *, one_artist: bool) -> None:
        service = self._artist_index
        if service is None or self._artist_entry(key) is None:
            return
        credits = service.one_artist_credits(key) if one_artist else service.split_credits(key)
        if not credits:
            self._set_message("This artist has no credit to change.")
            return
        if one_artist:
            service.make_one_artist(key)
        else:
            service.split_artist(key)
        # The index is rebuilt in the background. The artist the choice produces is opened
        # when that rebuild lands, in _on_artist_index_changed.
        origins, message = format_artist_decision_message(credits, one_artist=one_artist)
        self._pending_artist_choice = (key, origins)
        self._set_message(message)

    def _on_artist_index_changed(self) -> None:
        """Follow a finished index build: open the artist an action produced, refresh the tabs.

        When the action made the current artist disappear, the first artist that holds one
        of its credits is opened; the others stay in the sidebar list. An artist tab whose
        artist no longer exists is closed, the others show the rebuilt track list.
        """
        service = self._artist_index
        if service is None:
            return
        index = service.index
        previous, self._artist_index_seen = self._artist_index_seen, index
        self._artist_revision += 1
        self.artistsChanged.emit()
        pending, self._pending_artist_choice = self._pending_artist_choice, None

        effects = decide_artist_index_effects(
            previous_index=previous,
            new_index=index,
            pending_choice=pending,
            groups=self._groups,
            tab_states=self._tab_states,
            is_plugin_artist=self._is_plugin_artist,
        )

        for tab_id, new_title in effects.retitled_tabs:
            self._tab_state(tab_id)["title"] = new_title

        self._scan_coordinator.mark_tabs_dirty(effects.reloaded_tab_ids)

        if effects.opened_artist is not None:
            self.openArtistPage(effects.opened_artist[0], effects.opened_artist[1])

        for group_id, tab_id in effects.stale_tabs:
            self.closeTab(group_id, tab_id)

        if effects.reloaded_tab_ids:
            self._refresh_timer.start()

        if effects.retitled_tabs or effects.stale_tabs:
            self.layoutChanged.emit()

    def _artist_entry(self, key: str) -> ArtistEntry | None:
        return self._artist_index.index.entry(key) if self._artist_index is not None else None

    def _artist_track_ids(self, key: str) -> list[str]:
        """The tracks of an artist, read on the graphical thread before a job uses them."""
        if self._artist_entry(key) is None and self._is_plugin_artist(key):
            assert self._artist_manager is not None
            return list(self._artist_manager.service.repository.catalog_track_ids(key))
        return self._artist_index.tracks_of(key) if self._artist_index is not None else []

    def _is_plugin_artist(self, key: str) -> bool:
        """Whether ``key`` is an artist of the artist manager plugin and not of the core index."""
        return bool(self._artist_manager is not None and self._plugin_artist_name(key))

    def _plugin_artist_name(self, key: str) -> str:
        return self._artist_manager.artist_name(key) if self._artist_manager is not None else ""

    @Slot(str, result=bool)
    def isPluginArtistPage(self, key: str) -> bool:
        """Whether an artist page belongs to the plugin (behind the switch) and has its header."""
        return self._artist_entry(str(key)) is None and self._is_plugin_artist(str(key))

    def _artist_rows(self, track_ids: list[str]) -> list[dict[str, Any]]:
        """Rows of an artist page: by album, then track number, then title."""
        return sort_artist_tracks(self._library.tracks_by_ids(track_ids))

    def attach_artist_manager(self, model: Any) -> None:
        """Attach the artist manager; its file applications refresh the rows and the player."""
        if self._artist_manager is not None:
            raise RuntimeError("An artist manager is already attached to this workspace.")
        self._artist_manager = model
        model.setParent(self)
        model.tracksChanged.connect(self._on_artist_files_changed)
        model.noticeRaised.connect(self._set_message)

    @Property(QObject, notify=layoutChanged)
    def genreManager(self) -> QObject | None:
        """The plugin model is absent until the user opens Genre Manager."""
        return self._genre_manager_model

    def attach_genre_manager_factory(self, factory: Callable[[], QObject]) -> None:
        self._genre_manager_factory = factory

    @Slot(str, str)
    def openGenreManagerView(self, view: str, title: str) -> None:
        if view not in {"classify", "genres", "uncertain", "organize"}:
            return
        if self._genre_manager_model is None:
            if self._genre_manager_factory is None:
                self._set_message("Genre Manager is unavailable in this workspace.")
                return
            self._genre_manager_model = self._genre_manager_factory()
            self._genre_manager_model.setParent(self)
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._activity = "plugins"
        self._sidebar_visible = True
        self._open_special_tab(f"genre_manager:{view}", title)
        self._record_navigation()
        self.layoutChanged.emit()
        self._persist()

    @Slot(list)
    def _on_artist_files_changed(self, _track_ids: list) -> None:
        """Files were renamed or tagged: reload the rows, the inspector and the player."""
        self._reload_analysis_values()
        if self._player is not None and self._player.playing_id_value():
            self._player.refreshTrack(self._player.playing_id_value())

    def attach_trash_model(self, model: TrashModel) -> None:
        """Attach the dedicated Windows recycle model."""
        if self._trash_model is not None:
            raise RuntimeError("A trash model is already attached to this workspace.")
        self._trash_model = model
        model.setParent(self)
        model.tracksRecycled.connect(self._on_tracks_recycled)
        model.folderRecycled.connect(self._on_folder_recycled)
        model.attach_delete_choices(self._plugin_ui)  # what plugins add to the confirmation

    def attach_file_move_model(self, model: FileMoveModel) -> None:
        """Attach the model that moves dragged files between library folders."""
        if self._file_move_model is not None:
            raise RuntimeError("A file move model is already attached to this workspace.")
        self._file_move_model = model
        model.setParent(self)
        model.tracksMoved.connect(self._on_tracks_moved)
        model.tracksCopied.connect(self._on_tracks_copied)
        model.tracksRenamed.connect(self._on_tracks_renamed)
        model.folderChanged.connect(self._on_folder_changed)
        model.noticeRaised.connect(self._set_message)

    def attach_plugin_host(self, host: PluginHost) -> None:
        """Show the notices of the plugins on the message line."""
        host.setParent(self)
        host.noticeRaised.connect(self._set_message)
        host.uiRefreshRequested.connect(self._plugin_ui.refresh)
        host.dialogRequested.connect(self._plugin_ui.open_dialog)
        host.tabRequested.connect(self.openPluginTab)
        host.availabilityChanged.connect(self._on_availability_changed)
        host.attach_status_bar(self._status_bar)

    def attach_availability(
        self, registry: TrackAvailabilityRegistry, settings: SettingsRepository
    ) -> None:
        """Let the track lists leave out the tracks a plugin reports as not on this device."""
        self._availability.attach(registry, settings)
        self.availabilityFilterChanged.emit()
        self._refresh_track_models(None)

    @Property(bool, notify=availabilityFilterChanged)
    def availabilityProvided(self) -> bool:
        """Whether a running plugin provides track availability; the filter is offered then."""
        return self._availability.provided

    @Property(bool, notify=availabilityFilterChanged)
    def hideNotOnDevice(self) -> bool:
        """The choice "Hide tracks not on this device", one value for every track list."""
        return self._availability.wanted

    @Slot(bool)
    def setHideNotOnDevice(self, hide: bool) -> None:
        self._availability.set_wanted(bool(hide))
        self.availabilityFilterChanged.emit()
        self._refresh_track_models(None)

    @Slot(object)
    def _on_availability_changed(self, track_ids: object) -> None:
        """A plugin says the availability of some tracks (None: all) changed; ask again."""
        changed = {str(item) for item in track_ids} if isinstance(track_ids, list | tuple) else None
        self._refresh_track_models(changed)

    def _refresh_track_models(self, changed: set[str] | None) -> None:
        for model in tuple(self._track_models.values()):
            model.refresh_filter(changed)

    def attach_plugins_view(self, model: PluginsViewModel) -> None:
        """Attach the Plugins activity; its detail tabs and notices come back to this workspace."""
        self._plugins_view = model
        model.setParent(self)
        model.detailRequested.connect(self.openPluginDetail)
        model.noticeRaised.connect(self._set_message)

    @Slot(str, str)
    def openPluginDetail(self, plugin_id: str, title: str) -> None:
        """Open, or focus, the detail tab of a plugin (tab kind ``plugin``, ref = plugin id)."""
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._open_special_tab(f"plugin:{plugin_id}", title)
        self._record_navigation()
        self.layoutChanged.emit()
        self._persist()

    def register_plugins(
        self, plugins: Sequence[LoadedPlugin], settings: SettingsRepository | None
    ) -> None:
        """Show what the running plugins contribute, once they are loaded.

        A saved plugin activity that no running plugin provides falls back to the Explorer.
        """
        self._plugin_ui.register(plugins, settings)
        self._status_bar.register(plugins)
        if "." in self._activity and not self._plugin_ui.has_activity(self._activity):
            self._activity = "explorer"
            self._persist()
        self.layoutChanged.emit()

    @Slot(str, str)
    def openPluginTab(self, kind: str, ref: str) -> None:
        """Open a tab of a plugin's ``TabKind``, as a preview tab like a playlist."""
        if not self._plugin_ui.is_plugin_kind(kind):
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        tab_id = f"{kind}:{ref}"
        state = self._ensure_tab(tab_id)
        state["title"] = self._plugin_ui.tab_title(kind, ref)
        state["icon"] = self._plugin_ui.tab_icon(kind)
        group = self._groups[self._active_group]
        self._place_tab(self._active_group, tab_id, preview=True)
        group["active"] = tab_id
        self._load_group_view(self._active_group)
        self._record_navigation()
        self._scan_coordinator.mark_tab_dirty(tab_id)
        self._refresh_timer.start()
        self.layoutChanged.emit()
        self.selectionChanged.emit()

    @Slot()
    def _refresh_plugin_lists(self) -> None:
        """A plugin's data changed: the open playlists and plugin lists read their rows again."""
        for tab_id, state in self._tab_states.items():
            kind = state.get("kind")
            if kind == "playlist" or self._plugin_ui.is_track_list_kind(str(kind)):
                self._scan_coordinator.mark_tab_dirty(tab_id)
        self._refresh_timer.start()

    @Slot(str, str, list, bool)
    def playPluginRows(self, kind: str, ref: str, rows: list, shuffled: bool) -> None:
        """Play the rows of a plugin list that have a local file; the others are skipped."""
        available = prepare_playlist_playback_rows(rows, shuffled=shuffled)
        if available and self._player is not None:
            ids = [str(row["id"]) for row in available]
            title = self._plugin_ui.tab_title(kind, ref)
            self._player.playQueueWithRows(ids, 0, f"{kind}:{ref}", title, available)
        elif not available:
            self._set_message("There are no available tracks in these results.")

    @Slot(str, list, result=list)
    def pluginTrackActions(self, source: str, ids: list) -> list[dict[str, Any]]:
        """The menu entries the plugins offer for the selected rows of a list."""
        return self._plugin_ui.track_action_items(self._rows_of(source, ids))

    @Slot(str, list, str)
    def runPluginTrackAction(self, source: str, ids: list, key: str) -> None:
        self._plugin_ui.run_track_action(key, self._rows_of(source, ids))

    def _rows_of(self, source: str, ids: Sequence[object]) -> list[dict[str, Any]]:
        """The rows of the open list ``source`` that carry these identifiers."""
        model = self._active_track_model(source)
        wanted = {str(identity) for identity in ids}
        return [row for row in model.rows_snapshot() if str(row["id"]) in wanted] if model else []

    @Slot(list, str)
    def moveTracksToFolder(self, track_ids: list, folder_id: str) -> None:
        """Move the files of these tracks into a library folder, without overwriting."""
        if self._file_move_model is None:
            self._set_message("Moving files is not available.")
            return
        target = resolve_folder_drop_target(folder_id, self._roots_by_id)
        if target is None:
            self._set_message("Drop the files on a folder of the library.")
            return
        root_id, relative, name = target
        self._file_move_model.move_tracks(track_ids, root_id, relative, name)

    @Slot(str)
    def requestRenameFile(self, track_id: str) -> None:
        """Ask the window for the new name of a track's file (``renameFileRequested``)."""
        source = self._library.source_record(str(track_id))
        if source is None:
            self._set_message(
                self._library.non_file_refusal(str(track_id), "renamed")
                or "This file is no longer in the library."
            )
            return
        self.renameFileRequested.emit(str(track_id), source.path.stem)

    @Slot(str, str)
    def renameTrackFile(self, track_id: str, new_base_name: str) -> None:
        """Rename a track's file in its folder, keeping its extension, as a job.

        The new name must not contain a path separator or a name reserved by Windows, and must
        not be the name of another file of the folder; a refusal is shown on the message line
        and nothing changes on disk.
        """
        if self._file_move_model is None:
            self._set_message("Renaming files is not available.")
            return
        self._file_move_model.rename_track(str(track_id), str(new_base_name))

    @Slot(object)
    def _on_tracks_renamed(self, _renamed: object) -> None:
        """A file changed name: reload the tree, the open lists and the inspector."""
        self._refresh_library()
        self.metadataChanged.emit()

    @Slot(object)
    def _on_tracks_moved(self, _moved: object) -> None:
        """Files changed folder: reload the tree, the open lists and the inspector."""
        self._drop_moved_rows(_moved)
        self._refresh_library()
        self.metadataChanged.emit()

    @Slot(object)
    def _on_tracks_copied(self, copied: object) -> None:
        """Files were copied into a folder: the library reads the new files there."""
        if not isinstance(copied, dict):
            return
        root_id = str(copied.get("rootId", ""))
        relative = str(copied.get("relative", ""))
        self._refresh_library(root_id, {relative})
        self._request_folder_refresh(root_id, relative)

    def _drop_moved_rows(self, moved: object) -> None:
        """Take moved tracks out of the open folder lists at once.

        The reload that follows reads through worker connections that can take a while to
        open; until its rows arrive, a list must not keep showing a file that left the folder.
        Rows of a read already running are dropped too: that read may predate the move.
        """
        if not isinstance(moved, list):
            return
        moved_ids = {str(item.get("trackId", "")) for item in moved if isinstance(item, dict)}
        moved_ids.discard("")
        for model_key, model in tuple(self._track_models.items()):
            group_id, tab_id = self._model_identity(model_key)
            state = dict(self._tab_state(tab_id))
            state.update(self._group_tab_states.get((group_id, tab_id), {}))
            if state.get("kind") != "folder":
                continue
            job_id = self._track_tracker.cancel_and_release(model_key)
            if job_id:
                with suppress(LookupError, ValueError):
                    self._jobs.cancel(JobId.parse(job_id))
            model.replace(
                [row for row in model.source_rows_snapshot() if str(row["id"]) not in moved_ids]
            )

    def attach_analysis(
        self,
        settings: AnalysisSettingsModel,
        model: AnalysisModel,
        conflicts: TagConflictsModel,
    ) -> None:
        """Attach the analysis settings, the model that launches analysis jobs and the
        list of tag conflicts those jobs leave for the user to resolve."""
        if self._analysis_model is not None:
            raise RuntimeError("An analysis model is already attached to this workspace.")
        self._analysis_settings = settings
        self._analysis_model = model
        self._tag_conflicts = conflicts
        model.setParent(self)
        conflicts.setParent(self)
        model.conflictFound.connect(conflicts.add)
        conflicts.noticeRaised.connect(self._set_message)
        conflicts.resolved.connect(self._on_metadata_changed)
        model.resultsChanged.connect(self._on_analysis_results)
        model.noticeRaised.connect(self._set_message)
        settings.changed.connect(self._on_analysis_display_changed)
        self._apply_analysis_display()

    def _apply_analysis_display(self) -> None:
        if self._analysis_settings is not None:
            current = self._analysis_settings.settings
            self._library.set_analysis_display(current.notation, current.bpm_decimals)

    @Slot(list, bool)
    def analyzeTracks(self, track_ids: list, force: bool) -> None:
        """Analyze tracks on demand; ``force`` recomputes those already analyzed."""
        if self._analysis_model is not None:
            self._analysis_model.analyzeTracks(track_ids, force)

    @Slot(str, bool)
    def analyzeFolder(self, folder_id: str, force: bool) -> None:
        """Analyze a folder and everything inside it, recursively."""
        if self._analysis_model is None:
            return
        target = resolve_analyze_folder_target(str(folder_id))
        if target is None:
            self._set_message("This folder cannot be analyzed.")
            return
        self._analysis_model.analyzeTree(target[0], target[1], force)

    @Slot(list)
    def _on_analysis_results(self, track_ids: list) -> None:
        self._reload_analysis_values()
        playing = self._player.playing_id_value() if self._player is not None else ""
        if playing and playing in track_ids and self._player is not None:
            self._player.refreshTrack(playing)

    @Slot()
    def _on_analysis_display_changed(self) -> None:
        self._apply_analysis_display()
        self._reload_analysis_values()

    def _reload_analysis_values(self) -> None:
        """Reload the rows and the inspector so calculated values appear."""
        self._revision += 1
        self._scan_coordinator.mark_all_tabs_dirty()
        self.libraryChanged.emit()
        self.metadataChanged.emit()
        self._refresh_timer.start()

    @Slot(object)
    def _on_tracks_recycled(self, recycled: object) -> None:
        affected = extract_recycled_affected_folders(recycled)
        for root_id, folders in affected.items():
            self._scan_coordinator.mark_dirty_library(root_id, folders)
        if affected:
            self._revision += 1
            self.libraryChanged.emit()
            self._refresh_timer.start()

    def refresh_after_track_files(self) -> None:
        """Read the library views again after the file or the source of plugin tracks changed.

        Same signal as a scan that changes tracks (``libraryChanged``): the folder tree, the open
        track lists and the inspector are read again. The folders of the tracks are not known
        here, so every tab is marked dirty. Graphical thread (the host queues the call there).
        """
        self._scan_coordinator.mark_dirty_library()
        self._refresh_library()
        self.metadataChanged.emit()
        self._refresh_timer.start()

    @Slot(str, str, str, str, bool, result=QObject)
    @Slot(str, str, str, str, bool, str, result=QObject)
    def trackModelForTab(
        self,
        tab_id: str,
        kind: str,
        ref: str,
        sort_key: str,
        ascending: bool,
        group_id: str = "",
    ) -> QObject:
        group = group_id or self._active_group
        model_key = self._model_key(group, tab_id)
        model = self._track_models.get(model_key)
        if model is None:
            model = TrackListModel(self)
            model.set_hidden_ids(self._availability.remote_ids)
            self._track_models[model_key] = model
        if kind in {"folder", "playlist", "artist"} or self._plugin_ui.is_track_list_kind(kind):
            self._request_track_rows(model_key, tab_id, group, kind, ref, sort_key, ascending)
        else:
            model.replace([])
        return model

    def _request_track_rows(
        self,
        model_key: str,
        tab_id: str,
        group_id: str,
        kind: str,
        ref: str,
        sort_key: str,
        ascending: bool,
    ) -> None:
        key = compute_track_request_key(
            self._tab_state(tab_id),
            self._group_tab_states.get((group_id, tab_id)),
            kind,
            ref,
            sort_key,
            ascending,
        )
        if self._track_tracker.is_current_request(model_key, key):
            return
        pending = self._explorer_coordinator.pending
        if pending is not None and pending["tab_id"] == tab_id and pending["group"] == group_id:
            self._cancel_explorer_track_action()
        generation, previous_job = self._track_tracker.next_generation(model_key, key)
        if previous_job:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(previous_job))
        # Read on the GUI thread, before the job starts: the job never reads the preferences.
        plugin_list = self._plugin_ui.is_track_list_kind(kind)
        add_play_stats = kind != "playlist" and not plugin_list and self._needs_play_stats(sort_key)
        # The index is read here, on the graphical thread, and the job gets its own copy.
        artist_ids = self._artist_track_ids(ref) if kind == "artist" else []
        query = key[4]

        def read_rows(context: JobContext) -> None:
            context.raise_if_cancelled()
            if kind == "playlist" and self._playlists_model is not None:
                rows = self._plugin_ui.decorate(self._playlists_model.service.rows(ref), kind, ref)
            elif plugin_list:
                rows = self._plugin_ui.decorate(
                    self._plugin_ui.track_rows(kind, ref, self._library.track), kind, ref
                )
            elif kind == "artist":
                rows = self._artist_rows(artist_ids)
            else:
                root_id, relative = parse_folder_ref(ref)
                rows = self._library.tracks_in_folder(root_id, relative)
            if query:
                rows = filter_track_rows(rows, query)
            if add_play_stats and self._play_log is not None:
                # One batched query per tab load, off the graphical thread.
                stats = self._play_log.track_play_stats(str(row.get("id", "")) for row in rows)
                rows = with_play_stats(rows, stats)
            ordered = order_track_rows(rows, sort_key, ascending)
            context.raise_if_cancelled()
            self.trackRowsReady.emit(model_key, generation, ordered)

        job_id = self._jobs.submit(
            read_rows,
            label="Load folder contents",
            visible=False,
            summary=fixed("Folder contents loaded"),
        )
        self._track_tracker.record_job(model_key, str(job_id))

    def _play_columns_visible(self) -> bool:
        hidden = set(self._column_preferences.get("hidden", ()))
        return any(key not in hidden for key in PLAY_COLUMN_KEYS)

    def _needs_play_stats(self, sort_key: str) -> bool:
        """Listening figures are read only when a column shows them or a sort uses them."""
        return needs_play_stats(
            sort_key,
            self._column_preferences.get("hidden", ()),
            self._play_log is not None,
        )

    @Slot(str, int, object)
    def _on_track_rows_ready(self, model_key: str, generation: int, rows: object) -> None:
        if not self._track_tracker.is_generation_valid(model_key, generation):
            return
        group_id, tab_id = self._model_identity(model_key)
        model = self._track_models.get(model_key)
        if model is None or not isinstance(rows, list):
            return
        self._track_tracker.on_rows_ready(model_key)
        model.replace(rows)
        revealed_track_id = self._explorer_coordinator.consume_pending_reveal_for_tab(tab_id)
        if revealed_track_id is not None and self._groups[self._active_group]["active"] == tab_id:
            self._select_revealed_row(tab_id, revealed_track_id)
            self._explorer_coordinator.clear_pending_reveal()
        if group_id in self._groups and self._groups[group_id]["active"] == tab_id:
            resolved = self._nav.consume_pending(
                group_id,
                tab_id,
                set(model.track_ids_snapshot()),
            )
            if resolved is not None:
                self._selection_by_tab[(group_id, tab_id)] = resolved
                self.selectionChanged.emit()
        pending = self._explorer_coordinator.pending
        if (
            pending is not None
            and pending["stage"] == "rows"
            and pending["tab_id"] == tab_id
            and pending["group"] == group_id
            and pending["rows_generation"] == generation
        ):
            self._complete_explorer_track_action(pending, model)

    def _request_folder_roots(self) -> None:
        self._folder_root_generation += 1
        generation = self._folder_root_generation
        if self._folder_root_job_id:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(self._folder_root_job_id))

        def read_roots(context: JobContext) -> None:
            try:
                context.raise_if_cancelled()
                roots = self._library.roots()
                context.raise_if_cancelled()
                self.folderRootsReady.emit(generation, roots, None)
            except JobCancelledError:
                raise
            except Exception as error:
                self.folderRootsReady.emit(generation, None, str(error))
                raise

        job_id = self._jobs.submit(
            read_roots,
            label="Load library folders",
            visible=False,
            summary=fixed("Library folders loaded"),
        )
        self._folder_root_job_id = str(job_id)

    @Slot(int, object, object)
    def _on_folder_roots_ready(self, generation: int, roots: object, error: object) -> None:
        if generation != self._folder_root_generation:
            return
        self._folder_root_job_id = ""
        if not isinstance(roots, list):
            self._set_message(f"Could not load library folders: {error or 'unknown error'}")
            return
        self._roots_by_id = {
            str(root.get("id", "")): dict(root) for root in roots if isinstance(root, dict)
        }
        self._folder_model.set_roots(roots)
        if not self._folder_tabs_checked:
            # Once, at the first list of sources after the start: the tabs of the last session.
            self._folder_tabs_checked = True
            self._drop_missing_folder_tabs()
        for folder_id in self._expanded:
            self._folder_model.set_expanded(folder_id, True)
        self.explorerChanged.emit()
        self._sync_folder_watches()
        for folder_id in tuple(self._expanded):
            if self._folder_model.is_expanded(folder_id) and not self._folder_model.branch_loaded(
                folder_id
            ):
                self._request_folder_branch(folder_id)
        if self._resume_roots_requested:
            self._resume_roots_requested = False
            for root_id in tuple(self._roots_by_id):
                self._start_root_scan(root_id, quiet=True)

    def _request_folder_branch(self, folder_id: str) -> None:
        if not self._folder_model.is_expanded(folder_id):
            return
        if self._folder_model.branch_loaded(folder_id):
            return
        if self._branch_tracker.is_in_flight(folder_id):
            return
        parsed = parse_folder_id(folder_id)
        if parsed is None:
            return
        root_id, relative = parsed
        generation = self._branch_tracker.next_generation(folder_id)
        self._folder_model.set_loading(folder_id, True)

        def read_branch(context: JobContext) -> None:
            try:
                context.raise_if_cancelled()
                rows = self._library.folder_children(root_id, relative)
                context.raise_if_cancelled()
                self.folderBranchReady.emit(folder_id, generation, rows, None)
            except JobCancelledError:
                raise
            except Exception as error:
                self.folderBranchReady.emit(folder_id, generation, None, str(error))
                raise

        job_id = self._jobs.submit(
            read_branch,
            label="Load folder contents",
            visible=False,
            summary=fixed("Folder contents loaded"),
        )
        self._branch_tracker.record_job(folder_id, str(job_id))

    @Slot(str, int, object, object)
    def _on_folder_branch_ready(
        self, folder_id: str, generation: int, rows: object, error: object
    ) -> None:
        if not self._branch_tracker.is_current_generation(folder_id, generation):
            return
        self._branch_tracker.finish_job(folder_id)
        if not self._folder_model.is_expanded(folder_id) or not isinstance(rows, list):
            self._folder_model.set_loading(folder_id, False)
            if error is not None:
                self._set_message(f"Could not load this folder: {error}")
            return
        self._folder_model.set_branch(folder_id, rows)
        self.explorerChanged.emit()

    @Slot(str, str, str, bool, int, result=list)
    def tabTracks(
        self, kind: str, ref: str, sort_key: str, ascending: bool, _revision: int = 0
    ) -> list[dict[str, Any]]:
        if kind != "folder":
            return []
        tab_id = f"folder:{ref}"
        model = self._active_track_model(tab_id)
        if model is None:
            self._request_track_rows(
                self._model_key(self._active_group, tab_id),
                tab_id,
                self._active_group,
                kind,
                ref,
                sort_key,
                ascending,
            )
            return []
        return model.rows_snapshot()

    @Slot(str, str, int, result=str)
    def tabSummary(self, kind: str, ref: str, _revision: int = 0) -> str:
        if kind != "folder":
            return ""
        root_id, relative = parse_folder_ref(ref)
        count, size, duration_us = self._library.folder_stats(root_id, relative)
        seconds = round(duration_us / 1_000_000)
        total = (
            f"{seconds // 3600} h {(seconds % 3600) // 60:02d} min"
            if seconds >= 3600
            else f"{seconds // 60} min"
        )
        size_text = (
            f"{size / (1024**3):.1f} GB" if size >= 1024**3 else f"{size / (1024**2):.1f} MB"
        )
        return f"{count} titles · {total} · {size_text}"

    @Slot(str, int, result=list)
    def playlistsContaining(self, _track_id: str, _revision: int = 0) -> list[str]:
        return self._playlists_model.containing(_track_id) if self._playlists_model else []

    # -------------------------------------------------------------- roots and scans

    @Slot(str, result=str)
    def addRoot(self, selected: str) -> str:
        path = local_path(selected)
        if not path:
            return ""
        source = Path(path)
        if not source.is_dir():
            self._set_message("Choose an existing folder.")
            return ""
        root = self._library.add_root(source)
        root_id = str(root["id"])
        self._roots_by_id[root_id] = dict(root)
        self._expanded.add(f"root:{root_id}")
        self._open_folder(root_id, "")
        self._refresh_library(root_id, {""})
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self.rescanRoot(root_id)
        self._persist()
        return root_id

    @Slot(str, result=str)
    def rescanRoot(self, root_id: str) -> str:
        return self._start_root_scan(root_id, quiet=False)

    @Slot(str)
    def removeRoot(self, root_id: str) -> None:
        """Remove a source from the library (U12): its files stay, its tracks keep their data.

        The scan and folder refresh jobs of the source are cancelled, its folder tabs close, the
        watcher follows the layout, and playlists show its tracks as unavailable.
        """
        root = self._roots_by_id.get(root_id)
        if root is None:
            self._set_message("This folder is no longer in the library.")
            return
        for job_id in self._scan_coordinator.forget_root(root_id):
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(job_id))
        self._close_folder_tabs(f"folder:{root_id}")
        self._library.remove_root(root_id)
        del self._roots_by_id[root_id]
        self._expanded = {
            item
            for item in self._expanded
            if item != f"root:{root_id}" and not self._within_folder(item, f"folder:{root_id}")
        }
        self._refresh_library(root_id, {""})
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()
        self._set_message(
            f"Removed “{root['name']}” from the library. Your files stay on disk; "
            "analysis and edits are kept if you add the folder again."
        )

    @staticmethod
    def _within_folder(ref: str, prefix: str) -> bool:
        """Whether a folder id or tab id is ``prefix`` itself or a folder under it."""
        return ref == prefix or ref.startswith(prefix + "/")

    def _close_folder_tabs(self, prefix: str) -> list[tuple[str, str]]:
        """Close every tab that shows the folder ``prefix`` or a folder under it.

        Returns the (window, tab) pairs closed. A window that empties and goes is skipped.
        """
        closed: list[tuple[str, str]] = []
        for group_id in tuple(self._groups):
            if group_id not in self._groups:
                continue
            for tab_id in tuple(self._groups[group_id]["tabs"]):
                if group_id not in self._groups or tab_id not in self._groups[group_id]["tabs"]:
                    continue
                if self._within_folder(tab_id, prefix):
                    self.closeTab(group_id, tab_id)
                    closed.append((group_id, tab_id))
        return closed

    @Slot(str, str)
    def createFolder(self, parent_folder_id: str, name: str) -> None:
        """Create a folder inside a source or a folder, on disk, as a job (plan 132.2)."""
        parsed = parse_folder_id(parent_folder_id)
        if parsed is None or self._file_move_model is None:
            self._set_message("Folders cannot be created here.")
            return
        root_id, relative = parsed
        self._file_move_model.create_folder(root_id, relative, name)

    @Slot(str)
    def createUnnamedFolder(self, parent_folder_id: str) -> None:
        """Create "Unnamed folder NN" in a source or folder at once, with no name prompt."""
        parsed = parse_folder_id(parent_folder_id)
        if parsed is None or self._file_move_model is None:
            self._set_message("Folders cannot be created here.")
            return
        root_id, relative = parsed
        self._file_move_model.create_unnamed_folder(root_id, relative)

    @Slot(str, str)
    def renameFolder(self, folder_id: str, name: str) -> None:
        """Rename a folder of a source on disk; open tabs follow it (plan 132.2)."""
        parsed = parse_folder_id(folder_id)
        if parsed is None or self._file_move_model is None:
            self._set_message("Folders cannot be renamed here.")
            return
        root_id, relative = parsed
        if not relative:
            self._set_message("A source is removed from the library, not renamed.")
            return
        self._file_move_model.rename_folder(root_id, relative, name)

    @Slot(str)
    def recycleFolder(self, folder_id: str) -> None:
        """Ask to send a folder with everything in it to the Recycle Bin (plan 132.2)."""
        parsed = parse_folder_id(folder_id)
        if parsed is None or self._trash_model is None:
            self._set_message("Folders cannot be recycled here.")
            return
        root_id, relative = parsed
        self._trash_model.request_recycle_folder(root_id, relative)

    @Slot(list, str)
    def copyTracksToFolder(self, track_ids: list, folder_id: str) -> None:
        """Copy the files of these tracks into a library folder, without overwriting."""
        if self._file_move_model is None:
            self._set_message("Copying files is not available.")
            return
        target = resolve_folder_drop_target(folder_id, self._roots_by_id)
        if target is None:
            self._set_message("Drop the files on a folder of the library.")
            return
        root_id, relative, name = target
        self._file_move_model.copy_tracks(track_ids, root_id, relative, name)

    @Property(int, notify=clipboardChanged)
    def clipboardCount(self) -> int:
        """How many tracks Ctrl+C or Ctrl+X holds."""
        return len(self._track_clipboard.track_ids)

    @Slot(list, list, str, bool)
    def setTrackClipboard(self, track_ids: list, entry_ids: list, source: str, cut: bool) -> None:
        """Ctrl+C (``cut`` false) or Ctrl+X: hold a reference to the selected tracks."""
        ids = tuple(dict.fromkeys(str(identity) for identity in track_ids if str(identity)))
        if not ids:
            return
        self._track_clipboard = TrackClipboard(
            ids, tuple(str(entry) for entry in entry_ids if str(entry)), str(source), bool(cut)
        )
        self.clipboardChanged.emit()
        count = len(ids)
        verb = "Cut" if cut else "Copied"
        self._set_message(f"{verb} {count} track{'s' if count != 1 else ''}.")

    @Slot(str, str)
    def pasteTracks(self, target_kind: str, target_ref: str) -> None:
        """Ctrl+V in the list ``target_kind:target_ref``: add, copy or move what was held."""
        clipboard = self._track_clipboard
        plan = plan_paste(clipboard, target_kind, target_ref)
        if self._apply_track_plan(plan, target_kind, target_ref) and clipboard.cut:
            self._track_clipboard = TrackClipboard()
            self.clipboardChanged.emit()

    @Slot(list, str, str, str, bool)
    def dropTracksOnList(
        self, track_ids: list, source: str, target_kind: str, target_ref: str, copy: bool
    ) -> None:
        """Tracks dragged from a list and dropped on another one (``copy``: Ctrl was held)."""
        ids = tuple(dict.fromkeys(str(identity) for identity in track_ids if str(identity)))
        plan = plan_drop(ids, str(source), target_kind, target_ref, bool(copy))
        self._apply_track_plan(plan, target_kind, target_ref)

    def _apply_track_plan(self, plan: PastePlan, target_kind: str, target_ref: str) -> bool:
        """Carry out a paste or a drop; return whether something was started."""
        if plan.action == "none":
            if plan.message:
                self._set_message(plan.message)
            return False
        ids = list(plan.track_ids)
        if plan.action == "add":
            if self._playlists_model is None:
                self._set_message("Playlists are not available.")
                return False
            self._playlists_model.add(target_ref, ids)
            if plan.remove_from and plan.remove_entries:
                self._playlists_model.remove(plan.remove_from, list(plan.remove_entries))
            name = str(self._playlists_model.details(target_ref).get("name", "the playlist"))
            count = len(ids)
            self._set_message(f"Added {count} track{'s' if count != 1 else ''} to {name}.")
            return True
        folder_id = f"folder:{target_ref}"
        if plan.action == "copy":
            self.copyTracksToFolder(ids, folder_id)
        else:
            self.moveTracksToFolder(ids, folder_id)
        return True

    @Slot(str)
    def openFolderInExplorer(self, folder_id: str) -> None:
        """Show a folder of a source in Windows Explorer."""
        parsed = parse_folder_id(folder_id)
        root = self._roots_by_id.get(parsed[0]) if parsed else None
        if parsed is None or root is None:
            self._set_message("This folder is no longer in the library.")
            return
        target = Path(str(root["path"])) / parsed[1]
        try:
            self._shell_reveal.open_folder(target)
        except (OSError, RuntimeError, ValueError) as error:
            self._set_message(f"Could not open this folder in Windows Explorer: {error}")

    @Slot(object)
    def _on_folder_changed(self, payload: object) -> None:
        """A folder was created or renamed on disk: the tree and the open tabs follow."""
        if not isinstance(payload, dict):
            return
        root_id = str(payload.get("rootId", ""))
        relative = str(payload.get("relative", ""))
        if payload.get("action") == "created":
            parent = relative.rpartition("/")[0]
            self._expanded.add(f"folder:{root_id}/{parent}" if parent else f"root:{root_id}")
            self._refresh_library(root_id, {parent})
            if payload.get("startRename") is True:
                self.folderRenameRequested.emit(f"folder:{root_id}/{relative}")
        elif payload.get("action") == "renamed":
            previous = str(payload.get("previous", ""))
            self._follow_folder_rename(root_id, previous, relative)
            self._refresh_library(
                root_id, {previous.rpartition("/")[0], relative.rpartition("/")[0]}
            )
        self.layoutChanged.emit()
        self._persist()

    def _follow_folder_rename(self, root_id: str, previous: str, relative: str) -> None:
        """Re-open the tabs of a renamed folder, and its expanded branches, at the new path."""
        old_ref = f"folder:{root_id}/{previous}"
        new_ref = f"folder:{root_id}/{relative}"
        closed = self._close_folder_tabs(old_ref)
        for group_id, tab_id in closed:
            _, _, rest = tab_id.partition(old_ref)
            target = parse_folder_id(new_ref + rest)
            if target is None:
                continue
            window = group_id if group_id in self._groups else self._active_group
            self._open_folder(target[0], target[1], group_id=window)
        self._expanded = {
            new_ref + item[len(old_ref) :] if self._within_folder(item, old_ref) else item
            for item in self._expanded
        }

    @Slot(object)
    def _on_folder_recycled(self, payload: object) -> None:
        """A folder went to the Recycle Bin: its tabs close and the tree drops it."""
        if not isinstance(payload, dict):
            return
        root_id = str(payload.get("rootId", ""))
        relative = str(payload.get("relative", ""))
        ref = f"folder:{root_id}/{relative}"
        self._close_folder_tabs(ref)
        self._expanded = {item for item in self._expanded if not self._within_folder(item, ref)}
        self._refresh_library(root_id, {str(payload.get("parentRelative", ""))})
        self.layoutChanged.emit()
        self._persist()

    def _start_root_scan(self, root_id: str, *, quiet: bool) -> str:
        root = self._roots_by_id.get(root_id)
        if root is None:
            self._set_message("This folder is no longer in the library.")
            return ""
        request_id = os.urandom(16).hex()
        previous_job = self._scan_coordinator.prepare_scan_request(root_id, request_id, quiet=quiet)
        if previous_job:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(previous_job))
        generation = self._library.begin_scan(root_id, show_scanning=not quiet)
        self._refresh_library(root_id, {""})

        def task(context: JobContext) -> None:
            complete = False
            cancelled = False
            available = True
            issues: list[str] = []
            failure = ""
            seen = 0
            try:
                for batch in self._scanner.scan(
                    root["path"], is_cancelled=lambda: context.is_cancelled
                ):
                    issues.extend(issue.message for issue in batch.issues)
                    for issue in batch.issues:
                        context.report_failure(issue.path, issue.message)
                    seen += len(batch.entries)
                    last = batch.entries[-1].relative_path if batch.entries else ""
                    context.report_items(seen, None, last.rpartition("/")[0] or str(root["name"]))
                    changed_folders = self._library.upsert_folders(
                        root_id, batch.folders, generation
                    )
                    unchanged = self._library.unchanged_paths(
                        root_id,
                        [(entry.relative_path, entry.revision) for entry in batch.entries],
                    )
                    records: list[tuple[str, Path, Any, Any]] = []
                    for entry in batch.entries:
                        snapshot = (
                            None
                            if entry.relative_path in unchanged
                            else self._reader.read(entry.path)
                        )
                        records.append((entry.relative_path, entry.path, entry.revision, snapshot))
                    identities = self._library.upsert_locations(root_id, records, generation)
                    changed_parents = {
                        entry.relative_path.rpartition("/")[0]
                        for entry in batch.entries
                        if entry.relative_path not in unchanged
                    }
                    changed_parents.update(folder.rpartition("/")[0] for folder in changed_folders)
                    if changed_parents:
                        self.batchReady.emit(
                            root_id,
                            request_id,
                            {
                                "count": sum(bool(identity) for identity in identities),
                                "folders": sorted(changed_parents),
                            },
                        )
                    if batch.complete:
                        complete = True
                    if batch.cancelled:
                        cancelled = True
                        break
                available = Path(str(root["path"])).is_dir()
            except OSError as error:
                issues.append(str(error))
                available = Path(str(root["path"])).is_dir()
            except Exception as error:
                failure = f"{type(error).__name__}: {error}"
                issues.append(failure)
                raise
            finally:
                changed_folders = self._library.finish_scan(
                    root_id, generation, complete=complete, available=available
                )
                self.scanFinished.emit(
                    root_id,
                    request_id,
                    {
                        "complete": complete,
                        "cancelled": cancelled,
                        "available": available,
                        "issues": issues,
                        "error": failure,
                        "changedFolders": changed_folders,
                    },
                )
            if cancelled:
                raise JobCancelledError(request_id)

        job_id = self._jobs.submit(
            task,
            label=f"Indexing {root['name']}",
            summary=scan_summary(str(root["name"])),
            visible=not quiet,
            priority=-1 if quiet else 0,
        )
        self._scan_coordinator.record_scan_job(root_id, str(job_id))
        self._persist()
        return request_id

    @Slot()
    def resumeRoots(self) -> None:
        self._resume_roots_requested = True
        if not self._roots_by_id:
            self._request_folder_roots()
            return
        self._resume_roots_requested = False
        for root_id in tuple(self._roots_by_id):
            self._start_root_scan(root_id, quiet=True)

    @Slot(str)
    def toggleFolder(self, folder_id: str) -> None:
        self._cancel_explorer_track_action()
        if folder_id in self._expanded:
            self._expanded.remove(folder_id)
            self._folder_model.set_expanded(folder_id, False)
            job_id = self._branch_tracker.cancel_job(folder_id)
            if job_id:
                with suppress(LookupError, ValueError):
                    self._jobs.cancel(JobId.parse(job_id))
        else:
            self._expanded.add(folder_id)
            self._folder_model.set_expanded(folder_id, True)
            self._request_folder_branch(folder_id)
        self.explorerChanged.emit()
        self.layoutChanged.emit()
        self._persist()

    @Slot(str)
    def openFolder(self, folder_id: str) -> None:
        parsed = parse_folder_id(folder_id)
        if parsed is None:
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        if not self._open_folder(*parsed, preview=True):
            self._request_folder_refresh(*parsed)
            return
        self._record_navigation()
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(str, str)
    def selectExplorerTrack(self, track_id: str, folder_id: str) -> None:
        """Open a tree track's folder and select it only when it is in the listing."""
        self._leave_explorer_selection()
        self._explorer_anchor = str(track_id)
        self.selectionChanged.emit()
        self._request_explorer_track_action(track_id, folder_id, play=False)

    @Slot(str, str)
    def activateExplorerTrack(self, track_id: str, folder_id: str) -> None:
        """Reveal and play a tree track, or play it alone when the listing filters it out."""
        self._request_explorer_track_action(track_id, folder_id, play=True)

    def _request_explorer_track_action(self, track_id: str, folder_id: str, *, play: bool) -> None:
        parsed = parse_folder_id(folder_id)
        if parsed is None or not track_id:
            return

        root_id, relative = parsed
        source = f"folder:{root_id}/{relative}"
        if self._explorer_coordinator.should_ignore_request(
            track_id, source, self._active_group, play
        ):
            return

        self._cancel_explorer_track_action()
        self._capture_navigation()
        if self._open_folder(root_id, relative, preview=True):
            self._record_navigation()
            self.layoutChanged.emit()
            self.selectionChanged.emit()
            self._persist()

        ref = f"{root_id}/{relative}"
        tab_id = f"folder:{ref}"
        state = self._ensure_tab(tab_id)
        sort_key = str(state.get("sortKey", "fileCreatedAt"))
        ascending = bool(state.get("sortAscending", False))
        model = cast(
            TrackListModel,
            self.trackModelForTab(tab_id, "folder", ref, sort_key, ascending),
        )
        query = str(state.get("searchQuery", "")).casefold().strip()
        request_key = ("folder", ref, sort_key, ascending, query)
        model_key = self._model_key(self._active_group, tab_id)
        request_generation = self._track_tracker.generations.get(model_key, 0)
        pending, _ = self._explorer_coordinator.start_request(
            track_id=track_id,
            source=source,
            root_id=root_id,
            relative=relative,
            tab_id=tab_id,
            group_id=self._active_group,
            play=play,
            rows_generation=request_generation,
        )
        if self._track_tracker.has_completed_request(model_key, request_key):
            self._complete_explorer_track_action(pending, model)
        else:
            self._explorer_coordinator.set_pending(pending)

    def _complete_explorer_track_action(
        self, pending: dict[str, Any], model: TrackListModel
    ) -> None:
        active = self._explorer_coordinator.pending
        if active is not None and active["generation"] != pending["generation"]:
            return
        if active is None:
            self._explorer_coordinator.set_pending(pending)
        if not self._explorer_coordinator.is_context_current(
            pending, self._active_group, self._groups
        ):
            self._explorer_coordinator.clear_pending()
            return

        track_id = str(pending["track_id"])
        row_index = model.row_for_id(track_id)
        if row_index >= 0:
            if pending["mode"] == "select":
                self._explorer_coordinator.clear_pending()
                self.selectTrack(track_id, "single", [])
                return
            pending["queue_rows"] = model.rows_snapshot()
            self._request_explorer_track_snapshot(pending)
            return

        if pending["mode"] == "select":
            self._explorer_coordinator.clear_pending()
            return
        self._request_explorer_track_snapshot(pending)

    def _request_explorer_track_snapshot(self, pending: dict[str, Any]) -> None:
        pending["stage"] = "source_check"
        generation = int(pending["generation"])
        track_id = str(pending["track_id"])

        def read_track(context: JobContext) -> None:
            try:
                context.raise_if_cancelled()
                track = self._library.track(track_id)
                context.raise_if_cancelled()
                if not track or not Path(str(track.get("path", ""))).is_file():
                    track = {}
                self.explorerTrackReady.emit(generation, track, None)
            except JobCancelledError:
                raise
            except Exception as error:
                self.explorerTrackReady.emit(generation, None, str(error))
                raise

        job_id = self._jobs.submit(
            read_track, label="Load selected track", visible=False, summary=fixed("Track loaded")
        )
        self._explorer_coordinator.record_job(str(job_id))

    @Slot(int, object, object)
    def _on_explorer_track_ready(self, generation: int, track: object, error: object) -> None:
        if not self._explorer_coordinator.is_matching_ready(generation):
            return
        pending = self._explorer_coordinator.pending
        if pending is None:
            return
        self._explorer_coordinator.finish_job()
        if not self._explorer_coordinator.is_context_current(
            pending, self._active_group, self._groups
        ):
            self._explorer_coordinator.clear_pending()
            return
        if error is not None:
            self._explorer_coordinator.clear_pending()
            self._set_message(f"Could not load this track: {error}")
            return
        track_dict = track if isinstance(track, dict) else None
        valid, err_msg = validate_explorer_track(
            track_dict, pending["root_id"], pending["relative"]
        )
        if not valid:
            self._explorer_coordinator.clear_pending()
            if err_msg:
                self._set_message(err_msg)
            return

        assert track_dict is not None
        track_id = str(pending["track_id"])
        queue_rows = pending.get("queue_rows")
        if isinstance(queue_rows, list):
            captured_rows = update_captured_rows(queue_rows, track_id, track_dict)
            if captured_rows is not None:
                self._explorer_coordinator.clear_pending()
                self.selectTrack(track_id, "single", [])
                self.trackRevealRequested.emit(
                    str(pending["group"]), str(pending["tab_id"]), track_id
                )
                self.playTrack(track_id, str(pending["source"]), captured_rows)
                return

        self._explorer_coordinator.clear_pending()
        self.playTrack(track_id, str(pending["source"]), [track_dict])

    def _cancel_explorer_track_action(self) -> None:
        job_id = self._explorer_coordinator.cancel_action()
        if job_id:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(job_id))

    def _cancel_explorer_track_action_for_tab(self, tab_id: str) -> None:
        job_id = self._explorer_coordinator.cancel_action_for_tab(tab_id)
        if job_id:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(job_id))

    def _open_folder(
        self,
        root_id: str,
        relative: str,
        *,
        preview: bool = False,
        group_id: str | None = None,
    ) -> bool:
        ref = f"{root_id}/{relative}"
        tab_id = f"folder:{ref}"
        target = self._active_group if group_id is None else group_id
        group = self._groups[target]
        changed = group["active"] != tab_id or tab_id not in group["tabs"]
        if not changed:
            return False
        self._ensure_tab(tab_id)
        self._place_tab(target, tab_id, preview=preview)
        group["active"] = tab_id
        self._load_group_view(target)
        key = (target, tab_id)
        self._selection_by_tab.setdefault(key, [])
        self._anchor_by_tab.setdefault(key, "")
        return True

    # -------------------------------------------------------------- layout actions

    @Property(QObject, constant=True)
    def toolWindows(self) -> ToolWindowRegistry:
        return self._tool_windows

    @Slot(str, bool)
    def openToolWindow(self, window_id: str, below: bool = False) -> None:
        """Show a tool window in its dock; ``below`` stacks it under the window shown first."""
        side = self._tool_windows.side_of(window_id)
        if side is None or not self._tool_windows.is_pane(window_id):
            return
        if side == "left":
            self._cancel_explorer_track_action()
        self._capture_navigation()
        for other in _SIDES:
            if other != side and window_id in self._docks[other].windows:
                remaining = tuple(w for w in self._docks[other].windows if w != window_id)
                self._docks[other] = replace(
                    self._docks[other], windows=remaining, open=bool(remaining)
                )
        dock = self._docks[side]
        others = tuple(w for w in dock.windows if w != window_id)
        windows = (others[0], window_id) if below and others else (window_id,)
        self._docks[side] = replace(dock, open=True, windows=windows)
        if side == "left":
            self._fullscreen = False
        else:
            self._prepare_visible_metadata()
        self._record_navigation()
        self.layoutChanged.emit()
        self._persist()

    @Slot(str)
    def setActivity(self, activity: str) -> None:
        """Alias of ``openToolWindow`` kept for plugins and tab requests."""
        self.openToolWindow(activity, False)

    @Slot(str)
    def toggleToolWindow(self, window_id: str) -> None:
        side = self._tool_windows.side_of(window_id)
        if side is None:
            return
        dock = self._docks[side]
        if dock.open and window_id in dock.windows:
            self.closeToolWindow(window_id)
        else:
            self.openToolWindow(window_id, False)

    @Slot(str)
    def closeToolWindow(self, window_id: str) -> None:
        side = self._tool_windows.side_of(window_id)
        if side is None or window_id not in self._docks[side].windows:
            return
        dock = self._docks[side]
        remaining = tuple(w for w in dock.windows if w != window_id)
        self._docks[side] = replace(dock, windows=remaining, open=bool(remaining))
        self.layoutChanged.emit()
        self._persist()

    @Slot(str)
    def toggleDock(self, side: str) -> None:
        if side not in _SIDES:
            return
        dock = self._docks[side]
        if dock.open:
            self._docks[side] = replace(dock, open=False)
        else:
            default = "explorer" if side == "left" else "info"
            self._docks[side] = replace(dock, open=True, windows=dock.windows or (default,))
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, int)
    def setDockWidth(self, side: str, width: int) -> None:
        if side not in _SIDES:
            return
        clamped = min(max(int(width), layout.MIN_DOCK_WIDTH), layout.MAX_DOCK_WIDTH)
        self._docks[side] = replace(self._docks[side], width=clamped)
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, float)
    def setDockRatio(self, side: str, ratio: float) -> None:
        if side not in _SIDES:
            return
        self._docks[side] = replace(self._docks[side], ratio=min(max(float(ratio), 0.1), 0.9))
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, result=dict)
    def dockState(self, side: str) -> dict[str, Any]:
        if side not in _SIDES:
            return {}
        return {"side": side, **self._docks[side].to_dict()}

    @Slot(bool)
    def setSidebarVisible(self, visible: bool) -> None:
        self._sidebar_visible = bool(visible)
        self.layoutChanged.emit()
        self._persist()

    @Slot()
    def toggleSidebar(self) -> None:
        self.toggleDock("left")

    @Slot(str)
    def openPlaylist(self, _playlist_id: str) -> None:
        if self._playlists_model is None:
            return
        details = self._playlists_model.details(_playlist_id)
        if not details:
            return
        self._capture_navigation()
        self._playlists_model.refresh()
        tab_id = "playlist:" + _playlist_id
        group = self._groups[self._active_group]
        self._ensure_tab(tab_id)["title"] = details["name"]
        self._place_tab(self._active_group, tab_id, preview=True)
        group["active"] = tab_id
        self._load_group_view(self._active_group)
        self._record_navigation()
        self._scan_coordinator.mark_tab_dirty(tab_id)
        self._refresh_timer.start()
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot()
    def openConvert(self) -> None:
        if self._conversion_model is None:  # the Convert plugin is not loaded in this build
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._activity = "convert"
        self._sidebar_visible = True
        self._open_special_tab("convert:", "Convert")
        self._record_navigation()
        if self._conversion_model is not None:
            self._conversion_model.ensure_capabilities()
        self.layoutChanged.emit()
        self._persist()

    @Slot()
    def openSettings(self) -> None:
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._open_special_tab("settings:", "Settings")
        self._record_navigation()
        self.layoutChanged.emit()
        self._persist()

    @Slot()
    def openProfile(self) -> None:
        """Open the Profile page: the name, the picture and the listening statistics."""
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._open_special_tab("profile:", "Profile")
        self._record_navigation()
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str)
    def openArtistView(self, view: str, title: str) -> None:
        """Open a page of the artist manager (``from_tags.tracks``, ``catalog``…) as a tab."""
        if self._artist_manager is None:
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._sidebar_visible = True
        self._open_special_tab(f"artists:{view}", title)
        self._record_navigation()
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str)
    def openArtistPage(self, artist_id: str, name: str) -> None:
        """Open the page of one artist, listed like a playlist page.

        The core index names the artists of v0.1. An id it does not know opens nothing, unless
        the artist manager plugin (behind the plugin switch) knows it: then that plugin page
        opens, with the plugin's name for the artist.
        """
        entry = self._artist_entry(str(artist_id))
        if entry is None and not self._is_plugin_artist(str(artist_id)):
            return
        key = entry.key if entry is not None else str(artist_id)
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._sidebar_visible = True
        tab_id = f"artist:{key}"
        group = self._groups[self._active_group]
        state = self._ensure_tab(tab_id)
        state["title"] = entry.name if entry is not None else name or self._plugin_artist_name(key)
        self._place_tab(self._active_group, tab_id, preview=True)
        group["active"] = tab_id
        self._load_group_view(self._active_group)
        self._record_navigation()
        self._scan_coordinator.mark_tab_dirty(tab_id)
        self._refresh_timer.start()
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(str, list, bool)
    def playArtistRows(self, artist_id: str, rows: list, shuffled: bool) -> None:
        """Play the tracks of an artist page, in order or shuffled."""
        available = prepare_artist_playback_rows(rows, shuffled=shuffled)
        if available and self._player is not None:
            entry = self._artist_entry(str(artist_id))
            ids = [str(row["id"]) for row in available]
            self._player.playQueueWithRows(
                ids,
                0,
                f"artist:{artist_id}",
                entry.name if entry else self._plugin_artist_name(str(artist_id)) or "Artist",
                available,
            )
        elif not available:
            self._set_message("This artist has no track to play.")

    @Slot(str)
    def openTasks(self, job_id: str = "") -> None:
        """Open the Tasks page as an editor tab, like Settings; Back and Forward replay it.

        ``job_id`` names the job the page should select (empty: keep the page as it is).
        """
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._open_special_tab("tasks:", "Tasks")
        self._record_navigation()
        self.layoutChanged.emit()
        self._persist()
        self.taskFocusRequested.emit(job_id)

    def _open_special_tab(self, tab_id: str, title: str) -> None:
        group = self._groups[self._active_group]
        open_special_tab(group, self._tab_state(tab_id), tab_id, title)
        self._load_group_view(self._active_group)

    @Slot(str, str)
    def activateTab(self, group_id: str, tab_id: str) -> None:
        if group_id not in self._groups or tab_id not in self._groups[group_id]["tabs"]:
            return
        self._cancel_explorer_track_action()
        self._leave_explorer_selection()
        self._capture_navigation()
        self._active_group = group_id
        self._groups[group_id]["active"] = tab_id
        self._load_group_view(group_id)
        self._record_navigation()
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(str)
    def focusGroup(self, group_id: str) -> None:
        """Make a center window the focused one; the tab keys act on it."""
        if group_id not in self._groups or group_id == self._active_group:
            return
        self._cancel_explorer_track_action()
        self._leave_explorer_selection()
        self._capture_navigation()
        self._active_group = group_id
        self._load_group_view(group_id)
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(str)
    def setActiveGroup(self, group_id: str) -> None:
        """Alias kept for callers written before the group ids; use ``focusGroup``."""
        self.focusGroup(group_id)

    @Slot(str, str)
    def closeTab(self, group_id: str, tab_id: str) -> None:
        if group_id not in self._groups:
            return
        closed, _ = close_tab_in_group(self._groups, group_id, tab_id)
        if not closed:
            return
        self._cancel_explorer_track_action()
        was_active = group_id == self._active_group
        if was_active:
            self._capture_navigation()
        self._forget_tab(group_id, tab_id)
        if not self._groups[group_id]["tabs"] and len(self._groups) > 1:
            self._remove_group(group_id)
        if was_active:
            self._load_group_view(self._active_group)
            self._record_navigation()
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Property(dict, constant=True)
    def savedWindow(self) -> dict[str, Any]:
        """The window geometry saved at the last close ({} the first time)."""
        return dict(self._window_geometry or {})

    @Slot(int, int, int, int, bool)
    def saveWindowGeometry(self, x: int, y: int, width: int, height: int, maximized: bool) -> None:
        """Remember where the main window is; it is written with the session when MTEE closes."""
        self._window_geometry = {
            "x": int(x),
            "y": int(y),
            "width": int(width),
            "height": int(height),
            "maximized": bool(maximized),
        }
        self._persist()

    @Slot(str, str, str)
    def closeTabs(self, group_id: str, scope: str, tab_id: str) -> None:
        """Close tabs of a window: ``others``, those ``left``/``right`` of one, or ``all``."""
        if group_id not in self._groups or scope not in ("others", "all", "left", "right"):
            return
        tabs: list[str] = list(self._groups[group_id]["tabs"])
        if scope != "all":
            if tab_id not in tabs:
                return
            position = tabs.index(tab_id)
            if scope == "others":
                tabs = [tab for tab in tabs if tab != tab_id]
            elif scope == "left":
                tabs = tabs[:position]
            else:
                tabs = tabs[position + 1 :]
        for closing in tabs:
            if group_id not in self._groups:
                break
            self.closeTab(group_id, closing)

    @Slot(str)
    def closeGroup(self, group_id: str) -> None:
        """Close a center window and its tabs. The last window stays."""
        if group_id not in self._groups or len(self._groups) < 2:
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._remove_group(group_id)
        self._load_group_view(self._active_group)
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    def _forget_tab(self, group_id: str, tab_id: str) -> None:
        """Release what a tab that left its group held: rows, jobs and saved state."""
        model_key = self._model_key(group_id, tab_id)
        model = self._track_models.pop(model_key, None)
        if model is not None:
            model.deleteLater()
        job_id = self._track_tracker.cancel_and_release(model_key)
        if job_id:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(job_id))
        if not is_tab_in_any_group(self._groups, tab_id):
            purge_forgotten_tab_state(
                tab_id,
                self._tab_states,
                self._group_tab_states,
                self._selection_by_tab,
                self._anchor_by_tab,
            )

    def _new_group(self, group_id: str) -> None:
        """Register an empty group with its own settings page and navigation stack."""
        self._groups[group_id] = {"tabs": [], "active": "", "selections": {}}
        self._settings_pages[group_id] = "general"
        self._nav.add_group(group_id, self._navigation_location(group_id))

    def _remove_group(self, group_id: str) -> None:
        """Remove a center window; its tabs are released when no other window keeps them."""
        if group_id not in self._groups or len(self._groups) < 2:
            return
        order = self._group_order()
        position = order.index(group_id)
        tabs = list(self._groups[group_id]["tabs"])
        remaining = layout.remove(self._layout, group_id)
        assert remaining is not None, "the last center window is never removed"
        self._layout = remaining
        del self._groups[group_id]
        self._settings_pages.pop(group_id, None)
        for store in (self._group_tab_states, self._selection_by_tab, self._anchor_by_tab):
            for key in [key for key in store if key[0] == group_id]:
                del store[key]
        self._nav.remove_group(group_id)
        for tab_id in tabs:
            self._forget_tab(group_id, tab_id)
        if self._active_group == group_id:
            remaining = self._group_order()
            self._active_group = remaining[min(position, len(remaining) - 1)]

    def _take_tab(self, source_id: str, tab_id: str, target_id: str, index: int) -> None:
        """Move a tab from one group to another, with its view state and selection."""
        close_tab_in_group(self._groups, source_id, tab_id)
        key = (source_id, tab_id)
        target_key = (target_id, tab_id)
        if key in self._group_tab_states:
            self._group_tab_states[target_key] = self._group_tab_states.pop(key)
        if key in self._selection_by_tab:
            self._selection_by_tab[target_key] = self._selection_by_tab.pop(key)
        if key in self._anchor_by_tab:
            self._anchor_by_tab[target_key] = self._anchor_by_tab.pop(key)
        tabs: list[str] = self._groups[target_id]["tabs"]
        if tab_id in tabs:
            tabs.remove(tab_id)
        tabs.insert(min(max(index, 0), len(tabs)), tab_id)
        self._forget_tab(source_id, tab_id)

    def _copy_tab_view(self, source_id: str, tab_id: str, target_id: str) -> None:
        """Give a copy of a tab in another window the view state and selection of its source."""
        key = (source_id, tab_id)
        target_key = (target_id, tab_id)
        if key in self._group_tab_states:
            self._group_tab_states[target_key] = dict(self._group_tab_states[key])
        if key in self._selection_by_tab:
            self._selection_by_tab[target_key] = list(self._selection_by_tab[key])
        if key in self._anchor_by_tab:
            self._anchor_by_tab[target_key] = self._anchor_by_tab[key]

    def _finish_layout_change(self) -> None:
        self._load_group_view(self._active_group)
        self._record_navigation()
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(str, str, str, str)
    def splitWithTab(
        self, target_group_id: str, edge: str, source_group_id: str, tab_id: str
    ) -> None:
        """Drop a tab on an edge of a center window: the tab opens in a new window beside it.

        The only tab of a window (Ctrl+Backslash) is copied: the same tab opens beside it and
        stays in the window too. A tab of a window with several tabs moves.
        """
        if (
            target_group_id not in self._groups
            or source_group_id not in self._groups
            or tab_id not in self._groups[source_group_id]["tabs"]
            or edge not in ("left", "right", "top", "bottom")
        ):
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        new_id = self._new_group_id()
        self._new_group(new_id)
        self._layout = layout.split(self._layout, target_group_id, edge, new_id)  # type: ignore[arg-type]
        if target_group_id == source_group_id and len(self._groups[source_group_id]["tabs"]) == 1:
            self._copy_tab_view(source_group_id, tab_id, new_id)
            self._groups[new_id]["tabs"].append(tab_id)
        else:
            self._take_tab(source_group_id, tab_id, new_id, 0)
            if source_group_id != new_id and not self._groups[source_group_id]["tabs"]:
                self._remove_group(source_group_id)
        self._groups[new_id]["active"] = tab_id
        self._active_group = new_id
        self._finish_layout_change()

    @Slot(str, str, str, int)
    def moveTab(self, source_group_id: str, tab_id: str, target_group_id: str, index: int) -> None:
        """Move a tab to another window (or reorder it in its own) at ``index``."""
        if (
            source_group_id not in self._groups
            or target_group_id not in self._groups
            or tab_id not in self._groups[source_group_id]["tabs"]
        ):
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        if source_group_id == target_group_id:
            tabs: list[str] = self._groups[source_group_id]["tabs"]
            tabs.remove(tab_id)
            tabs.insert(min(max(index, 0), len(tabs)), tab_id)
        else:
            self._take_tab(source_group_id, tab_id, target_group_id, index)
            if not self._groups[source_group_id]["tabs"]:
                self._remove_group(source_group_id)
        self._groups[target_group_id]["active"] = tab_id
        self._active_group = target_group_id
        self._finish_layout_change()

    @Slot(str, str, str)
    def openFolderAt(self, folder_id: str, target_group_id: str, zone: str) -> None:
        """Open an Explorer folder in a window (``center``) or in a new window on an edge."""
        parsed = parse_folder_id(folder_id)
        if parsed is None or target_group_id not in self._groups:
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        if zone == "center":
            group_id = target_group_id
        elif zone in ("left", "right", "top", "bottom"):
            group_id = self._new_group_id()
            self._new_group(group_id)
            self._layout = layout.split(self._layout, target_group_id, zone, group_id)  # type: ignore[arg-type]
        else:
            return
        if not self._open_folder(*parsed, preview=True, group_id=group_id):
            if group_id != target_group_id and not self._groups[group_id]["tabs"]:
                self._remove_group(group_id)
            self._request_folder_refresh(*parsed)
            return
        self._active_group = group_id
        self._finish_layout_change()

    @Slot(list, list)
    def setSplitRatios(self, path: list, ratios: list) -> None:
        """Set the shares of a split (the path of the split in the tree, root first)."""
        try:
            tree_path = tuple(int(index) for index in path)
            shares = [float(value) for value in ratios]
            self._layout = layout.set_ratios(
                self._layout, tree_path, shares, MIN_CENTER_WINDOW_SHARE
            )
        except (TypeError, ValueError, IndexError):
            return
        self.layoutChanged.emit()
        self._persist()

    @Slot(str)
    def focusNeighbour(self, direction: str) -> None:
        """Focus the window next to the focused one in ``direction``."""
        if direction not in ("left", "right", "top", "bottom"):
            return
        target = layout.neighbour(self._layout, self._active_group, direction)  # type: ignore[arg-type]
        if target is not None:
            self.focusGroup(target)

    @Slot(str)
    def moveTabToNeighbour(self, direction: str) -> None:
        """Move the active tab of the focused window to the window next to it."""
        if direction not in ("left", "right", "top", "bottom"):
            return
        target = layout.neighbour(self._layout, self._active_group, direction)  # type: ignore[arg-type]
        tab_id = str(self._groups[self._active_group]["active"])
        if target is None or not tab_id:
            return
        self.moveTab(self._active_group, tab_id, target, len(self._groups[target]["tabs"]))

    def _plugin_list_kind(self, tab_id: str) -> str:
        """The tab kind of ``tab_id`` when it is a track list of a plugin, else an empty string."""
        kind = tab_id.partition(":")[0]
        return kind if self._plugin_ui.is_track_list_kind(kind) else ""

    @Slot(str, str)
    def setSort(self, tab_id: str, key: str) -> None:
        if key not in _COLUMN_KEYS and not self._plugin_ui.has_column(key):
            return
        self._cancel_explorer_track_action_for_tab(tab_id)
        self._keep(tab_id)
        state = self._ensure_tab(tab_id)
        if state.get("sortMode") != "manual" or state.get("sortKey") != key:
            state["sortMode"] = "manual"
            state["sortKey"] = key
            state["sortAscending"] = True
        elif bool(state.get("sortAscending", True)):
            state["sortAscending"] = False
        else:
            self._set_default_sort(state)
        self._capture_navigation()
        self._revision += 1
        self._scan_coordinator.mark_tab_dirty(tab_id)
        self.layoutChanged.emit()
        self.libraryChanged.emit()
        self._refresh_timer.start()
        self._persist()

    @Slot(str, str)
    def toggleColumn(self, tab_id: str, key: str) -> None:
        self._ensure_tab(tab_id)
        self._column_preferences, changed, needs_play_stats = toggle_column(
            self._column_preferences, key, _COLUMN_KEYS
        )
        if not changed:
            return
        self._refresh_hidden_sorts(set(self._column_preferences["hidden"]))
        if needs_play_stats:
            self.refreshPlayStats()
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str, int)
    def resizeColumn(self, tab_id: str, key: str, width: int) -> None:
        plugin_kind = self._plugin_list_kind(tab_id)
        if plugin_kind:
            self._plugin_ui.resize_column(plugin_kind, key, width)
            return
        if tab_id.startswith("playlist:") and self._playlists_model is not None:
            self._playlists_model.resizeColumn(key, width)
            return
        self._ensure_tab(tab_id)
        self._column_preferences, changed = resize_column(
            self._column_preferences, key, width, _COLUMN_KEYS
        )
        if changed:
            self.layoutChanged.emit()
            self._persist()

    @Slot(str, dict)
    def resizeColumns(self, tab_id: str, widths: dict) -> None:
        """Save several widths at once, after a border drag (plan 133.3)."""
        plugin_kind = self._plugin_list_kind(tab_id)
        if tab_id.startswith("playlist:") and self._playlists_model is not None:
            # One write for all the widths: one write per column would keep only the last.
            self._playlists_model.resizeColumns(dict(widths))
            return
        if plugin_kind:
            for key, width in widths.items():
                self.resizeColumn(tab_id, key, int(width))
            return
        self._ensure_tab(tab_id)
        self._column_preferences, changed = resize_columns(
            self._column_preferences, widths, _COLUMN_KEYS
        )
        if changed:
            self.layoutChanged.emit()
            self._persist()

    @Slot(str, str, int)
    def moveColumn(self, tab_id: str, key: str, offset: int) -> None:
        plugin_kind = self._plugin_list_kind(tab_id)
        if plugin_kind:
            self._plugin_ui.move_column(plugin_kind, key, offset)
            return
        if tab_id.startswith("playlist:") and self._playlists_model is not None:
            self._playlists_model.moveColumn(key, offset)
            return
        self._ensure_tab(tab_id)
        self._column_preferences, changed = move_column(
            self._column_preferences, key, offset, _COLUMN_KEYS
        )
        if changed:
            self.layoutChanged.emit()
            self._persist()

    @Slot(str, str, str, bool)
    def moveColumnRelative(self, tab_id: str, key: str, target_key: str, after: bool) -> None:
        plugin_kind = self._plugin_list_kind(tab_id)
        if plugin_kind:
            self._plugin_ui.move_column_relative(plugin_kind, key, target_key, after)
            return
        if tab_id.startswith("playlist:") and self._playlists_model is not None:
            self._playlists_model.moveColumnRelative(key, target_key, after)
            return
        self._ensure_tab(tab_id)
        self._column_preferences, changed = move_column_relative(
            self._column_preferences, key, target_key, after, _COLUMN_KEYS
        )
        if changed:
            self.layoutChanged.emit()
            self._persist()

    @Slot(bool)
    def setShowArtwork(self, visible: bool) -> None:
        self._column_preferences, changed = set_show_artwork(self._column_preferences, visible)
        if changed:
            self.layoutChanged.emit()
            self._persist()

    @Slot()
    def resetColumns(self) -> None:
        self._column_preferences = reset_column_preferences()
        self._refresh_hidden_sorts(set(self._column_preferences["hidden"]))
        self.layoutChanged.emit()
        self._persist()

    def _refresh_hidden_sorts(self, hidden: set[str]) -> None:
        reset_tabs = find_tabs_with_hidden_sort(self._tab_states, hidden)
        for tab_id in reset_tabs:
            self._scan_coordinator.mark_tab_dirty(tab_id)
        if reset_tabs:
            self._revision += 1
            self.libraryChanged.emit()
            self._refresh_timer.start()

    @Slot(str, str)
    def setTabView(self, tab_id: str, view: str) -> None:
        if view not in {"list", "artwork"}:
            return
        self._keep(tab_id)
        self._tab_state(tab_id)["view"] = view
        self._capture_navigation()
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str)
    def setSearch(self, tab_id: str, query: str) -> None:
        self._cancel_explorer_track_action_for_tab(tab_id)
        self._tab_state(tab_id)["searchQuery"] = query[:256]
        # Capture before _keep: its layoutChanged makes the field re-read the group state,
        # and a stale query there overwrote the first typed character.
        self._capture_navigation()
        self._keep(tab_id)
        self._revision += 1
        self._scan_coordinator.mark_tab_dirty(tab_id)
        self.libraryChanged.emit()
        self._refresh_timer.start()
        self._persist()

    @Slot(bool)
    def setRightPanelVisible(self, visible: bool) -> None:
        self._capture_navigation()
        self._right_visible = bool(visible)
        self._record_navigation()
        self._prepare_visible_metadata()
        self.layoutChanged.emit()
        self._persist()

    @Slot(str)
    def showRightPanel(self, tab: str) -> None:
        self._capture_navigation()
        self._right_tab = tab if tab in {"info", "queue", "history"} else "info"
        self._right_visible = True
        self._record_navigation()
        self._prepare_visible_metadata()
        self.layoutChanged.emit()
        self._persist()

    @Slot(str)
    def toggleRightPanel(self, tab: str) -> None:
        self._capture_navigation()
        if self._right_visible and self._right_tab == tab:
            self._right_visible = False
        else:
            self._right_visible = True
            self._right_tab = tab if tab in {"info", "queue", "history"} else "info"
        self._prepare_visible_metadata()
        self._record_navigation()
        self.layoutChanged.emit()
        self._persist()

    @Slot(int)
    def setFullscreenPage(self, page: int) -> None:
        """Show page 0 or 1 of the fullscreen player; ignored without a playing track."""
        target = 1 if int(page) >= 1 else 0
        has_track = self._player is not None and bool(self._player.playing_id_value())
        if target == self._fullscreen_page or (target and not has_track):
            return
        self._fullscreen_page = target
        self.layoutChanged.emit()

    @Slot(bool)
    def setFullscreen(self, enabled: bool) -> None:
        self._capture_navigation()
        if bool(enabled) != self._fullscreen:
            self._fullscreen_page = 0  # reopening always shows the card
        self._fullscreen = bool(enabled)
        self._record_navigation()
        self._prepare_visible_metadata()
        self.layoutChanged.emit()

    @Slot(bool)
    def setPreviewTabs(self, enabled: bool) -> None:
        """Browsing opens one replaceable preview tab; off keeps every opened tab."""
        self._preview_tabs = bool(enabled)
        if not self._preview_tabs:
            for state in self._tab_states.values():
                state.pop("preview", None)
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str)
    def keepTab(self, group_id: str, tab_id: str) -> None:
        """Turn a preview tab into a permanent one."""
        if group_id in self._groups and keep_tab_state(self._tab_state(tab_id)):
            self.layoutChanged.emit()
            self._persist()

    def _keep(self, tab_id: str) -> None:
        """Working in a tab (sorting, searching, changing its view) makes it permanent."""
        if keep_tab_state(self._tab_state(tab_id)):
            self.layoutChanged.emit()

    def _place_tab(self, group_id: str, tab_id: str, *, preview: bool) -> None:
        """Add a tab to a group; a preview tab takes the place of the group's other one."""
        displaced = place_tab(
            self._groups[group_id],
            self._tab_states,
            tab_id,
            preview=preview,
            preview_enabled=self._preview_tabs,
        )
        if displaced is not None:
            self._forget_tab(group_id, displaced)

    @Slot(int)
    def setSidebarWidth(self, width: int) -> None:
        self.setDockWidth("left", width)

    @Slot(int)
    def setRightPanelWidth(self, width: int) -> None:
        self.setDockWidth("right", width)

    # -------------------------------------------------------------- selection and actions

    @Slot()
    @Slot(str)
    def clearSelection(self, group_id: str = "") -> None:
        target = group_id or self._active_group
        if target not in self._groups:
            return
        tab_id = str(self._groups[target]["active"])
        key = (target, tab_id)
        if target != self._active_group:
            self.focusGroup(target)
        self._nav.clear_pending_if_matches(target, tab_id)
        if self._selection_source == "explorer":
            self._leave_explorer_selection()
            self.selectionChanged.emit()
        if not self._selection_by_tab.get(key) and not self._anchor_by_tab.get(key):
            return
        self._selection_by_tab[key] = []
        self._anchor_by_tab[key] = ""
        self.selectionChanged.emit()
        self._persist()

    @Slot(str, str, list)
    def selectTrack(self, track_id: str, mode: str = "single", ordered: list | None = None) -> None:
        self._cancel_explorer_track_action()
        tab_id = str(self._groups[self._active_group]["active"])
        key = (self._active_group, tab_id)
        self._nav.clear_pending_if_matches(self._active_group, tab_id)
        self._leave_explorer_selection()
        selected = self._selection_by_tab.setdefault(key, [])
        anchor = self._anchor_by_tab.get(key, "")
        new_selected, new_anchor = calculate_selection(selected, anchor, track_id, mode, ordered)
        selected[:] = new_selected
        self._anchor_by_tab[key] = new_anchor
        self.selectionChanged.emit()
        self._persist()

    @Slot(list)
    def selectAll(self, ordered: list) -> None:
        tab_id = str(self._groups[self._active_group]["active"])
        key = (self._active_group, tab_id)
        self._nav.clear_pending_if_matches(self._active_group, tab_id)
        self._leave_explorer_selection()
        self._selection_by_tab[key] = [str(track_id) for track_id in ordered]
        self._anchor_by_tab[key] = str(ordered[0]) if ordered else ""
        self.selectionChanged.emit()
        self._persist()

    @Slot(str, str)
    @Slot(str, str, list)
    def playTrack(self, track_id: str, source: str, rows: list | None = None) -> None:
        self._cancel_explorer_track_action()
        plugin_kind, _, plugin_ref = source.partition(":")
        plugin_list = self._plugin_ui.is_track_list_kind(plugin_kind)
        if source.startswith("playlist:") or plugin_list:
            model = self._active_track_model(source)
            captured = rows if rows is not None else model.rows_snapshot() if model else []
            if plugin_list:
                name = self._plugin_ui.tab_title(plugin_kind, plugin_ref)
            else:
                detail = (
                    self._playlists_model.details(source.partition(":")[2])
                    if self._playlists_model
                    else {}
                )
                name = str(detail.get("name", "Playlist"))
            playback_args = build_playlist_track_playback(captured, track_id, name, source)
            if playback_args is None:
                self._set_message(
                    "This track has no local file."
                    if plugin_list
                    else "This track is unavailable. Locate a local file first."
                )
                return
            ids, chosen_index, title, playable = playback_args
            if self._player is not None:
                self._player.playQueueWithRows(ids, chosen_index, source, title, playable)
            return
        supplied_rows = (
            [dict(row) for row in rows if isinstance(row, dict)] if rows is not None else None
        )
        track = next(
            (row for row in supplied_rows or () if str(row.get("id", "")) == track_id),
            None,
        )
        if track is None:
            track = self.track(track_id) if supplied_rows is None else {}
        try:
            folder = parse_folder_id(source)
        except ValueError:
            folder = None
        if folder is not None:
            root_id, relative = folder
        elif track:
            root_id, relative = str(track.get("rootId", "")), folder_from_track(track)
        else:
            root_id, relative = "", ""
        model = self._active_track_model(f"folder:{root_id}/{relative}")
        model_rows = model.rows_snapshot() if model else None
        tab_state = self._tab_state(f"folder:{root_id}/{relative}") if root_id else None

        order, folder_rows = resolve_folder_playback_rows(
            supplied_rows=supplied_rows,
            model_rows=model_rows,
            track=track,
            folder=folder,
            library_query_fn=self._library.tracks_in_folder,
            tab_state=tab_state,
            track_id=track_id,
        )
        self.activationRequested.emit(track_id, order)
        if self._player is not None:
            if track_id not in order:
                order.append(track_id)
            title = self._playback_source_title(source, track)
            self._player.playQueueWithRows(order, order.index(track_id), source, title, folder_rows)
        else:
            self._set_message("The audio runtime is unavailable.")

    @Slot(str, str, list)
    def playTrackFromRows(self, track_id: str, source: str, rows: list) -> None:
        self.playTrack(track_id, source, rows)

    def _playback_source_title(self, source: str, track: dict[str, Any]) -> str:
        return format_playback_source_title(
            source=source,
            track=track,
            roots_by_id=self._roots_by_id,
            artist_entry_fn=self._artist_entry,
            plugin_artist_name_fn=self._plugin_artist_name,
        )

    @Slot()
    def togglePlay(self) -> None:
        if self._player is not None:
            self._player.togglePlay()

    @Slot()
    def previous(self) -> None:
        if self._player is not None:
            self._player.previous()

    @Slot()
    def next(self) -> None:
        if self._player is not None:
            self._player.next()

    @Slot()
    def toggleShuffle(self) -> None:
        if self._player is not None:
            self._player.toggleShuffle()

    @Slot()
    def cycleRepeat(self) -> None:
        if self._player is not None:
            self._player.cycleRepeat()

    @Slot(float)
    def seek(self, position: float) -> None:
        if self._player is not None:
            self._player.seek(position)

    @Slot(int)
    def setVolume(self, volume: int) -> None:
        if self._player is not None:
            self._player.setVolume(volume)

    @Slot()
    def toggleMute(self) -> None:
        if self._player is not None:
            self._player.toggleMute()

    @Slot(str)
    def beginFieldEdit(self, field: str) -> None:
        if self._metadata_editor is not None:
            self._metadata_editor.begin_field_edit(field)

    @Slot(str, str, bool)
    def commitField(self, field: str, value: str, remove: bool = False) -> None:
        if self._metadata_editor is not None:
            self._metadata_editor.commit_field(field, value, remove)
        else:
            self._set_message("Metadata is read-only in this step.")

    @Slot()
    def finishSave(self) -> None:
        if self._metadata_editor is not None:
            self._metadata_editor.finish_save()

    @Slot()
    def retrySave(self) -> None:
        if self._metadata_editor is not None:
            self._metadata_editor.retry_save()

    @Slot()
    def undoSave(self) -> None:
        if self._metadata_editor is not None:
            self._metadata_editor.undo_save()

    @Slot()
    def stopPlaybackAndSave(self) -> None:
        if self._metadata_editor is not None:
            self._metadata_editor.stopPlaybackAndSave()

    @Slot(list)
    def addToNewPlaylist(self, _track_ids: list) -> None:
        if self._playlists_model is not None:
            self._playlists_model.createUntitled("", self.localTrackIds(_track_ids))

    @Slot(list, str)
    def togglePlaylist(self, _track_ids: list, _playlist_id: str) -> None:
        if self._playlists_model is not None:
            self._playlists_model.toggle(_playlist_id, self.localTrackIds(_track_ids))

    @Slot()
    def addSelectionToConvert(self) -> None:
        if self._conversion_model is not None:
            self._conversion_model.add_tracks(self.selected_ids_snapshot())
        self.openConvert()

    @Slot()
    def retryConversion(self) -> None:
        if self._conversion_model is not None:
            self._conversion_model.retry_failed()

    @Slot()
    def clearMessage(self) -> None:
        self._set_message("")

    # -------------------------------------------------------------- internals

    # The docks hold the tool windows (plan 131.4). The names below read and write the dock
    # state, so the code that uses the first window and the dock sizes keeps working.
    @property
    def _activity(self) -> str:
        windows = self._docks["left"].windows
        return windows[0] if windows else "explorer"

    @_activity.setter
    def _activity(self, activity: str) -> None:
        self._set_first_window("left", activity)

    @property
    def _sidebar_visible(self) -> bool:
        return self._docks["left"].open

    @_sidebar_visible.setter
    def _sidebar_visible(self, visible: bool) -> None:
        self._docks["left"] = replace(self._docks["left"], open=bool(visible))

    @property
    def _sidebar_width(self) -> int:
        return self._docks["left"].width

    @_sidebar_width.setter
    def _sidebar_width(self, width: int) -> None:
        self._docks["left"] = replace(self._docks["left"], width=int(width))

    @property
    def _right_visible(self) -> bool:
        return self._docks["right"].open

    @_right_visible.setter
    def _right_visible(self, visible: bool) -> None:
        self._docks["right"] = replace(self._docks["right"], open=bool(visible))

    @property
    def _right_panel_width(self) -> int:
        return self._docks["right"].width

    @_right_panel_width.setter
    def _right_panel_width(self, width: int) -> None:
        self._docks["right"] = replace(self._docks["right"], width=int(width))

    @property
    def _right_tab(self) -> str:
        windows = self._docks["right"].windows
        return windows[0] if windows and windows[0] in _RIGHT_TABS else "info"

    @_right_tab.setter
    def _right_tab(self, tab: str) -> None:
        self._set_first_window("right", tab)

    def _set_first_window(self, side: str, window_id: str) -> None:
        dock = self._docks[side]
        rest = tuple(item for item in dock.windows[1:] if item != window_id)
        self._docks[side] = replace(dock, windows=(window_id, *rest))

    def _ensure_tab(self, tab_id: str) -> dict[str, Any]:
        return ensure_tab_state(tab_id, self._tab_states, self._roots_by_id)

    def _tab_state(self, tab_id: str) -> dict[str, Any]:
        if not hasattr(self, "_tab_states"):
            self._tab_states: dict[str, dict[str, Any]] = {}
        return self._tab_states.setdefault(tab_id, {})

    def _restore_groups(
        self, raw_groups: list[Any], center: Any
    ) -> tuple[dict[str, dict[str, Any]], layout.Node, dict[str, dict[str, Any]], int]:
        groups, tree, tab_states, next_group = restore_session_groups(
            raw_groups, self._roots_by_id, center
        )
        return groups, tree, tab_states, next_group

    def _current_track_model(self) -> TrackListModel | None:
        active = str(self._groups[self._active_group]["active"])
        return self._active_track_model(active)

    def _refresh_library(
        self, root_id: str | None = None, changed_folders: set[str] | None = None
    ) -> None:
        if self._playlists_model is not None:
            self._playlists_model.refresh()
        self._revision += 1
        self.libraryChanged.emit()
        self._scan_coordinator.mark_dirty_library(root_id, changed_folders)
        self._refresh_timer.start()

    def _refresh_models(self) -> None:
        if not self._jobs.accepting:
            return  # a refresh timer that fires after shutdown began has nothing to load
        if self._scan_coordinator.has_dirty_roots():
            self._scan_coordinator.consume_dirty_roots()
            self._request_folder_roots()
        dirty_all_branches, dirty_branches = self._scan_coordinator.consume_dirty_branches()
        if dirty_all_branches:
            for job_id in self._branch_tracker.cancel_all_jobs():
                with suppress(LookupError, ValueError):
                    self._jobs.cancel(JobId.parse(job_id))
            self._folder_model.invalidate_all_branches()
        else:
            for root_id, relative in dirty_branches:
                folder_id = f"root:{root_id}" if not relative else f"folder:{root_id}/{relative}"
                job_id = self._branch_tracker.cancel_job(folder_id)
                if job_id:
                    with suppress(LookupError, ValueError):
                        self._jobs.cancel(JobId.parse(job_id))
                self._folder_model.invalidate_branch(folder_id)
        all_tabs = {self._model_identity(key)[1] for key in self._track_models}
        dirty_tabs = self._scan_coordinator.consume_dirty_tabs(all_tabs)
        for model_key, model in tuple(self._track_models.items()):
            group_id, tab_id = self._model_identity(model_key)
            if tab_id not in dirty_tabs or group_id not in self._groups:
                continue
            state = dict(self._tab_state(tab_id))
            state.update(self._group_tab_states.get((group_id, tab_id), {}))
            kind = str(state.get("kind", ""))
            if kind not in {"folder", "playlist", "artist"} and not (
                self._plugin_ui.is_track_list_kind(kind)
            ):
                model.replace([])
                continue
            self._track_tracker.invalidate_key(model_key)
            self._request_track_rows(
                model_key,
                tab_id,
                group_id,
                str(state.get("kind", "folder")),
                str(state.get("ref", "")),
                str(state.get("sortKey", "fileCreatedAt")),
                bool(state.get("sortAscending", False)),
            )
        for folder_id in tuple(self._expanded):
            if self._folder_model.is_expanded(folder_id) and not self._folder_model.branch_loaded(
                folder_id
            ):
                self._request_folder_branch(folder_id)
        self.explorerChanged.emit()

    # ------------------------------------------------------------ folder refresh

    def _sync_folder_watches(self) -> None:
        """Watch the folders of the active tabs and refresh those that just became visible."""
        targets, paths, active = compute_folder_watch_targets(self._groups, self._roots_by_id)
        self._folder_watch.set_watched(paths)
        newly_visible = self._scan_coordinator.update_watch_targets(targets, active)
        for root_id, relative in newly_visible:
            self._request_folder_refresh(root_id, relative)

    def _on_folder_watch_changed(self, path: str) -> None:
        target = self._scan_coordinator.resolve_watch_target(path)
        if target is not None:
            self._request_folder_refresh(*target)

    def _on_application_state_changed(self, state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            for root_id, relative in sorted(self._scan_coordinator.active_folder_tabs):
                self._request_folder_refresh(root_id, relative)

    def _request_folder_refresh(self, root_id: str, relative: str) -> None:
        root = self._roots_by_id.get(root_id)
        if (
            root is None
            or self._scan_coordinator.is_scan_active(root_id)
            or not self._jobs.accepting
        ):
            return  # a running full scan will see the change
        if not self._scan_coordinator.begin_folder_refresh(root_id, relative):
            return
        root_path = str(root["path"])

        def task(context: JobContext) -> None:
            result = refresh_folder(
                self._library,
                self._scanner,
                self._reader,
                root_id,
                root_path,
                relative,
                wait=context.sleep,
            )
            self.folderRefreshed.emit(
                root_id,
                relative,
                {"folders": list(result.folders), "unstable": result.unstable},
            )

        try:
            job_id = self._jobs.submit(
                task,
                label="Refresh folder",
                visible=False,
                priority=1,
                summary=fixed("Folder refreshed"),
            )
        except RuntimeError:
            return
        self._scan_coordinator.record_folder_refresh_job(root_id, relative, str(job_id))

    def _on_folder_refreshed(self, root_id: str, relative: str, payload: object) -> None:
        detail = payload if isinstance(payload, dict) else {}
        unstable = bool(detail.get("unstable"))
        retry_unstable, had_pending = self._scan_coordinator.finish_folder_refresh(
            root_id, relative, unstable=unstable
        )
        folders = {str(item) for item in detail.get("folders", [])}
        if folders:
            self._refresh_library(root_id, folders | {relative})
        if retry_unstable:
            QTimer.singleShot(2_000, lambda: self._request_folder_refresh(root_id, relative))
        if had_pending:
            self._request_folder_refresh(root_id, relative)

    def _on_scan_batch(self, root_id: str, request_id: str, detail: object) -> None:
        if not self._scan_coordinator.is_matching_request(root_id, request_id):
            return
        payload = detail if isinstance(detail, dict) else {}
        count = int(payload.get("count", 0))
        total_count = self._scan_coordinator.record_scan_batch(root_id, count)
        if not self._scan_coordinator.is_quiet_request(request_id):
            self._set_message(f"Indexed {total_count:,} audio files…")
        self._revision += 1
        self.libraryChanged.emit()
        changed_folders = payload.get("folders", [])
        if isinstance(changed_folders, list):
            self._scan_coordinator.mark_dirty_batch(root_id, changed_folders)
        self._refresh_timer.start()

    def _on_scan_finished(self, root_id: str, request_id: str, result: dict[str, Any]) -> None:
        if not self._scan_coordinator.is_matching_request(root_id, request_id):
            return
        quiet, scan_count = self._scan_coordinator.finish_scan(root_id, request_id)
        changed_folders = result.get("changedFolders", [])
        if isinstance(changed_folders, list):
            self._scan_coordinator.mark_dirty_finished(root_id, changed_folders)
        else:
            self._scan_coordinator.mark_dirty_finished(root_id, [])
        self._refresh_timer.start()
        msg = format_scan_finished_message(result, scan_count, quiet)
        if msg is not None:
            self._set_message(msg)
        self._persist()
        root = self._roots_by_id.get(root_id)
        if root is not None and result.get("complete") and not result.get("cancelled"):
            self._plugin_ui.library_scanned(Path(str(root["path"])))

    def _on_metadata_changed(self) -> None:
        self._revision += 1
        self.libraryChanged.emit()
        if self._player is not None and self._player.playing_id_value():
            self._player.refreshTrack(self._player.playing_id_value())
        self._refresh_timer.start()

    def _prepare_visible_metadata(self) -> None:
        if self._metadata_editor is None:
            return
        if should_prepare_track_inspection(self._right_visible, self._fullscreen, self._right_tab):
            self._metadata_editor.prepareTrackInspection()
        else:
            self._metadata_editor.cancelPendingInspection()

    def _set_message(self, message: str) -> None:
        if self._message == message:
            return
        self._message = message
        self.messageChanged.emit()

    @staticmethod
    def _set_default_sort(state: dict[str, Any]) -> None:
        set_default_sort(state)

    @property
    def _session_closed(self) -> bool:
        return self._session_writer.is_closed

    @property
    def _session_future(self) -> Future[None] | None:
        return self._session_writer.future

    def _persist(self) -> None:
        if self._session_writer.is_closed:
            return
        self._session_timer.start()

    def _session_snapshot(self) -> dict[str, Any]:
        return build_session_snapshot(
            expanded=self._expanded,
            groups=self._groups,
            layout_tree=self._layout,
            tab_states=self._tab_states,
            selection_by_tab=self._selection_by_tab,
            anchor_by_tab=self._anchor_by_tab,
            active_group=self._active_group,
            activity=self._activity,
            sidebar_visible=self._sidebar_visible,
            right_visible=self._right_visible,
            right_tab=self._right_tab,
            sidebar_width=self._sidebar_width,
            right_panel_width=self._right_panel_width,
            preview_tabs=self._preview_tabs,
            column_preferences=self._column_preferences,
            next_group=self._next_group,
            artist_sort=self._artist_sort,
            docks=self._docks,
            window=self._window_geometry,
        )

    @Slot()
    def _write_pending_session(self) -> None:
        self._session_writer.write_pending(self._session_snapshot())

    @Slot(object, object)
    def _on_session_write_finished(self, future: object, error: object) -> None:
        matched, exc = self._session_writer.handle_write_finished(future, error)
        if not matched:
            return
        if exc is not None:
            self._set_message(f"Could not save this workspace: {exc}")

    @Slot()
    def flush_session(self) -> None:
        """Persist the latest independent snapshot before SQLite is closed."""
        if self._session_writer.is_closed:
            return
        if self._genre_manager_model is not None:
            closer = getattr(self._genre_manager_model, "close", None)
            if callable(closer):
                closer()
        self._folder_watch.close()
        self._session_timer.stop()
        state = self._session_snapshot()
        error = self._session_writer.flush(state)
        if error is not None:
            self._set_message(f"Could not save this workspace: {error}")
