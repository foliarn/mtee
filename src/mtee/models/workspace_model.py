"""Live Explorer state, folder browsing and navigation actions for QML."""

from __future__ import annotations

import os
import re
import sqlite3
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlparse

from PySide6.QtCore import Property, QEvent, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication, QMouseEvent, QWindow

from mtee.domain.jobs import JobCancelledError, JobId
from mtee.domain.navigation_history import NavigationHistory, NavigationLocation
from mtee.models.analysis_model import AnalysisModel
from mtee.models.analysis_settings_model import AnalysisSettingsModel
from mtee.models.conversion_queue_model import ConversionQueueModel
from mtee.models.folder_tree_model import FolderTreeModel
from mtee.models.metadata_editor_model import MetadataEditorModel
from mtee.models.player_model import PlayerModel
from mtee.models.playlists_model import PlaylistsModel
from mtee.models.tag_conflicts_model import TagConflictsModel
from mtee.models.track_list_model import TrackListModel
from mtee.models.trash_model import TrashModel
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.workspace_repository import (
    COLUMN_OPTIONS,
    DEFAULT_COLUMN_PREFERENCES,
    WorkspaceRepository,
)
from mtee.services.folder_refresh import refresh_folder
from mtee.services.folder_watch import FolderWatchService
from mtee.services.jobs import JobContext, JobService
from mtee.services.library_scanner import LibraryScanner
from mtee.services.metadata_reader import MetadataReader
from mtee.services.platform.shell_reveal import WindowsShellReveal

__all__ = ["WorkspaceModel"]

_SORT_KEYS = {
    "index",
    "title",
    "artist",
    "album",
    "genre",
    "bpm",
    "key",
    "duration",
    "format",
    "bitrate",
    "filename",
    "fileCreatedAt",
    "fileModifiedAt",
}
_COLUMN_KEYS = {key for key, _label in COLUMN_OPTIONS}
_ACTIVITIES = {"explorer", "playlists", "convert", "tasks", "plugins", "profile"}


class WorkspaceModel(QObject):
    """Own live root, tab, selection and scan state; all file work is asynchronous."""

    layoutChanged = Signal()
    explorerChanged = Signal()
    libraryChanged = Signal()
    selectionChanged = Signal()
    metadataChanged = Signal()
    messageChanged = Signal()
    trackRevealRequested = Signal(int, str, str)
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
    enqueuePrepared = Signal(int, object)

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
        self._enqueue_sequence = 0
        self._enqueue_next_to_apply = 1
        self._enqueue_ready: dict[int, dict[str, Any]] = {}
        self._metadata_editor: MetadataEditorModel | None = None
        self._conversion_model: ConversionQueueModel | None = None
        self._trash_model: TrashModel | None = None
        self._analysis_model: AnalysisModel | None = None
        self._analysis_settings: AnalysisSettingsModel | None = None
        self._tag_conflicts: TagConflictsModel | None = None
        self._scanner = LibraryScanner()
        self._reader = MetadataReader()
        self._shell_reveal = WindowsShellReveal()
        self._roots_by_id: dict[str, dict[str, Any]] = {}
        self._resume_roots_requested = False
        self._state = session.load()
        saved_column_preferences = self._state.get("columnPreferences", DEFAULT_COLUMN_PREFERENCES)
        self._column_preferences = _copy_column_preferences(saved_column_preferences)
        self._expanded = set(self._state.get("expanded", []))
        self._groups = self._restore_groups(self._state.get("groups", []))
        self._active_group = min(int(self._state.get("activeGroup", 0)), len(self._groups) - 1)
        self._selection_by_tab: dict[tuple[int, str], list[str]] = {}
        self._anchor_by_tab: dict[tuple[int, str], str] = {}
        for group_index, group in enumerate(self._groups):
            saved = group.get("selections", {})
            for tab_id in group["tabs"]:
                tab_state = self._tab_state(tab_id)
                selected = saved.get(tab_id, {})
                if not isinstance(selected, dict):
                    selected = {}
                key = (group_index, tab_id)
                self._selection_by_tab[key] = list(
                    selected.get("ids", tab_state.get("selectedIds", []))
                )
                self._anchor_by_tab[key] = str(
                    selected.get("anchor", tab_state.get("selectionAnchor", ""))
                )
        self._activity = str(self._state.get("activity", "explorer"))
        self._sidebar_visible = bool(self._state.get("sidebarVisible", True))
        self._right_visible = bool(self._state.get("rightPanelVisible", False))
        saved_right_tab = str(self._state.get("rightPanelTab", "info"))
        self._right_tab = saved_right_tab if saved_right_tab in {"info", "queue"} else "info"
        self._sidebar_width = int(self._state.get("sidebarWidth", 240))
        self._right_panel_width = int(self._state.get("rightPanelWidth", 360))
        self._fullscreen = False
        self._fullscreen_page = 0
        self._island_enabled = bool(self._state.get("islandEnabled", True))
        self._settings_pages = ["general" for _ in self._groups]
        self._navigation_scroll: dict[tuple[int, str, str], float] = {}
        self._navigation_anchor: dict[tuple[int, str, str], tuple[str, float]] = {}
        self._group_tab_states: dict[tuple[int, str], dict[str, Any]] = {
            (index, tab_id): self._view_fields(self._tab_states.get(tab_id, {}))
            for index, group in enumerate(self._groups)
            for tab_id in group["tabs"]
        }
        self._navigation_histories = [NavigationHistory() for _ in self._groups]
        self._navigation_replaying = False
        self._pending_navigation_selection: tuple[int, str, list[str]] | None = None
        for index in range(len(self._groups)):
            self._navigation_histories[index] = self._navigation_histories[index].visit(
                self._navigation_location(index)
            )
        self._message = (
            "The saved workspace was invalid. MTEE restored a safe default layout."
            if session.load_recovered
            else ""
        )
        self._revision = 0
        self._requests: dict[str, str] = {}
        self._quiet_requests: set[str] = set()
        self._jobs_by_root: dict[str, str] = {}
        self._scan_counts: dict[str, int] = {}
        self._track_models: dict[str, TrackListModel] = {}
        self._track_request_generation: dict[str, int] = {}
        self._track_request_keys: dict[str, tuple[Any, ...]] = {}
        self._track_job_ids: dict[str, str] = {}
        self._explorer_activation_generation = 0
        self._pending_explorer_track: dict[str, Any] | None = None
        self._pending_reveal: tuple[str, str] | None = None
        self._explorer_track_job_id = ""
        self._folder_request_generation: dict[str, int] = {}
        self._folder_job_ids: dict[str, str] = {}
        self._folder_root_generation = 0
        self._folder_root_job_id = ""
        self._dirty_all_branches = False
        self._dirty_root_ids: set[str] = set()
        self._dirty_folder_branches: set[tuple[str, str]] = set()
        self._dirty_tabs: set[str] = set()
        self._dirty_all_tabs = False
        self._folder_model = FolderTreeModel(self)
        self._session_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="mtee-session"
        )
        self._session_future: Future[None] | None = None
        self._session_pending: dict[str, Any] | None = None
        self._session_closed = False
        self._session_timer = QTimer(self)
        self._session_timer.setSingleShot(True)
        self._session_timer.setInterval(300)
        self._session_timer.timeout.connect(self._write_pending_session)
        self.sessionWriteFinished.connect(self._on_session_write_finished)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(90)
        self._refresh_timer.timeout.connect(self._refresh_models)
        self._folder_refresh_jobs: dict[tuple[str, str], str] = {}
        self._folder_refresh_pending: set[tuple[str, str]] = set()
        self._folder_refresh_unstable: dict[tuple[str, str], int] = {}
        self._active_folder_tabs: set[tuple[str, str]] = set()
        self._watch_targets: dict[str, tuple[str, str]] = {}
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
        return [
            {
                "tabs": [
                    dict(self._tab_state(tab_id)) | self._group_tab_states.get((index, tab_id), {})
                    for tab_id in group["tabs"]
                ],
                "active": group["active"],
            }
            for index, group in enumerate(self._groups)
        ]

    @Property(list, notify=layoutChanged)
    def groups(self) -> list[dict[str, Any]]:
        return self.groups_snapshot()

    @Property(dict, notify=layoutChanged)
    def columnPreferences(self) -> dict[str, Any]:
        return _copy_column_preferences(self._column_preferences)

    @Property(list, constant=True)
    def columnOptions(self) -> list[dict[str, str]]:
        return [{"key": key, "label": label} for key, label in COLUMN_OPTIONS]

    @Property(int, notify=layoutChanged)
    def activeGroup(self) -> int:
        return self._active_group

    @Property(bool, notify=layoutChanged)
    def canNavigateBack(self) -> bool:
        return self._navigation_histories[self._active_group].can_back

    @Property(bool, notify=layoutChanged)
    def canNavigateForward(self) -> bool:
        return self._navigation_histories[self._active_group].can_forward

    @Property(str, notify=layoutChanged)
    def settingsPage(self) -> str:
        return self._settings_pages[self._active_group]

    @Slot(int, result=str)
    def settingsPageForGroup(self, group_index: int) -> str:
        if 0 <= group_index < len(self._groups):
            return self._settings_pages[group_index]
        return "general"

    @staticmethod
    def _view_fields(tab: dict[str, Any]) -> dict[str, Any]:
        return {
            key: tab[key]
            for key in ("searchQuery", "sortKey", "sortAscending", "sortMode", "view")
            if key in tab
        }

    def _save_group_view(self, group_index: int) -> None:
        tab_id = str(self._groups[group_index]["active"])
        if tab_id:
            self._group_tab_states[(group_index, tab_id)] = self._view_fields(
                self._tab_states.get(tab_id, {})
            )

    def _load_group_view(self, group_index: int) -> None:
        tab_id = str(self._groups[group_index]["active"])
        saved = self._group_tab_states.get((group_index, tab_id))
        if saved is not None:
            self._tab_state(tab_id).update(saved)
            self._dirty_tabs.add(tab_id)
            self._refresh_timer.start()

    @staticmethod
    def _model_key(group_index: int, tab_id: str) -> str:
        return tab_id if group_index == 0 else f"@{group_index}|{tab_id}"

    @staticmethod
    def _model_identity(model_key: str) -> tuple[int, str]:
        if model_key.startswith("@") and "|" in model_key:
            group, _, tab_id = model_key[1:].partition("|")
            if group.isdecimal():
                return int(group), tab_id
        return 0, model_key

    def _active_track_model(self, tab_id: str) -> TrackListModel | None:
        return self._track_models.get(self._model_key(self._active_group, tab_id))

    def _navigation_location(self, group_index: int) -> NavigationLocation:
        tab_id = str(self._groups[group_index]["active"])
        tab = dict(self._tab_states.get(tab_id, {}))
        tab.update(self._group_tab_states.get((group_index, tab_id), {}))
        return NavigationLocation(
            self._activity,
            tab_id,
            self._fullscreen,
            self._right_visible,
            self._right_tab,
            self._settings_pages[group_index],
            {
                "searchQuery": str(tab.get("searchQuery", "")),
                "sortKey": str(tab.get("sortKey", "index")),
                "sortAscending": bool(tab.get("sortAscending", True)),
                "sortMode": str(tab.get("sortMode", "default")),
                "view": str(tab.get("view", "list")),
                "selected": list(self._selection_by_tab.get((group_index, tab_id), [])),
                "anchor": self._anchor_by_tab.get((group_index, tab_id), ""),
                "scrollList": self._navigation_scroll.get((group_index, tab_id, "list"), 0.0),
                "scrollArtwork": self._navigation_scroll.get((group_index, tab_id, "artwork"), 0.0),
                "anchorList": self._navigation_anchor.get((group_index, tab_id, "list"), ("", 0.0)),
                "anchorArtwork": self._navigation_anchor.get(
                    (group_index, tab_id, "artwork"), ("", 0.0)
                ),
            },
        )

    def _capture_navigation(self) -> None:
        if self._navigation_replaying:
            return
        self._pending_navigation_selection = None
        group = self._active_group
        self._save_group_view(group)
        self._navigation_histories[group] = self._navigation_histories[group].capture(
            self._navigation_location(group)
        )

    def _record_navigation(self) -> None:
        if self._navigation_replaying:
            return
        group = self._active_group
        self._save_group_view(group)
        self._navigation_histories[group] = self._navigation_histories[group].visit(
            self._navigation_location(group)
        )

    @Slot(int, str, str, float)
    @Slot(int, str, str, float, str, float)
    def setNavigationScroll(
        self,
        group_index: int,
        tab_id: str,
        view: str,
        content_y: float,
        anchor_id: str = "",
        anchor_offset: float = 0.0,
    ) -> None:
        if view in {"list", "artwork"} and 0 <= group_index < len(self._groups):
            key = (group_index, tab_id, view)
            self._navigation_scroll[key] = max(0.0, content_y)
            self._navigation_anchor[key] = (anchor_id, anchor_offset)

    @Slot(int, str, str, result=float)
    def navigationScroll(self, group_index: int, tab_id: str, view: str) -> float:
        return self._navigation_scroll.get((group_index, tab_id, view), 0.0)

    @Slot(int, str, str, result=dict)
    def navigationAnchor(self, group_index: int, tab_id: str, view: str) -> dict[str, Any]:
        track_id, offset = self._navigation_anchor.get((group_index, tab_id, view), ("", 0.0))
        return {"id": track_id, "offset": offset}

    @Slot(str)
    def setSettingsPage(self, page: str) -> None:
        self.setSettingsPageForGroup(self._active_group, page)

    @Slot(int, str)
    def setSettingsPageForGroup(self, group_index: int, page: str) -> None:
        if (
            not 0 <= group_index < len(self._groups)
            or page not in {"general", "analysis"}
            or page == self._settings_pages[group_index]
        ):
            return
        if group_index != self._active_group:
            self.setActiveGroup(group_index)
        self._capture_navigation()
        self._settings_pages[group_index] = page
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
        history = self._navigation_histories[group]
        while True:
            next_history = history.back() if back else history.forward()
            if next_history is history or next_history.current is None:
                return
            history = next_history
            location = history.current
            assert location is not None
            if (
                location.tab_id.startswith("playlist:")
                and self._playlists_model is not None
                and not self._playlists_model.details(location.tab_id.partition(":")[2])
            ):
                self._set_message("This playlist is no longer available.")
                self._navigation_histories[group] = history
                continue
            self._navigation_histories[group] = history
            self._replay_navigation(location)
            return

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
        self._navigation_replaying = True
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
            self._activity = location.activity
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
                self._dirty_tabs.add(tab_id)
                self._revision += 1
                self.libraryChanged.emit()
                self._refresh_timer.start()
            self._selection_by_tab[(self._active_group, tab_id)] = list(
                location.view.get("selected", [])
            )
            if tab_id.startswith(("folder:", "playlist:")):
                self._pending_navigation_selection = (
                    self._active_group,
                    tab_id,
                    list(self._selection_by_tab[(self._active_group, tab_id)]),
                )
            self._anchor_by_tab[(self._active_group, tab_id)] = str(location.view.get("anchor", ""))
            for view in ("list", "artwork"):
                key = (self._active_group, tab_id, view)
                self._navigation_scroll[key] = float(
                    location.view.get("scroll" + view.title(), 0.0)
                )
                anchor = location.view.get("anchor" + view.title(), ("", 0.0))
                if isinstance(anchor, (list, tuple)) and len(anchor) == 2:
                    self._navigation_anchor[key] = (str(anchor[0]), float(anchor[1]))
            self.layoutChanged.emit()
            self.selectionChanged.emit()
            self._persist()
        finally:
            self._navigation_replaying = False

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
    def islandEnabled(self) -> bool:
        return self._island_enabled

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
        tab_id = str(self._groups[self._active_group]["active"])
        return list(self._selection_by_tab.get((self._active_group, tab_id), []))

    @Slot(int, result=list)
    def selectedIdsForGroup(self, group_index: int) -> list[str]:
        if not 0 <= group_index < len(self._groups):
            return []
        tab_id = str(self._groups[group_index]["active"])
        return list(self._selection_by_tab.get((group_index, tab_id), []))

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

    def attach_conversion_model(self, model: ConversionQueueModel) -> None:
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
        model.libraryImported.connect(self._refresh_library)

    @Slot()
    def _on_playlists_changed(self) -> None:
        if self._playlists_model is not None:
            for state in self._tab_states.values():
                if state.get("kind") == "playlist":
                    detail = self._playlists_model.details(str(state.get("ref", "")))
                    if detail:
                        state["title"] = detail["name"]
        self._revision += 1
        self._dirty_all_tabs = True
        self.libraryChanged.emit()
        self.layoutChanged.emit()
        self._refresh_timer.start()

    @Slot(str)
    def _on_playlist_deleted(self, identity: str) -> None:
        for index in range(len(self._groups)):
            self.closeTab(index, "playlist:" + identity)

    @Slot(list, result=list)
    def localTrackIds(self, identities: list) -> list[str]:
        model = self._current_track_model()
        lookup = (
            {r["id"]: r.get("trackId", r["id"]) for r in model.rows_snapshot()} if model else {}
        )
        playlist = bool(model and any("entryId" in r for r in model.rows_snapshot()))
        lookup.update({identity: identity for identity in lookup.values() if identity})
        return list(
            dict.fromkeys(
                str(lookup.get(i, "" if playlist else i))
                for i in identities
                if lookup.get(i, "" if playlist else i)
            )
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

    @Slot(list)
    def addTracksToConvert(self, track_ids: list) -> None:
        """Queue these tracks, given by their library identity, for conversion and open it."""
        identities = [str(identity) for identity in track_ids if str(identity)]
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
        elif kind == "folder" and self._folder_source_exists(source):
            self.openFolder(source)

    def _folder_source_exists(self, source: str) -> bool:
        try:
            parsed = _parse_folder_id(source)
        except ValueError:
            return False
        if parsed is None:
            return False
        root_id, relative = parsed
        if root_id not in self._roots_by_id:
            return False
        return not relative or relative in set(self._library.folders(root_id))

    def _select_revealed_row(self, tab_id: str, track_id: str) -> None:
        """Select the first row of the tab that shows this track, now or when rows arrive."""
        model = self._active_track_model(tab_id)
        if model is not None:
            for row in model.rows_snapshot():
                if str(row.get("trackId", row.get("id", ""))) == track_id:
                    self._pending_reveal = None
                    self.selectTrack(str(row["id"]), "single", [])
                    return
        self._pending_reveal = (tab_id, track_id)

    @Slot(str, str, int)
    def movePlaylistEntry(self, source: str, entry: str, offset: int) -> None:
        state = self._tab_state(source)
        if state.get("searchQuery") or state.get("sortKey") != "index":
            self._set_message("Switch to Custom order and clear search before reordering.")
            return
        model = self._active_track_model(source)
        if model is None or self._playlists_model is None or source == "playlist:liked":
            return
        entries = model.track_ids_snapshot()
        if entry not in entries:
            return
        index = entries.index(entry)
        target = min(max(index + offset, 0), len(entries) - 1)
        entries.insert(target, entries.pop(index))
        identity = source.partition(":")[2]
        version = self._playlists_model.details(identity).get("version", -1)
        self._playlists_model.reorder(identity, entries, version)

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
        from mtee.domain.playlists import reorder_entries

        state = self._tab_state(source)
        if state.get("searchQuery") or state.get("sortKey") != "index":
            self._set_message("Switch to Custom order and clear search before reordering.")
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
            next_entries = reorder_entries(entries, [str(i) for i in entry_ids], before)
        except ValueError as error:
            self._set_message(str(error))
            return
        if next_entries != entries:
            self._playlists_model.reorder(identity, next_entries, expected_version)

    @Slot(str)
    def customPlaylistOrder(self, tab_id: str) -> None:
        state = self._tab_state(tab_id)
        state.update(
            {"sortMode": "default", "sortKey": "index", "sortAscending": True, "searchQuery": ""}
        )
        self._dirty_tabs.add(tab_id)
        self._revision += 1
        self.libraryChanged.emit()
        self.layoutChanged.emit()
        self._refresh_timer.start()
        self._persist()

    @Slot(str, list, bool)
    def playPlaylistRows(self, identity: str, rows: list, shuffled: bool) -> None:
        import random

        available = [
            dict(r) | {"id": r["trackId"]}
            for r in rows
            if isinstance(r, dict) and r.get("available") and r.get("trackId")
        ]
        if shuffled:
            random.shuffle(available)
        if available and self._player is not None:
            ids = [r["id"] for r in available]
            detail = self._playlists_model.details(identity) if self._playlists_model else {}
            self._player.playQueueWithRows(
                ids, 0, "playlist:" + identity, detail.get("name", "Playlist"), available
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
        self._enqueue_sequence += 1
        sequence = self._enqueue_sequence
        captured_rows = [dict(row) for row in rows if isinstance(row, dict)]
        playlist_service = self._playlists_model.service if self._playlists_model else None
        playlist_id = source.partition(":")[2] if source.startswith("playlist:") else ""
        detail = (
            self._playlists_model.details(playlist_id)
            if playlist_id and self._playlists_model
            else {}
        )
        source_title = str(detail.get("name", "Playlist")) if playlist_id else source

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
                accepted: list[dict[str, Any]] = []
                rejected = 0
                for row in targets:
                    context.raise_if_cancelled()
                    if not isinstance(row, dict):
                        rejected += 1
                        continue
                    track_id = str(row.get("trackId") or row.get("id") or "")
                    path = str(row.get("path", ""))
                    available = bool(
                        track_id
                        and row.get("available", row.get("status") == "readable")
                        and path
                        and Path(path).is_file()
                    )
                    if not available:
                        rejected += 1
                        continue
                    accepted.append(dict(row) | {"id": track_id})
                self.enqueuePrepared.emit(
                    sequence,
                    {
                        "rows": accepted,
                        "rejected": rejected,
                        "source": source,
                        "source_title": source_title,
                    },
                )
            except Exception as error:
                self.enqueuePrepared.emit(sequence, {"error": str(error)})

        try:
            self._jobs.submit(
                prepare,
                label="Add playlist to queue" if entire_playlist else "Add tracks to queue",
                visible=entire_playlist or len(identities) > 100,
            )
        except RuntimeError as error:
            self.enqueuePrepared.emit(sequence, {"error": str(error)})

    @Slot(int, object)
    def _on_enqueue_prepared(self, sequence: int, result: object) -> None:
        self._enqueue_ready[sequence] = (
            result if isinstance(result, dict) else {"error": "Invalid queue batch"}
        )
        while self._enqueue_next_to_apply in self._enqueue_ready:
            ready = self._enqueue_ready.pop(self._enqueue_next_to_apply)
            self._enqueue_next_to_apply += 1
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
    def tagConflicts(self) -> QObject:
        return self._tag_conflicts if self._tag_conflicts is not None else self

    @Property(list, notify=selectionChanged)
    def infoFieldsReadOnly(self) -> list[dict[str, str]]:
        ids = self.selected_ids_snapshot()
        if len(ids) != 1:
            return []
        track = self.track(ids[0])
        labels = (
            ("Title", "title"),
            ("Artist", "artist"),
            ("Album", "album"),
            ("Genre", "genre"),
            ("Date", "year"),
            ("BPM", "bpmText"),
            ("Key", "key"),
            ("Track number", "trackNumber"),
            ("Comment", "comment"),
        )
        return [
            {"label": label, "value": str(track.get(key, "") or "—")}
            for label, key in labels
            if track.get(key, "")
        ]

    @Property(list, notify=selectionChanged)
    def infoFile(self) -> list[dict[str, str]]:
        ids = self.selected_ids_snapshot()
        if len(ids) != 1:
            return []
        track = self.track(ids[0])
        labels = (
            ("Duration", "duration"),
            ("Format", "format"),
            ("Codec", "codec"),
            ("Bitrate", "bitrateText"),
            ("Sample rate", "sampleRate"),
            ("Size", "size"),
            ("Date created", "fileCreatedAtText"),
            ("Date modified", "fileModifiedAtText"),
            ("Filename", "filename"),
            ("Path", "path"),
            ("Status", "status"),
        )
        return [{"label": label, "value": str(track.get(key, "") or "—")} for label, key in labels]

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
            self._set_message("This file is no longer in the library.")
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
        self.selectionChanged.connect(editor.refresh_selection)
        self.selectionChanged.connect(self._prepare_visible_metadata)
        editor.refresh_selection()
        self._prepare_visible_metadata()

    def attach_trash_model(self, model: TrashModel) -> None:
        """Attach the dedicated Windows recycle model."""
        if self._trash_model is not None:
            raise RuntimeError("A trash model is already attached to this workspace.")
        self._trash_model = model
        model.setParent(self)
        model.tracksRecycled.connect(self._on_tracks_recycled)

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
        try:
            parsed = _parse_folder_id(str(folder_id))
        except ValueError:
            parsed = None
        if parsed is None:
            self._set_message("This folder cannot be analyzed.")
            return
        self._analysis_model.analyzeTree(parsed[0], parsed[1], force)

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
        self._dirty_all_tabs = True
        self.libraryChanged.emit()
        self.metadataChanged.emit()
        self._refresh_timer.start()

    @Slot(object)
    def _on_tracks_recycled(self, recycled: object) -> None:
        if not isinstance(recycled, list):
            return
        affected: dict[str, set[str]] = {}
        for item in recycled:
            if not isinstance(item, dict) or item.get("status") != "recycled":
                continue
            root_id = str(item.get("rootId", ""))
            if root_id:
                affected.setdefault(root_id, set()).add(str(item.get("parentRelative", "")))
        for root_id, folders in affected.items():
            self._dirty_root_ids.add(root_id)
            for relative in folders:
                self._dirty_folder_branches.add((root_id, relative))
                self._dirty_tabs.add(f"folder:{root_id}/{relative}")
        if affected:
            self._revision += 1
            self.libraryChanged.emit()
            self._refresh_timer.start()

    @Slot(str, str, str, str, bool, result=QObject)
    @Slot(str, str, str, str, bool, int, result=QObject)
    def trackModelForTab(
        self,
        tab_id: str,
        kind: str,
        ref: str,
        sort_key: str,
        ascending: bool,
        group_index: int = -1,
    ) -> QObject:
        group = self._active_group if group_index < 0 else group_index
        model_key = self._model_key(group, tab_id)
        model = self._track_models.get(model_key)
        if model is None:
            model = TrackListModel(self)
            self._track_models[model_key] = model
        if kind in {"folder", "playlist"}:
            self._request_track_rows(model_key, tab_id, group, kind, ref, sort_key, ascending)
        else:
            model.replace([])
        return model

    def _request_track_rows(
        self,
        model_key: str,
        tab_id: str,
        group_index: int,
        kind: str,
        ref: str,
        sort_key: str,
        ascending: bool,
    ) -> None:
        tab = dict(self._tab_state(tab_id))
        tab.update(self._group_tab_states.get((group_index, tab_id), {}))
        query = str(tab.get("searchQuery", "")).casefold().strip()
        key = (kind, ref, sort_key, bool(ascending), query)
        if self._track_request_keys.get(model_key) == key:
            return
        pending = self._pending_explorer_track
        if pending is not None and pending["tab_id"] == tab_id and pending["group"] == group_index:
            self._cancel_explorer_track_action()
        generation = self._track_request_generation.get(model_key, 0) + 1
        self._track_request_generation[model_key] = generation
        previous_job = self._track_job_ids.get(model_key)
        if previous_job:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(previous_job))
        self._track_request_keys[model_key] = key

        def read_rows(context: JobContext) -> None:
            context.raise_if_cancelled()
            if kind == "playlist" and self._playlists_model is not None:
                rows = self._playlists_model.service.rows(ref)
            else:
                root_id, relative = _parse_folder_ref(ref)
                rows = self._library.tracks_in_folder(root_id, relative)
            if query:
                rows = [
                    row
                    for row in rows
                    if query
                    in " ".join(
                        str(row.get(field, ""))
                        for field in ("title", "artist", "album", "genre", "filename")
                    ).casefold()
                ]
            ordered = (
                rows if sort_key == "index" and ascending else _sort_rows(rows, sort_key, ascending)
            )
            context.raise_if_cancelled()
            self.trackRowsReady.emit(model_key, generation, ordered)

        job_id = self._jobs.submit(read_rows, label="Load folder contents", visible=False)
        self._track_job_ids[model_key] = str(job_id)

    @Slot(str, int, object)
    def _on_track_rows_ready(self, model_key: str, generation: int, rows: object) -> None:
        if generation != self._track_request_generation.get(model_key):
            return
        group_index, tab_id = self._model_identity(model_key)
        model = self._track_models.get(model_key)
        if model is None or not isinstance(rows, list):
            return
        self._track_job_ids.pop(model_key, None)
        model.replace(rows)
        reveal = self._pending_reveal
        if reveal is not None and reveal[0] == tab_id:
            self._pending_reveal = None
            if self._groups[self._active_group]["active"] == tab_id:
                self._select_revealed_row(tab_id, reveal[1])
                self._pending_reveal = None
        pending_navigation = self._pending_navigation_selection
        if (
            pending_navigation is not None
            and pending_navigation[:2] == (group_index, tab_id)
            and group_index < len(self._groups)
            and self._groups[group_index]["active"] == tab_id
        ):
            available_ids = set(model.track_ids_snapshot())
            key = (group_index, tab_id)
            self._selection_by_tab[key] = [
                identity for identity in pending_navigation[2] if identity in available_ids
            ]
            self._pending_navigation_selection = None
            self.selectionChanged.emit()
        pending = self._pending_explorer_track
        if (
            pending is not None
            and pending["stage"] == "rows"
            and pending["tab_id"] == tab_id
            and pending["group"] == group_index
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

        job_id = self._jobs.submit(read_roots, label="Load library folders", visible=False)
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
        if folder_id in self._folder_job_ids:
            return
        parsed = _parse_folder_id(folder_id)
        if parsed is None:
            return
        root_id, relative = parsed
        generation = self._folder_request_generation.get(folder_id, 0) + 1
        self._folder_request_generation[folder_id] = generation
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

        job_id = self._jobs.submit(read_branch, label="Load folder contents", visible=False)
        self._folder_job_ids[folder_id] = str(job_id)

    @Slot(str, int, object, object)
    def _on_folder_branch_ready(
        self, folder_id: str, generation: int, rows: object, error: object
    ) -> None:
        if generation != self._folder_request_generation.get(folder_id):
            return
        self._folder_job_ids.pop(folder_id, None)
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
        root_id, relative = _parse_folder_ref(ref)
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
        path = _local_path(selected)
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

    def _start_root_scan(self, root_id: str, *, quiet: bool) -> str:
        root = self._roots_by_id.get(root_id)
        if root is None:
            self._set_message("This folder is no longer in the library.")
            return ""
        previous_job = self._jobs_by_root.get(root_id)
        if previous_job:
            previous_request = self._requests.get(root_id)
            if previous_request is not None:
                self._quiet_requests.discard(previous_request)
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(previous_job))
        generation = self._library.begin_scan(root_id, show_scanning=not quiet)
        request_id = os.urandom(16).hex()
        self._requests[root_id] = request_id
        if quiet:
            self._quiet_requests.add(request_id)
        self._scan_counts[root_id] = 0
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
            visible=not quiet,
            priority=-1 if quiet else 0,
        )
        self._jobs_by_root[root_id] = str(job_id)
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
            self._folder_request_generation[folder_id] = (
                self._folder_request_generation.get(folder_id, 0) + 1
            )
            job_id = self._folder_job_ids.pop(folder_id, "")
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
        parsed = _parse_folder_id(folder_id)
        if parsed is None:
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        if not self._open_folder(*parsed):
            self._request_folder_refresh(*parsed)
            return
        self._record_navigation()
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(str, str)
    def selectExplorerTrack(self, track_id: str, folder_id: str) -> None:
        """Open a tree track's folder and select it only when it is in the listing."""
        self._request_explorer_track_action(track_id, folder_id, play=False)

    @Slot(str, str)
    def activateExplorerTrack(self, track_id: str, folder_id: str) -> None:
        """Reveal and play a tree track, or play it alone when the listing filters it out."""
        self._request_explorer_track_action(track_id, folder_id, play=True)

    def _request_explorer_track_action(self, track_id: str, folder_id: str, *, play: bool) -> None:
        parsed = _parse_folder_id(folder_id)
        if parsed is None or not track_id:
            return

        root_id, relative = parsed
        source = f"folder:{root_id}/{relative}"
        pending = self._pending_explorer_track
        if (
            not play
            and pending is not None
            and pending["mode"] == "activate"
            and pending["group"] == self._active_group
            and pending["track_id"] == track_id
            and pending["source"] == source
        ):
            return

        self._cancel_explorer_track_action()
        generation = self._explorer_activation_generation
        self._capture_navigation()
        if self._open_folder(root_id, relative):
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
        request_generation = self._track_request_generation.get(model_key, 0)
        pending = {
            "generation": generation,
            "group": self._active_group,
            "tab_id": tab_id,
            "track_id": str(track_id),
            "source": source,
            "root_id": root_id,
            "relative": relative,
            "mode": "activate" if play else "select",
            "stage": "rows",
            "rows_generation": request_generation,
        }
        if (
            self._track_request_keys.get(model_key) == request_key
            and model_key not in self._track_job_ids
        ):
            self._complete_explorer_track_action(pending, model)
        else:
            self._pending_explorer_track = pending

    def _complete_explorer_track_action(
        self, pending: dict[str, Any], model: TrackListModel
    ) -> None:
        active = self._pending_explorer_track
        if active is not None and active["generation"] != pending["generation"]:
            return
        if active is None:
            self._pending_explorer_track = pending
        if not self._explorer_track_context_is_current(pending):
            self._pending_explorer_track = None
            return

        track_id = str(pending["track_id"])
        row_index = model.row_for_id(track_id)
        if row_index >= 0:
            if pending["mode"] == "select":
                self._pending_explorer_track = None
                self.selectTrack(track_id, "single", [])
                return
            pending["queue_rows"] = model.rows_snapshot()
            self._request_explorer_track_snapshot(pending)
            return

        if pending["mode"] == "select":
            self._pending_explorer_track = None
            return
        self._request_explorer_track_snapshot(pending)

    def _explorer_track_context_is_current(self, pending: dict[str, Any]) -> bool:
        group_index = int(pending["group"])
        return (
            0 <= group_index < len(self._groups)
            and self._active_group == group_index
            and self._groups[group_index]["active"] == pending["tab_id"]
        )

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

        job_id = self._jobs.submit(read_track, label="Load selected track", visible=False)
        self._explorer_track_job_id = str(job_id)

    @Slot(int, object, object)
    def _on_explorer_track_ready(self, generation: int, track: object, error: object) -> None:
        pending = self._pending_explorer_track
        if (
            pending is None
            or pending["generation"] != generation
            or pending["stage"] != "source_check"
        ):
            return
        self._explorer_track_job_id = ""
        if not self._explorer_track_context_is_current(pending):
            self._pending_explorer_track = None
            return
        if error is not None:
            self._pending_explorer_track = None
            self._set_message(f"Could not load this track: {error}")
            return
        if not isinstance(track, dict) or not track:
            self._pending_explorer_track = None
            self._set_message("This file is no longer in the library.")
            return
        if str(track.get("rootId", "")) != str(pending["root_id"]) or _folder_from_track(
            track
        ) != str(pending["relative"]):
            self._pending_explorer_track = None
            self._set_message("This file is no longer in this folder.")
            return

        track_id = str(pending["track_id"])
        queue_rows = pending.get("queue_rows")
        if isinstance(queue_rows, list):
            captured_rows = [dict(row) for row in queue_rows if isinstance(row, dict)]
            for index, row in enumerate(captured_rows):
                if str(row.get("id", "")) == track_id:
                    captured_rows[index] = track
                    self._pending_explorer_track = None
                    self.selectTrack(track_id, "single", [])
                    self.trackRevealRequested.emit(
                        int(pending["group"]), str(pending["tab_id"]), track_id
                    )
                    self.playTrack(track_id, str(pending["source"]), captured_rows)
                    return

        self._pending_explorer_track = None
        self.playTrack(track_id, str(pending["source"]), [track])

    def _cancel_explorer_track_action(self) -> None:
        self._explorer_activation_generation += 1
        self._pending_explorer_track = None
        job_id = self._explorer_track_job_id
        self._explorer_track_job_id = ""
        if job_id:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(job_id))

    def _cancel_explorer_track_action_for_tab(self, tab_id: str) -> None:
        pending = self._pending_explorer_track
        if pending is not None and pending["tab_id"] == tab_id:
            self._cancel_explorer_track_action()

    def _open_folder(self, root_id: str, relative: str) -> bool:
        ref = f"{root_id}/{relative}"
        tab_id = f"folder:{ref}"
        group = self._groups[self._active_group]
        changed = group["active"] != tab_id or tab_id not in group["tabs"]
        if not changed:
            return False
        self._ensure_tab(tab_id)
        if tab_id not in group["tabs"]:
            group["tabs"].append(tab_id)
        group["active"] = tab_id
        self._load_group_view(self._active_group)
        key = (self._active_group, tab_id)
        self._selection_by_tab.setdefault(key, [])
        self._anchor_by_tab.setdefault(key, "")
        return True

    # -------------------------------------------------------------- layout actions

    @Slot(str)
    def setActivity(self, activity: str) -> None:
        if activity not in _ACTIVITIES:
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._activity = activity
        self._sidebar_visible = True
        self._fullscreen = False
        self._record_navigation()
        self.layoutChanged.emit()
        self._persist()

    @Slot(bool)
    def setSidebarVisible(self, visible: bool) -> None:
        self._sidebar_visible = bool(visible)
        self.layoutChanged.emit()
        self._persist()

    @Slot()
    def toggleSidebar(self) -> None:
        self.setSidebarVisible(not self._sidebar_visible)

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
        if tab_id not in group["tabs"]:
            group["tabs"].append(tab_id)
        group["active"] = tab_id
        self._load_group_view(self._active_group)
        self._record_navigation()
        self._dirty_tabs.add(tab_id)
        self._refresh_timer.start()
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot()
    def openConvert(self) -> None:
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
    def openTasks(self) -> None:
        """Open the Tasks page as an editor tab, like Settings; Back and Forward replay it."""
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._open_special_tab("tasks:", "Tasks")
        self._record_navigation()
        self.layoutChanged.emit()
        self._persist()

    def _open_special_tab(self, tab_id: str, title: str) -> None:
        group = self._groups[self._active_group]
        self._tab_state(tab_id).update(
            {"id": tab_id, "kind": tab_id.partition(":")[0], "ref": "", "title": title}
        )
        if tab_id not in group["tabs"]:
            group["tabs"].append(tab_id)
        group["active"] = tab_id
        self._load_group_view(self._active_group)

    @Slot(int, str)
    def activateTab(self, group_index: int, tab_id: str) -> None:
        if (
            not 0 <= group_index < len(self._groups)
            or tab_id not in self._groups[group_index]["tabs"]
        ):
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._active_group = group_index
        self._groups[group_index]["active"] = tab_id
        self._load_group_view(group_index)
        self._record_navigation()
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(int)
    def setActiveGroup(self, group_index: int) -> None:
        if not 0 <= group_index < len(self._groups) or group_index == self._active_group:
            return
        self._cancel_explorer_track_action()
        self._capture_navigation()
        self._active_group = group_index
        self._load_group_view(group_index)
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(int, str)
    def closeTab(self, group_index: int, tab_id: str) -> None:
        if not 0 <= group_index < len(self._groups):
            return
        group = self._groups[group_index]
        tabs = group["tabs"]
        if tab_id not in tabs:
            return
        self._cancel_explorer_track_action()
        if group_index == self._active_group:
            self._capture_navigation()
        old_index = tabs.index(tab_id)
        tabs.remove(tab_id)
        model_key = self._model_key(group_index, tab_id)
        model = self._track_models.pop(model_key, None)
        if model is not None:
            model.deleteLater()
        self._track_request_generation[model_key] = (
            self._track_request_generation.get(model_key, 0) + 1
        )
        job_id = self._track_job_ids.pop(model_key, "")
        if job_id:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(job_id))
        self._track_request_keys.pop(model_key, None)
        if group["active"] == tab_id:
            group["active"] = tabs[min(old_index, len(tabs) - 1)] if tabs else ""
        if not any(tab_id in item["tabs"] for item in self._groups):
            self._tab_states.pop(tab_id, None)
            self._group_tab_states = {
                key: value for key, value in self._group_tab_states.items() if key[1] != tab_id
            }
            self._selection_by_tab = {
                key: value for key, value in self._selection_by_tab.items() if key[1] != tab_id
            }
            self._anchor_by_tab = {
                key: value for key, value in self._anchor_by_tab.items() if key[1] != tab_id
            }
        if group_index == self._active_group:
            self._load_group_view(group_index)
            self._record_navigation()
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot()
    def toggleSplit(self) -> None:
        self._cancel_explorer_track_action()
        if len(self._groups) == 1:
            active = str(self._groups[0]["active"])
            self._groups.append(
                {
                    "tabs": [active] if active else [],
                    "active": active,
                    "selections": {active: {"ids": [], "anchor": ""}} if active else {},
                }
            )
            if active:
                self._selection_by_tab[(1, active)] = []
                self._anchor_by_tab[(1, active)] = ""
            self._settings_pages.append(self._settings_pages[0])
            self._navigation_histories.append(
                NavigationHistory().visit(self._navigation_location(1))
            )
        else:
            for tab_id in self._groups[1]["tabs"]:
                model_key = self._model_key(1, tab_id)
                model = self._track_models.pop(model_key, None)
                if model is not None:
                    model.deleteLater()
                self._track_request_generation[model_key] = (
                    self._track_request_generation.get(model_key, 0) + 1
                )
                job_id = self._track_job_ids.pop(model_key, "")
                if job_id:
                    with suppress(LookupError, ValueError):
                        self._jobs.cancel(JobId.parse(job_id))
                self._track_request_keys.pop(model_key, None)
            for tab_id in self._groups[1]["tabs"]:
                if tab_id not in self._groups[0]["tabs"]:
                    self._groups[0]["tabs"].append(tab_id)
            if not self._groups[0]["active"]:
                self._groups[0]["active"] = self._groups[1]["active"]
            self._groups.pop()
            self._navigation_histories.pop()
            self._settings_pages.pop()
            self._group_tab_states = {
                key: value for key, value in self._group_tab_states.items() if key[0] == 0
            }
            self._navigation_scroll = {
                key: value for key, value in self._navigation_scroll.items() if key[0] == 0
            }
            self._navigation_anchor = {
                key: value for key, value in self._navigation_anchor.items() if key[0] == 0
            }
            self._active_group = 0
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(str, str)
    def setSort(self, tab_id: str, key: str) -> None:
        if key not in _COLUMN_KEYS:
            return
        self._cancel_explorer_track_action_for_tab(tab_id)
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
        self._dirty_tabs.add(tab_id)
        self.layoutChanged.emit()
        self.libraryChanged.emit()
        self._refresh_timer.start()
        self._persist()

    @Slot(str, str)
    def toggleColumn(self, tab_id: str, key: str) -> None:
        if key not in _COLUMN_KEYS:
            return
        self._ensure_tab(tab_id)
        hidden = list(self._column_preferences["hidden"])
        if key in hidden:
            hidden.remove(key)
        else:
            if len(_COLUMN_KEYS) - len(hidden) <= 1:
                return
            hidden.append(key)
        self._column_preferences["hidden"] = hidden
        self._refresh_hidden_sorts(set(hidden))
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str, int)
    def resizeColumn(self, tab_id: str, key: str, width: int) -> None:
        if tab_id.startswith("playlist:") and self._playlists_model is not None:
            self._playlists_model.resizeColumn(key, width)
            return
        if key not in _COLUMN_KEYS:
            return
        self._ensure_tab(tab_id)
        widths = dict(self._column_preferences["widths"])
        widths[key] = min(max(int(width), 44), 640)
        self._column_preferences["widths"] = widths
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str, int)
    def moveColumn(self, tab_id: str, key: str, offset: int) -> None:
        if tab_id.startswith("playlist:") and self._playlists_model is not None:
            self._playlists_model.moveColumn(key, offset)
            return
        if key not in _COLUMN_KEYS or offset not in {-1, 1}:
            return
        self._ensure_tab(tab_id)
        order = list(self._column_preferences["order"])
        if key not in order:
            return
        old_index = order.index(key)
        new_index = min(max(old_index + offset, 0), len(order) - 1)
        if new_index == old_index:
            return
        order.insert(new_index, order.pop(old_index))
        self._column_preferences["order"] = order
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str, str, bool)
    def moveColumnRelative(self, tab_id: str, key: str, target_key: str, after: bool) -> None:
        if tab_id.startswith("playlist:") and self._playlists_model is not None:
            self._playlists_model.moveColumnRelative(key, target_key, after)
            return
        if key not in _COLUMN_KEYS or target_key not in _COLUMN_KEYS or key == target_key:
            return
        self._ensure_tab(tab_id)
        order = list(self._column_preferences["order"])
        if key not in order or target_key not in order:
            return
        order.remove(key)
        target_index = order.index(target_key) + (1 if after else 0)
        order.insert(target_index, key)
        if order == self._column_preferences["order"]:
            return
        self._column_preferences["order"] = order
        self.layoutChanged.emit()
        self._persist()

    @Slot(bool)
    def setShowArtwork(self, visible: bool) -> None:
        visible = bool(visible)
        if self._column_preferences["showArtwork"] == visible:
            return
        self._column_preferences["showArtwork"] = visible
        self.layoutChanged.emit()
        self._persist()

    @Slot()
    def resetColumns(self) -> None:
        self._column_preferences = _copy_column_preferences(DEFAULT_COLUMN_PREFERENCES)
        self._refresh_hidden_sorts(set(self._column_preferences["hidden"]))
        self.layoutChanged.emit()
        self._persist()

    def _refresh_hidden_sorts(self, hidden: set[str]) -> None:
        reset_tabs: list[str] = []
        for tab_id, state in self._tab_states.items():
            if state.get("sortMode") == "manual" and state.get("sortKey") in hidden:
                self._set_default_sort(state)
                self._dirty_tabs.add(tab_id)
                reset_tabs.append(tab_id)
        if reset_tabs:
            self._revision += 1
            self.libraryChanged.emit()
            self._refresh_timer.start()

    @Slot(str, str)
    def setTabView(self, tab_id: str, view: str) -> None:
        if view not in {"list", "artwork"}:
            return
        self._tab_state(tab_id)["view"] = view
        self._capture_navigation()
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str)
    def setSearch(self, tab_id: str, query: str) -> None:
        self._cancel_explorer_track_action_for_tab(tab_id)
        self._tab_state(tab_id)["searchQuery"] = query[:256]
        self._capture_navigation()
        self._revision += 1
        self._dirty_tabs.add(tab_id)
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
        self._right_tab = tab if tab in {"info", "queue"} else "info"
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
            self._right_tab = tab if tab in {"info", "queue"} else "info"
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
    def setIslandEnabled(self, enabled: bool) -> None:
        self._island_enabled = bool(enabled)
        self.layoutChanged.emit()
        self._persist()

    @Slot(int)
    def setSidebarWidth(self, width: int) -> None:
        self._sidebar_width = min(max(int(width), 180), 420)
        self.layoutChanged.emit()
        self._persist()

    @Slot(int)
    def setRightPanelWidth(self, width: int) -> None:
        self._right_panel_width = min(max(int(width), 260), 480)
        self.layoutChanged.emit()
        self._persist()

    # -------------------------------------------------------------- selection and actions

    @Slot()
    @Slot(int)
    def clearSelection(self, group_index: int = -1) -> None:
        target = self._active_group if group_index < 0 else group_index
        if not 0 <= target < len(self._groups):
            return
        tab_id = str(self._groups[target]["active"])
        key = (target, tab_id)
        if target != self._active_group:
            self.setActiveGroup(target)
        if (
            self._pending_navigation_selection is not None
            and self._pending_navigation_selection[:2] == key
        ):
            self._pending_navigation_selection = None
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
        if (
            self._pending_navigation_selection is not None
            and self._pending_navigation_selection[:2] == key
        ):
            self._pending_navigation_selection = None
        selected = self._selection_by_tab.setdefault(key, [])
        anchor = self._anchor_by_tab.get(key, "")
        if mode == "toggle":
            if track_id in selected:
                selected.remove(track_id)
            else:
                selected.append(track_id)
                self._anchor_by_tab[key] = track_id
        elif mode == "range" and ordered:
            start = anchor if anchor in ordered else (selected[-1] if selected else track_id)
            first, last = sorted((ordered.index(start), ordered.index(track_id)))
            selected[:] = [str(item) for item in ordered[first : last + 1]]
            self._anchor_by_tab[key] = start
        else:
            selected[:] = [track_id]
            self._anchor_by_tab[key] = track_id
        self.selectionChanged.emit()
        self._persist()

    @Slot(list)
    def selectAll(self, ordered: list) -> None:
        tab_id = str(self._groups[self._active_group]["active"])
        key = (self._active_group, tab_id)
        if (
            self._pending_navigation_selection is not None
            and self._pending_navigation_selection[:2] == key
        ):
            self._pending_navigation_selection = None
        self._selection_by_tab[key] = [str(track_id) for track_id in ordered]
        self._anchor_by_tab[key] = str(ordered[0]) if ordered else ""
        self.selectionChanged.emit()
        self._persist()

    @Slot(str, str)
    @Slot(str, str, list)
    def playTrack(self, track_id: str, source: str, rows: list | None = None) -> None:
        self._cancel_explorer_track_action()
        if source.startswith("playlist:"):
            model = self._active_track_model(source)
            captured = rows if rows is not None else model.rows_snapshot() if model else []
            chosen = next((r for r in captured if r.get("id") == track_id), None)
            playable = [
                dict(r) | {"id": r["trackId"]}
                for r in captured
                if r.get("available") and r.get("trackId")
            ]
            if chosen is None or not chosen.get("available"):
                self._set_message("This track is unavailable. Locate a local file first.")
                return
            ids = [r["id"] for r in playable]
            if self._player is not None:
                detail = (
                    self._playlists_model.details(source.partition(":")[2])
                    if self._playlists_model
                    else {}
                )
                self._player.playQueueWithRows(
                    ids,
                    ids.index(chosen["trackId"]),
                    source,
                    detail.get("name", "Playlist"),
                    playable,
                )
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
        folder = _parse_folder_id(source)
        if folder is not None:
            root_id, relative = folder
        elif track:
            root_id, relative = str(track.get("rootId", "")), _folder_from_track(track)
        else:
            root_id, relative = "", ""
        model = self._active_track_model(f"folder:{root_id}/{relative}")
        if supplied_rows is not None:
            folder_rows = supplied_rows
            order = [str(row.get("id", "")) for row in folder_rows if row.get("id")]
        elif model:
            folder_rows = model.rows_snapshot()
            order = [str(row["id"]) for row in folder_rows]
        elif root_id:
            tab_id = f"folder:{root_id}/{relative}"
            state = self._tab_state(tab_id)
            folder_rows = self._library.tracks_in_folder(root_id, relative)
            query = str(state.get("searchQuery", "")).casefold().strip()
            if query:
                folder_rows = [
                    row
                    for row in folder_rows
                    if query
                    in " ".join(
                        str(row.get(key, ""))
                        for key in ("title", "artist", "album", "genre", "filename")
                    ).casefold()
                ]
            folder_rows = _sort_rows(
                folder_rows,
                str(state.get("sortKey", "fileCreatedAt")),
                bool(state.get("sortAscending", False)),
            )
            order = [str(row["id"]) for row in folder_rows]
        else:
            order = [track_id]
            folder_rows = [track] if track else []
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
        folder = _parse_folder_id(source)
        if folder is not None:
            root_id, relative = folder
            if relative:
                return Path(relative).name
            root = self._roots_by_id.get(root_id, {})
            return str(root.get("name") or track.get("title") or "Folder")
        return str(track.get("album") or track.get("title") or "Library")

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

    def _ensure_tab(self, tab_id: str) -> dict[str, Any]:
        state = self._tab_state(tab_id)
        if not state:
            kind, _, ref = tab_id.partition(":")
            title = {"settings": "Settings", "convert": "Convert", "tasks": "Tasks"}.get(
                kind, "Folder"
            )
            if kind == "folder":
                try:
                    root_id, relative = _parse_folder_ref(ref)
                    root = self._roots_by_id.get(root_id, {})
                    title = (
                        relative.rsplit("/", 1)[-1] if relative else str(root.get("name", "Folder"))
                    )
                except (ValueError, StopIteration):
                    pass
            state.update(
                {
                    "id": tab_id,
                    "kind": kind,
                    "ref": ref,
                    "title": title,
                    "sortMode": "default",
                    "sortKey": "index" if kind == "playlist" else "fileCreatedAt",
                    "sortAscending": kind == "playlist",
                    "view": "list",
                    "searchQuery": "",
                    "selectedIds": [],
                    "selectionAnchor": "",
                }
            )
        column_order = state.get("columnOrder", DEFAULT_COLUMN_PREFERENCES["order"])
        if not isinstance(column_order, list):
            column_order = list(DEFAULT_COLUMN_PREFERENCES["order"])
        valid_order = [key for key in column_order if isinstance(key, str) and key in _COLUMN_KEYS]
        state["columnOrder"] = list(
            dict.fromkeys(valid_order + DEFAULT_COLUMN_PREFERENCES["order"])
        )
        hidden = state.get("hiddenColumns", DEFAULT_COLUMN_PREFERENCES["hidden"])
        state["hiddenColumns"] = (
            [key for key in hidden if isinstance(key, str) and key in _COLUMN_KEYS]
            if isinstance(hidden, list)
            else list(DEFAULT_COLUMN_PREFERENCES["hidden"])
        )
        widths = dict(DEFAULT_COLUMN_PREFERENCES["widths"])
        saved_widths = state.get("columnWidths", {})
        if isinstance(saved_widths, dict):
            for key in _COLUMN_KEYS:
                try:
                    value = int(saved_widths.get(key, widths[key]))
                except (TypeError, ValueError, OverflowError):
                    continue
                widths[key] = 0 if key == "title" and value <= 0 else min(max(value, 44), 640)
        state["columnWidths"] = widths
        if state.get("sortMode") not in {"default", "manual"}:
            state["sortMode"] = "manual"
        return state

    def _tab_state(self, tab_id: str) -> dict[str, Any]:
        if not hasattr(self, "_tab_states"):
            self._tab_states: dict[str, dict[str, Any]] = {}
        return self._tab_states.setdefault(tab_id, {})

    def _restore_groups(self, raw_groups: list[Any]) -> list[dict[str, Any]]:
        self._tab_states: dict[str, dict[str, Any]] = {}
        groups: list[dict[str, Any]] = []
        for raw_group in raw_groups[:2]:
            if not isinstance(raw_group, dict):
                continue
            tab_ids = []
            for raw_tab in raw_group.get("tabs", []):
                if not isinstance(raw_tab, dict) or raw_tab.get("kind") not in {
                    "folder",
                    "playlist",
                }:
                    continue
                ref = str(raw_tab.get("ref", ""))
                if raw_tab.get("kind") == "folder":
                    try:
                        _parse_folder_ref(ref)
                    except ValueError:
                        continue
                tab_id = str(raw_tab.get("id", f"folder:{ref}"))
                self._tab_states[tab_id] = dict(raw_tab)
                if raw_tab.get("kind") == "folder":
                    self._set_default_sort(self._tab_states[tab_id])
                self._ensure_tab(tab_id)
                tab_ids.append(tab_id)
            active = str(raw_group.get("active", ""))
            if active not in tab_ids:
                active = tab_ids[0] if tab_ids else ""
            selections = raw_group.get("selections", {})
            if not isinstance(selections, dict):
                selections = {}
            groups.append({"tabs": tab_ids, "active": active, "selections": selections})
        return groups or [{"tabs": [], "active": "", "selections": {}}]

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
        if root_id is None:
            self._dirty_all_branches = True
            self._dirty_all_tabs = True
            self._dirty_root_ids.add("*")
        else:
            self._dirty_root_ids.add(root_id)
            for relative in changed_folders or {""}:
                self._dirty_folder_branches.add((root_id, relative))
                self._dirty_tabs.add(f"folder:{root_id}/{relative}")
        self._refresh_timer.start()

    def _refresh_models(self) -> None:
        if not self._jobs.accepting:
            return  # a refresh timer that fires after shutdown began has nothing to load
        if self._dirty_root_ids:
            self._dirty_root_ids.clear()
            self._request_folder_roots()
        dirty_branches = self._dirty_folder_branches
        self._dirty_folder_branches = set()
        if self._dirty_all_branches:
            for folder_id, job_id in tuple(self._folder_job_ids.items()):
                self._folder_request_generation[folder_id] = (
                    self._folder_request_generation.get(folder_id, 0) + 1
                )
                with suppress(LookupError, ValueError):
                    self._jobs.cancel(JobId.parse(job_id))
            self._folder_job_ids.clear()
            self._folder_model.invalidate_all_branches()
            self._dirty_all_branches = False
        else:
            for root_id, relative in dirty_branches:
                folder_id = f"root:{root_id}" if not relative else f"folder:{root_id}/{relative}"
                job_id = self._folder_job_ids.pop(folder_id, "")
                if job_id:
                    self._folder_request_generation[folder_id] = (
                        self._folder_request_generation.get(folder_id, 0) + 1
                    )
                    with suppress(LookupError, ValueError):
                        self._jobs.cancel(JobId.parse(job_id))
                self._folder_model.invalidate_branch(folder_id)
        if self._dirty_all_tabs:
            dirty_tabs = {self._model_identity(key)[1] for key in self._track_models}
            self._dirty_all_tabs = False
        else:
            dirty_tabs = self._dirty_tabs
        self._dirty_tabs = set()
        for model_key, model in tuple(self._track_models.items()):
            group_index, tab_id = self._model_identity(model_key)
            if tab_id not in dirty_tabs or group_index >= len(self._groups):
                continue
            state = dict(self._tab_state(tab_id))
            state.update(self._group_tab_states.get((group_index, tab_id), {}))
            if state.get("kind") not in {"folder", "playlist"}:
                model.replace([])
                continue
            self._track_request_keys.pop(model_key, None)
            self._request_track_rows(
                model_key,
                tab_id,
                group_index,
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
        active: set[tuple[str, str]] = set()
        for group in self._groups:
            tab_id = str(group["active"])
            if not tab_id.startswith("folder:"):
                continue
            with suppress(ValueError):
                parsed = _parse_folder_id(tab_id)
                if parsed is not None:
                    active.add(parsed)
        targets: dict[str, tuple[str, str]] = {}
        for root_id, relative in sorted(active):
            root = self._roots_by_id.get(root_id)
            if root is not None:
                path = str(Path(str(root["path"])) / relative)
                targets[os.path.normcase(os.path.normpath(path))] = (root_id, relative)
        self._watch_targets = targets
        self._folder_watch.set_watched(
            str(Path(str(self._roots_by_id[root_id]["path"])) / relative)
            for root_id, relative in sorted(active)
            if root_id in self._roots_by_id
        )
        newly_visible = active - self._active_folder_tabs
        self._active_folder_tabs = active
        for root_id, relative in sorted(newly_visible):
            self._request_folder_refresh(root_id, relative)

    def _on_folder_watch_changed(self, path: str) -> None:
        target = self._watch_targets.get(os.path.normcase(os.path.normpath(path)))
        if target is not None:
            self._request_folder_refresh(*target)

    def _on_application_state_changed(self, state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            for root_id, relative in sorted(self._active_folder_tabs):
                self._request_folder_refresh(root_id, relative)

    def _request_folder_refresh(self, root_id: str, relative: str) -> None:
        root = self._roots_by_id.get(root_id)
        if root is None or root_id in self._jobs_by_root or not self._jobs.accepting:
            return  # a running full scan will see the change
        key = (root_id, relative)
        if key in self._folder_refresh_jobs:
            self._folder_refresh_pending.add(key)
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
            job_id = self._jobs.submit(task, label="Refresh folder", visible=False, priority=1)
        except RuntimeError:
            return
        self._folder_refresh_jobs[key] = str(job_id)

    def _on_folder_refreshed(self, root_id: str, relative: str, payload: object) -> None:
        key = (root_id, relative)
        self._folder_refresh_jobs.pop(key, None)
        detail = payload if isinstance(payload, dict) else {}
        folders = {str(item) for item in detail.get("folders", [])}
        if folders:
            self._refresh_library(root_id, folders | {relative})
        if detail.get("unstable") and self._folder_refresh_unstable.get(key, 0) < 15:
            self._folder_refresh_unstable[key] = self._folder_refresh_unstable.get(key, 0) + 1
            QTimer.singleShot(2_000, lambda: self._request_folder_refresh(root_id, relative))
        elif not detail.get("unstable"):
            self._folder_refresh_unstable.pop(key, None)
        if key in self._folder_refresh_pending:
            self._folder_refresh_pending.discard(key)
            self._request_folder_refresh(root_id, relative)

    def _on_scan_batch(self, root_id: str, request_id: str, detail: object) -> None:
        if self._requests.get(root_id) != request_id:
            return
        payload = detail if isinstance(detail, dict) else {}
        count = int(payload.get("count", 0))
        self._scan_counts[root_id] = self._scan_counts.get(root_id, 0) + count
        if request_id not in self._quiet_requests:
            self._set_message(f"Indexed {self._scan_counts[root_id]:,} audio files…")
        self._revision += 1
        self.libraryChanged.emit()
        changed_folders = payload.get("folders", [])
        for relative in changed_folders if isinstance(changed_folders, list) else []:
            folder = str(relative)
            self._dirty_folder_branches.add((root_id, folder))
            self._dirty_tabs.add(f"folder:{root_id}/{folder}")
        self._refresh_timer.start()

    def _on_scan_finished(self, root_id: str, request_id: str, result: dict[str, Any]) -> None:
        if self._requests.get(root_id) != request_id:
            return
        self._requests.pop(root_id, None)
        quiet = request_id in self._quiet_requests
        self._quiet_requests.discard(request_id)
        self._jobs_by_root.pop(root_id, None)
        self._dirty_root_ids.add(root_id)
        changed_folders = result.get("changedFolders", [])
        for relative in changed_folders if isinstance(changed_folders, list) else []:
            folder = str(relative)
            self._dirty_folder_branches.add((root_id, folder))
            self._dirty_tabs.add(f"folder:{root_id}/{folder}")
        self._refresh_timer.start()
        if result["cancelled"]:
            self._set_message("Folder indexing cancelled; existing references were kept.")
        elif not result["available"]:
            self._set_message("This folder is unavailable. Reconnect it and rescan to continue.")
        elif result["issues"]:
            self._set_message(
                f"Indexing finished with {len(result['issues'])} folder access issue(s)."
            )
        elif not result["complete"]:
            self._set_message(
                "Indexing did not complete. Existing references were kept; rescan to retry."
            )
        elif not quiet:
            self._set_message(
                f"Folder indexing complete: {self._scan_counts.get(root_id, 0):,} audio files."
            )
        self._persist()

    def _on_metadata_changed(self) -> None:
        self._revision += 1
        self.libraryChanged.emit()
        if self._player is not None and self._player.playing_id_value():
            self._player.refreshTrack(self._player.playing_id_value())
        self._refresh_timer.start()

    def _prepare_visible_metadata(self) -> None:
        if self._metadata_editor is None:
            return
        if self._right_visible and not self._fullscreen and self._right_tab == "info":
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
        state["sortMode"] = "default"
        state["sortKey"] = "index" if state.get("kind") == "playlist" else "fileCreatedAt"
        state["sortAscending"] = state.get("kind") == "playlist"

    def _persist(self) -> None:
        if self._session_closed:
            return
        self._session_timer.start()

    def _session_snapshot(self) -> dict[str, Any]:
        return {
            "version": 1,
            "expanded": sorted(self._expanded),
            "groups": [
                {
                    "tabs": [dict(self._tab_state(tab_id)) for tab_id in group["tabs"]],
                    "active": group["active"],
                    "selections": {
                        tab_id: {
                            "ids": list(self._selection_by_tab.get((group_index, tab_id), [])),
                            "anchor": self._anchor_by_tab.get((group_index, tab_id), ""),
                        }
                        for tab_id in group["tabs"]
                    },
                }
                for group_index, group in enumerate(self._groups)
            ],
            "activeGroup": self._active_group,
            "activity": self._activity,
            "sidebarVisible": self._sidebar_visible,
            "rightPanelVisible": self._right_visible,
            "rightPanelTab": self._right_tab,
            "sidebarWidth": self._sidebar_width,
            "rightPanelWidth": self._right_panel_width,
            "islandEnabled": self._island_enabled,
            "columnPreferences": _copy_column_preferences(self._column_preferences),
        }

    @Slot()
    def _write_pending_session(self) -> None:
        state = self._session_snapshot()
        if self._session_future is not None:
            self._session_pending = state
            return
        self._submit_session_write(state)

    def _submit_session_write(self, state: dict[str, Any]) -> None:
        future = self._session_executor.submit(self._session.save, state)
        self._session_future = future

        def completed(done: Future[None]) -> None:
            try:
                error = done.exception()
            except BaseException as caught:
                error = caught
            self.sessionWriteFinished.emit(done, error)

        future.add_done_callback(completed)

    @Slot(object, object)
    def _on_session_write_finished(self, future: object, error: object) -> None:
        if future is not self._session_future:
            return
        self._session_future = None
        try:
            if error is not None:
                raise error if isinstance(error, BaseException) else RuntimeError(str(error))
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as caught:
            self._set_message(f"Could not save this workspace: {caught}")
        pending = self._session_pending
        self._session_pending = None
        if pending is not None and not self._session_closed:
            self._submit_session_write(pending)

    @Slot()
    def flush_session(self) -> None:
        """Persist the latest independent snapshot before SQLite is closed."""
        if self._session_closed:
            return
        self._folder_watch.close()
        self._session_timer.stop()
        state = self._session_snapshot()
        self._session_closed = True
        self._session_pending = None
        current = self._session_future
        try:
            if current is not None:
                current.result()
            self._session_future = None
            self._session_executor.submit(self._session.save, state).result()
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
            self._set_message(f"Could not save this workspace: {error}")
        finally:
            self._session_executor.shutdown(wait=True)


def _parse_folder_id(folder_id: str) -> tuple[str, str] | None:
    if folder_id.startswith("root:"):
        return folder_id.partition(":")[2], ""
    if folder_id.startswith("folder:"):
        return _parse_folder_ref(folder_id.partition(":")[2])
    return None


def _parse_folder_ref(ref: str) -> tuple[str, str]:
    root_id, separator, relative = ref.partition("/")
    if not root_id or not re.fullmatch(r"[0-9a-fA-F-]{36}", root_id):
        raise ValueError("invalid library root reference")
    if not separator or not relative:
        return root_id, ""
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("invalid relative folder path")
    return root_id, relative_path.as_posix() if separator else ""


def _local_path(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        if parsed.netloc:
            path = f"//{parsed.netloc}{path}"
        return path
    return value.strip()


def _sort_rows(rows: list[dict[str, Any]], key: str, ascending: bool) -> list[dict[str, Any]]:
    if key not in _SORT_KEYS or key == "index":
        return list(rows)
    field = {
        "duration": "seconds",
        "fileCreatedAt": "fileCreatedAtNs",
        "fileModifiedAt": "fileModifiedAtNs",
    }.get(key, key)
    numeric_fields = {"fileCreatedAtNs", "fileModifiedAtNs", "seconds", "bpm", "bitrate"}
    present: list[tuple[object, str, str, dict[str, Any]]] = []
    missing = []
    for row in rows:
        value = row.get(field)
        if value is None or value == "":
            missing.append(row)
            continue
        try:
            sort_value: object = (
                int(value)
                if field in {"fileCreatedAtNs", "fileModifiedAtNs"}
                else float(value)
                if field in numeric_fields
                else str(value).casefold()
            )
        except (TypeError, ValueError):
            missing.append(row)
            continue
        present.append(
            (
                sort_value,
                str(row.get("title", "")).casefold(),
                str(row.get("id", "")),
                row,
            )
        )
    # Stable passes keep title and UUID ties ascending in either direction.
    present.sort(key=lambda item: (item[1], item[2]))
    present.sort(key=lambda item: cast(Any, item[0]), reverse=not ascending)
    missing.sort(key=lambda row: (str(row.get("title", "")).casefold(), str(row.get("id", ""))))
    return [item[3] for item in present] + missing


def _copy_column_preferences(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else DEFAULT_COLUMN_PREFERENCES
    return {
        "order": list(source.get("order", DEFAULT_COLUMN_PREFERENCES["order"])),
        "hidden": list(source.get("hidden", DEFAULT_COLUMN_PREFERENCES["hidden"])),
        "widths": dict(source.get("widths", DEFAULT_COLUMN_PREFERENCES["widths"])),
        "showArtwork": bool(source.get("showArtwork", True)),
    }


def _folder_from_track(track: dict[str, Any]) -> str:
    return str(track.get("relativePath", "")).rpartition("/")[0]
