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

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from mtee.domain.jobs import JobCancelledError, JobId
from mtee.models.conversion_queue_model import ConversionQueueModel
from mtee.models.folder_tree_model import FolderTreeModel
from mtee.models.metadata_editor_model import MetadataEditorModel
from mtee.models.player_model import PlayerModel
from mtee.models.track_list_model import TrackListModel
from mtee.models.trash_model import TrashModel
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.workspace_repository import WorkspaceRepository
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
_COLUMN_KEYS = set(_SORT_KEYS) - {"index"}
_DEFAULT_COLUMN_ORDER = [
    "title",
    "artist",
    "album",
    "genre",
    "bpm",
    "key",
    "duration",
    "format",
    "filename",
    "bitrate",
    "fileCreatedAt",
    "fileModifiedAt",
]
_DEFAULT_HIDDEN_COLUMNS = [
    "album",
    "duration",
    "format",
    "filename",
    "bitrate",
    "fileCreatedAt",
    "fileModifiedAt",
]
_DEFAULT_COLUMN_WIDTHS = {
    "title": 0,
    "artist": 150,
    "album": 150,
    "genre": 110,
    "bpm": 52,
    "key": 52,
    "duration": 70,
    "format": 72,
    "filename": 180,
    "bitrate": 78,
    "fileCreatedAt": 155,
    "fileModifiedAt": 155,
}
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
    activationRequested = Signal(str, list)
    playbackChanged = Signal()
    positionChanged = Signal()
    folderRootsReady = Signal(int, object, object)
    folderBranchReady = Signal(str, int, object, object)
    trackRowsReady = Signal(str, int, object)
    explorerTrackReady = Signal(int, object, object)
    sessionWriteFinished = Signal(object, object)

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
        self._metadata_editor: MetadataEditorModel | None = None
        self._conversion_model: ConversionQueueModel | None = None
        self._trash_model: TrashModel | None = None
        self._scanner = LibraryScanner()
        self._reader = MetadataReader()
        self._shell_reveal = WindowsShellReveal()
        self._roots_by_id: dict[str, dict[str, Any]] = {}
        self._resume_roots_requested = False
        self._state = session.load()
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
        self._island_enabled = bool(self._state.get("islandEnabled", True))
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
        self.batchReady.connect(self._on_scan_batch)
        self.scanFinished.connect(self._on_scan_finished)
        self.folderRootsReady.connect(self._on_folder_roots_ready)
        self.folderBranchReady.connect(self._on_folder_branch_ready)
        self.trackRowsReady.connect(self._on_track_rows_ready)
        self.explorerTrackReady.connect(self._on_explorer_track_ready)
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
                "tabs": [dict(self._tab_state(tab_id)) for tab_id in group["tabs"]],
                "active": group["active"],
            }
            for group in self._groups
        ]

    @Property(list, notify=layoutChanged)
    def groups(self) -> list[dict[str, Any]]:
        return self.groups_snapshot()

    @Property(int, notify=layoutChanged)
    def activeGroup(self) -> int:
        return self._active_group

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
        return self.selected_ids_snapshot()

    def selected_ids_snapshot(self) -> list[str]:
        tab_id = str(self._groups[self._active_group]["active"])
        return list(self._selection_by_tab.get((self._active_group, tab_id), []))

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

    @Property(list, constant=True)
    def playlists(self) -> list[dict[str, Any]]:
        return []

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
            ("BPM", "bpm"),
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
    def trackModelForTab(
        self, tab_id: str, kind: str, ref: str, sort_key: str, ascending: bool
    ) -> QObject:
        model = self._track_models.get(tab_id)
        if model is None:
            model = TrackListModel(self)
            self._track_models[tab_id] = model
        if kind == "folder":
            self._request_track_rows(tab_id, kind, ref, sort_key, ascending)
        else:
            model.replace([])
        return model

    def _request_track_rows(
        self, tab_id: str, kind: str, ref: str, sort_key: str, ascending: bool
    ) -> None:
        tab = self._tab_state(tab_id)
        query = str(tab.get("searchQuery", "")).casefold().strip()
        key = (kind, ref, sort_key, bool(ascending), query)
        if self._track_request_keys.get(tab_id) == key:
            return
        pending = self._pending_explorer_track
        if pending is not None and pending["tab_id"] == tab_id:
            self._cancel_explorer_track_action()
        generation = self._track_request_generation.get(tab_id, 0) + 1
        self._track_request_generation[tab_id] = generation
        previous_job = self._track_job_ids.get(tab_id)
        if previous_job:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(previous_job))
        self._track_request_keys[tab_id] = key

        def read_rows(context: JobContext) -> None:
            context.raise_if_cancelled()
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
            ordered = _sort_rows(rows, sort_key, ascending)
            context.raise_if_cancelled()
            self.trackRowsReady.emit(tab_id, generation, ordered)

        job_id = self._jobs.submit(read_rows, label="Load folder contents", visible=False)
        self._track_job_ids[tab_id] = str(job_id)

    @Slot(str, int, object)
    def _on_track_rows_ready(self, tab_id: str, generation: int, rows: object) -> None:
        if generation != self._track_request_generation.get(tab_id):
            return
        model = self._track_models.get(tab_id)
        if model is None or not isinstance(rows, list):
            return
        self._track_job_ids.pop(tab_id, None)
        model.replace(rows)
        pending = self._pending_explorer_track
        if (
            pending is not None
            and pending["stage"] == "rows"
            and pending["tab_id"] == tab_id
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
        model = self._track_models.get(tab_id)
        if model is None:
            self._request_track_rows(tab_id, kind, ref, sort_key, ascending)
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
        return []

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
            try:
                for batch in self._scanner.scan(
                    root["path"], is_cancelled=lambda: context.is_cancelled
                ):
                    issues.extend(issue.message for issue in batch.issues)
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
        if not self._open_folder(*parsed):
            return
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
        if self._open_folder(root_id, relative):
            self.layoutChanged.emit()
            self.selectionChanged.emit()
            self._persist()

        ref = f"{root_id}/{relative}"
        tab_id = f"folder:{ref}"
        state = self._ensure_tab(tab_id)
        sort_key = str(state.get("sortKey", "index"))
        ascending = bool(state.get("sortAscending", True))
        model = cast(
            TrackListModel,
            self.trackModelForTab(tab_id, "folder", ref, sort_key, ascending),
        )
        query = str(state.get("searchQuery", "")).casefold().strip()
        request_key = ("folder", ref, sort_key, ascending, query)
        request_generation = self._track_request_generation.get(tab_id, 0)
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
            self._track_request_keys.get(tab_id) == request_key
            and tab_id not in self._track_job_ids
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
        self._activity = activity
        self._sidebar_visible = True
        self._fullscreen = False
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
        self._set_message("Playlists become available in a later step.")

    @Slot()
    def openConvert(self) -> None:
        self._cancel_explorer_track_action()
        self._activity = "convert"
        self._sidebar_visible = True
        self._open_special_tab("convert:", "Convert")
        if self._conversion_model is not None:
            self._conversion_model.ensure_capabilities()
        self.layoutChanged.emit()
        self._persist()

    @Slot()
    def openSettings(self) -> None:
        self._cancel_explorer_track_action()
        self._open_special_tab("settings:", "Settings")
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

    @Slot(int, str)
    def activateTab(self, group_index: int, tab_id: str) -> None:
        if (
            not 0 <= group_index < len(self._groups)
            or tab_id not in self._groups[group_index]["tabs"]
        ):
            return
        self._cancel_explorer_track_action()
        self._active_group = group_index
        self._groups[group_index]["active"] = tab_id
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(int)
    def setActiveGroup(self, group_index: int) -> None:
        if not 0 <= group_index < len(self._groups) or group_index == self._active_group:
            return
        self._cancel_explorer_track_action()
        self._active_group = group_index
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
        old_index = tabs.index(tab_id)
        tabs.remove(tab_id)
        if group["active"] == tab_id:
            group["active"] = tabs[min(old_index, len(tabs) - 1)] if tabs else ""
        if not any(tab_id in item["tabs"] for item in self._groups):
            self._tab_states.pop(tab_id, None)
            model = self._track_models.pop(tab_id, None)
            if model is not None:
                model.deleteLater()
            self._track_request_generation[tab_id] = (
                self._track_request_generation.get(tab_id, 0) + 1
            )
            job_id = self._track_job_ids.pop(tab_id, "")
            if job_id:
                with suppress(LookupError, ValueError):
                    self._jobs.cancel(JobId.parse(job_id))
            self._track_request_keys.pop(tab_id, None)
            self._selection_by_tab = {
                key: value for key, value in self._selection_by_tab.items() if key[1] != tab_id
            }
            self._anchor_by_tab = {
                key: value for key, value in self._anchor_by_tab.items() if key[1] != tab_id
            }
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
        else:
            for tab_id in self._groups[1]["tabs"]:
                if tab_id not in self._groups[0]["tabs"]:
                    self._groups[0]["tabs"].append(tab_id)
            if not self._groups[0]["active"]:
                self._groups[0]["active"] = self._groups[1]["active"]
            self._groups.pop()
            self._active_group = 0
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(str, str)
    def setSort(self, tab_id: str, key: str) -> None:
        if key not in _SORT_KEYS:
            return
        self._cancel_explorer_track_action_for_tab(tab_id)
        state = self._tab_state(tab_id)
        state["sortAscending"] = (
            not bool(state.get("sortAscending", True)) if state.get("sortKey") == key else True
        )
        state["sortKey"] = key
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
        state = self._ensure_tab(tab_id)
        hidden = list(state.get("hiddenColumns", []))
        if key in hidden:
            hidden.remove(key)
        else:
            hidden.append(key)
        state["hiddenColumns"] = hidden
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str, int)
    def resizeColumn(self, tab_id: str, key: str, width: int) -> None:
        if key not in _COLUMN_KEYS:
            return
        state = self._ensure_tab(tab_id)
        widths = dict(state.get("columnWidths", _DEFAULT_COLUMN_WIDTHS))
        widths[key] = min(max(int(width), 44), 640)
        state["columnWidths"] = widths
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str, int)
    def moveColumn(self, tab_id: str, key: str, offset: int) -> None:
        if key not in _COLUMN_KEYS or offset not in {-1, 1}:
            return
        state = self._ensure_tab(tab_id)
        order = list(state.get("columnOrder", _DEFAULT_COLUMN_ORDER))
        if key not in order:
            return
        old_index = order.index(key)
        new_index = min(max(old_index + offset, 0), len(order) - 1)
        if new_index == old_index:
            return
        order.insert(new_index, order.pop(old_index))
        state["columnOrder"] = order
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str)
    def setTabView(self, tab_id: str, view: str) -> None:
        if view not in {"list", "artwork"}:
            return
        self._tab_state(tab_id)["view"] = view
        self.layoutChanged.emit()
        self._persist()

    @Slot(str, str)
    def setSearch(self, tab_id: str, query: str) -> None:
        self._cancel_explorer_track_action_for_tab(tab_id)
        self._tab_state(tab_id)["searchQuery"] = query[:256]
        self._revision += 1
        self._dirty_tabs.add(tab_id)
        self.libraryChanged.emit()
        self._refresh_timer.start()
        self._persist()

    @Slot(bool)
    def setRightPanelVisible(self, visible: bool) -> None:
        self._right_visible = bool(visible)
        self._prepare_visible_metadata()
        self.layoutChanged.emit()
        self._persist()

    @Slot(str)
    def showRightPanel(self, tab: str) -> None:
        self._right_tab = tab if tab in {"info", "queue"} else "info"
        self._right_visible = True
        self._prepare_visible_metadata()
        self.layoutChanged.emit()
        self._persist()

    @Slot(str)
    def toggleRightPanel(self, tab: str) -> None:
        if self._right_visible and self._right_tab == tab:
            self._right_visible = False
        else:
            self._right_visible = True
            self._right_tab = tab if tab in {"info", "queue"} else "info"
        self._prepare_visible_metadata()
        self.layoutChanged.emit()
        self._persist()

    @Slot(bool)
    def setFullscreen(self, enabled: bool) -> None:
        self._fullscreen = bool(enabled)
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

    @Slot(str, str, list)
    def selectTrack(self, track_id: str, mode: str = "single", ordered: list | None = None) -> None:
        self._cancel_explorer_track_action()
        tab_id = str(self._groups[self._active_group]["active"])
        key = (self._active_group, tab_id)
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
        self._selection_by_tab[key] = [str(track_id) for track_id in ordered]
        self._anchor_by_tab[key] = str(ordered[0]) if ordered else ""
        self.selectionChanged.emit()
        self._persist()

    @Slot(str, str)
    @Slot(str, str, list)
    def playTrack(self, track_id: str, source: str, rows: list | None = None) -> None:
        self._cancel_explorer_track_action()
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
        model = self._track_models.get(f"folder:{root_id}/{relative}")
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
                str(state.get("sortKey", "index")),
                bool(state.get("sortAscending", True)),
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
        self._set_message("Playlists become available in a later step.")

    @Slot(list, str)
    def togglePlaylist(self, _track_ids: list, _playlist_id: str) -> None:
        return

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
            title = "Folder"
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
                    "sortKey": "index",
                    "sortAscending": True,
                    "view": "list",
                    "searchQuery": "",
                    "selectedIds": [],
                    "selectionAnchor": "",
                }
            )
        column_order = state.get("columnOrder", _DEFAULT_COLUMN_ORDER)
        if not isinstance(column_order, list):
            column_order = list(_DEFAULT_COLUMN_ORDER)
        valid_order = [key for key in column_order if isinstance(key, str) and key in _COLUMN_KEYS]
        state["columnOrder"] = list(dict.fromkeys(valid_order + _DEFAULT_COLUMN_ORDER))
        hidden = state.get("hiddenColumns", _DEFAULT_HIDDEN_COLUMNS)
        state["hiddenColumns"] = (
            [key for key in hidden if isinstance(key, str) and key in _COLUMN_KEYS]
            if isinstance(hidden, list)
            else list(_DEFAULT_HIDDEN_COLUMNS)
        )
        widths = dict(_DEFAULT_COLUMN_WIDTHS)
        saved_widths = state.get("columnWidths", {})
        if isinstance(saved_widths, dict):
            for key in _COLUMN_KEYS:
                try:
                    value = int(saved_widths.get(key, widths[key]))
                except (TypeError, ValueError, OverflowError):
                    continue
                widths[key] = 0 if key == "title" and value <= 0 else min(max(value, 44), 640)
        state["columnWidths"] = widths
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
                if not isinstance(raw_tab, dict) or raw_tab.get("kind") != "folder":
                    continue
                ref = str(raw_tab.get("ref", ""))
                try:
                    _parse_folder_ref(ref)
                except ValueError:
                    continue
                tab_id = str(raw_tab.get("id", f"folder:{ref}"))
                self._tab_states[tab_id] = dict(raw_tab)
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
        return self._track_models.get(active)

    def _refresh_library(
        self, root_id: str | None = None, changed_folders: set[str] | None = None
    ) -> None:
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
            dirty_tabs = set(self._track_models)
            self._dirty_all_tabs = False
        else:
            dirty_tabs = self._dirty_tabs
        self._dirty_tabs = set()
        for tab_id in dirty_tabs:
            model = self._track_models.get(tab_id)
            if model is None:
                continue
            state = self._tab_state(tab_id)
            if state.get("kind") != "folder":
                model.replace([])
                continue
            self._track_request_keys.pop(tab_id, None)
            self._request_track_rows(
                tab_id,
                "folder",
                str(state.get("ref", "")),
                str(state.get("sortKey", "index")),
                bool(state.get("sortAscending", True)),
            )
        for folder_id in tuple(self._expanded):
            if self._folder_model.is_expanded(folder_id) and not self._folder_model.branch_loaded(
                folder_id
            ):
                self._request_folder_branch(folder_id)
        self.explorerChanged.emit()

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
    present = []
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
                if field in {"bpm", "seconds", "bitrate"}
                else str(value).casefold()
            )
        except (TypeError, ValueError):
            sort_value = str(value).casefold()
        present.append((sort_value, str(row["id"]), row))
    present.sort(key=lambda item: (item[0], item[1]), reverse=not ascending)
    return [item[2] for item in present] + sorted(missing, key=lambda row: str(row["id"]))


def _folder_from_track(track: dict[str, Any]) -> str:
    return str(track.get("relativePath", "")).rpartition("/")[0]
