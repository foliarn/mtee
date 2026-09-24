"""Live Explorer state, folder browsing and navigation actions for QML."""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import suppress
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlparse

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from mtee.domain.jobs import JobCancelledError, JobId
from mtee.models.file_operation_model import FileOperationModel
from mtee.models.folder_tree_model import FolderTreeModel
from mtee.models.metadata_editor_model import MetadataEditorModel
from mtee.models.player_model import PlayerModel
from mtee.models.track_list_model import TrackListModel
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.workspace_repository import WorkspaceRepository
from mtee.services.jobs import JobContext, JobService
from mtee.services.library_scanner import LibraryScanner
from mtee.services.metadata_reader import MetadataReader

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
    "filename",
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
]
_DEFAULT_HIDDEN_COLUMNS = ["album", "duration", "format", "filename"]
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
    batchReady = Signal(str, str, object)
    scanFinished = Signal(str, str, object)
    activationRequested = Signal(str, list)
    playbackChanged = Signal()
    positionChanged = Signal()

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
        self._file_operations: FileOperationModel | None = None
        self._scanner = LibraryScanner()
        self._reader = MetadataReader()
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
        self._right_tab = str(self._state.get("rightPanelTab", "info"))
        self._sidebar_width = int(self._state.get("sidebarWidth", 240))
        self._right_panel_width = int(self._state.get("rightPanelWidth", 360))
        self._fullscreen = False
        self._island_enabled = False
        self._message = (
            "The saved workspace was invalid. MTEE restored a safe default layout."
            if session.load_recovered
            else ""
        )
        self._revision = 0
        self._requests: dict[str, str] = {}
        self._jobs_by_root: dict[str, str] = {}
        self._scan_counts: dict[str, int] = {}
        self._track_models: dict[str, TrackListModel] = {}
        self._folder_model = FolderTreeModel(library, self)
        self._folder_model.refresh(self._expanded)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(90)
        self._refresh_timer.timeout.connect(self._refresh_models)
        self.batchReady.connect(self._on_scan_batch)
        self.scanFinished.connect(self._on_scan_finished)
        jobs.jobUpdated.connect(self._on_job_updated)
        if player is not None:
            player.playbackChanged.connect(self.playbackChanged.emit)
            player.playbackChanged.connect(self.positionChanged.emit)
        self._persist()

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
        return False

    @Property(list, notify=libraryChanged)
    def convertInputs(self) -> list[dict[str, Any]]:
        return []

    @Property(list, notify=libraryChanged)
    def convertBatches(self) -> list[dict[str, Any]]:
        return []

    @Property(list, notify=libraryChanged)
    def tasks(self) -> list[dict[str, Any]]:
        result = []
        for status in self._jobs.statuses():
            result.append(
                {
                    "id": str(status.job_id),
                    "title": status.label,
                    "status": status.state.value,
                    "summary": status.error.message if status.error else "",
                    "progress": round(status.progress * 100),
                }
            )
        return result

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
    def fileOperations(self) -> QObject:
        return self._file_operations if self._file_operations is not None else self

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
            ("Bitrate", "bitrate"),
            ("Sample rate", "sampleRate"),
            ("Size", "size"),
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

    def attach_metadata_editor(self, editor: MetadataEditorModel) -> None:
        """Attach the single editor shared by the inspector and Fullscreen player."""
        if self._metadata_editor is not None:
            raise RuntimeError("A metadata editor is already attached to this workspace.")
        self._metadata_editor = editor
        editor.setParent(self)
        editor.changed.connect(self._on_metadata_changed)
        self.selectionChanged.connect(editor.refresh_selection)
        editor.refresh_selection()

    def attach_file_operations(self, model: FileOperationModel) -> None:
        """Attach the shared file operation model and refresh UUID-backed views."""
        if self._file_operations is not None:
            raise RuntimeError("A file operation model is already attached to this workspace.")
        self._file_operations = model
        model.setParent(self)
        model.operationFinished.connect(self._on_file_operation_finished)
        model.recoveryChecked.connect(self._on_file_recovery_checked)
        recovered = cast(list[dict[str, Any]], model.recoveryOperations)
        if recovered:
            self._on_file_recovery_checked(recovered)

    @Slot()
    def _on_file_operation_finished(self) -> None:
        self._refresh_library()
        if self._metadata_editor is not None:
            self._metadata_editor.refresh_selection()
        if self._file_operations is not None:
            self._set_message(cast(str, self._file_operations.message))

    @Slot(object)
    def _on_file_recovery_checked(self, operations: object) -> None:
        if isinstance(operations, list) and operations:
            self._set_message(
                f"{len(operations)} file operation(s) need inspection before more file changes."
            )

    @Slot(str, str, str, str, bool, result=QObject)
    def trackModelForTab(
        self, tab_id: str, kind: str, ref: str, sort_key: str, ascending: bool
    ) -> QObject:
        model = self._track_models.get(tab_id)
        if model is None:
            model = TrackListModel(self)
            self._track_models[tab_id] = model
        if kind == "folder":
            root_id, relative = _parse_folder_ref(ref)
            rows = self._library.tracks_in_folder(root_id, relative)
            tab = self._tab_state(tab_id)
            query = str(tab.get("searchQuery", "")).casefold().strip()
            if query:
                rows = [
                    row
                    for row in rows
                    if query
                    in " ".join(
                        str(row.get(key, ""))
                        for key in ("title", "artist", "album", "genre", "filename")
                    ).casefold()
                ]
            model.replace(_sort_rows(rows, sort_key, ascending))
        else:
            model.replace([])
        return model

    @Slot(str, str, str, bool, int, result=list)
    def tabTracks(
        self, kind: str, ref: str, sort_key: str, ascending: bool, _revision: int = 0
    ) -> list[dict[str, Any]]:
        if kind != "folder":
            return []
        root_id, relative = _parse_folder_ref(ref)
        return _sort_rows(self._library.tracks_in_folder(root_id, relative), sort_key, ascending)

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
        self._expanded.add(f"root:{root_id}")
        self._open_folder(root_id, "")
        self._refresh_library()
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self.rescanRoot(root_id)
        self._persist()
        return root_id

    @Slot(str, result=str)
    def rescanRoot(self, root_id: str) -> str:
        root = next((item for item in self._library.roots() if item["id"] == root_id), None)
        if root is None:
            self._set_message("This folder is no longer in the library.")
            return ""
        previous_job = self._jobs_by_root.get(root_id)
        if previous_job:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(previous_job))
        generation = self._library.begin_scan(root_id)
        request_id = os.urandom(16).hex()
        self._requests[root_id] = request_id
        self._scan_counts[root_id] = 0
        self._refresh_library()

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
                    self._library.upsert_folders(root_id, batch.folders, generation)
                    records = []
                    for entry in batch.entries:
                        snapshot = self._reader.read(entry.path)
                        records.append((entry.relative_path, entry.path, entry.revision, snapshot))
                    identities = self._library.upsert_locations(root_id, records, generation)
                    if identities or batch.folders:
                        self.batchReady.emit(root_id, request_id, len(identities))
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
                self._library.finish_scan(
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
                    },
                )
            if cancelled:
                raise JobCancelledError(request_id)

        job_id = self._jobs.submit(task, label=f"Indexing {root['name']}")
        self._jobs_by_root[root_id] = str(job_id)
        self._persist()
        return request_id

    @Slot()
    def resumeRoots(self) -> None:
        for root in self._library.roots():
            self.rescanRoot(str(root["id"]))

    @Slot(str)
    def toggleFolder(self, folder_id: str) -> None:
        if folder_id in self._expanded:
            self._expanded.remove(folder_id)
        else:
            self._expanded.add(folder_id)
        self._refresh_library()
        self._persist()

    @Slot(str)
    def openFolder(self, folder_id: str) -> None:
        parsed = _parse_folder_id(folder_id)
        if parsed is None:
            return
        self._open_folder(*parsed)
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    def _open_folder(self, root_id: str, relative: str) -> None:
        ref = f"{root_id}/{relative}"
        tab_id = f"folder:{ref}"
        self._ensure_tab(tab_id)
        group = self._groups[self._active_group]
        if tab_id not in group["tabs"]:
            group["tabs"].append(tab_id)
        group["active"] = tab_id
        key = (self._active_group, tab_id)
        self._selection_by_tab.setdefault(key, [])
        self._anchor_by_tab.setdefault(key, "")

    # -------------------------------------------------------------- layout actions

    @Slot(str)
    def setActivity(self, activity: str) -> None:
        if activity not in _ACTIVITIES:
            return
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
        self._activity = "convert"
        self._sidebar_visible = True
        self._open_special_tab("convert:", "Convert")
        self.layoutChanged.emit()
        self._persist()

    @Slot()
    def openSettings(self) -> None:
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
        self._active_group = group_index
        self._groups[group_index]["active"] = tab_id
        self.layoutChanged.emit()
        self.selectionChanged.emit()
        self._persist()

    @Slot(int)
    def setActiveGroup(self, group_index: int) -> None:
        if not 0 <= group_index < len(self._groups) or group_index == self._active_group:
            return
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
        old_index = tabs.index(tab_id)
        tabs.remove(tab_id)
        if group["active"] == tab_id:
            group["active"] = tabs[min(old_index, len(tabs) - 1)] if tabs else ""
        if not any(tab_id in item["tabs"] for item in self._groups):
            self._tab_states.pop(tab_id, None)
            self._track_models.pop(tab_id, None)
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
        state = self._tab_state(tab_id)
        state["sortAscending"] = (
            not bool(state.get("sortAscending", True)) if state.get("sortKey") == key else True
        )
        state["sortKey"] = key
        self._revision += 1
        self.layoutChanged.emit()
        self.libraryChanged.emit()
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
        self._tab_state(tab_id)["searchQuery"] = query[:256]
        self._revision += 1
        self.libraryChanged.emit()
        self._refresh_timer.start()
        self._persist()

    @Slot(bool)
    def setRightPanelVisible(self, visible: bool) -> None:
        self._right_visible = bool(visible)
        self.layoutChanged.emit()
        self._persist()

    @Slot(str)
    def showRightPanel(self, tab: str) -> None:
        self._right_tab = "queue" if tab == "queue" else "info"
        self._right_visible = True
        self.layoutChanged.emit()
        self._persist()

    @Slot(str)
    def toggleRightPanel(self, tab: str) -> None:
        if self._right_visible and self._right_tab == tab:
            self._right_visible = False
        else:
            self._right_visible = True
            self._right_tab = "queue" if tab == "queue" else "info"
        self.layoutChanged.emit()
        self._persist()

    @Slot(bool)
    def setFullscreen(self, enabled: bool) -> None:
        self._fullscreen = bool(enabled)
        self.layoutChanged.emit()

    @Slot(bool)
    def setIslandEnabled(self, enabled: bool) -> None:
        self._island_enabled = bool(enabled)
        self.layoutChanged.emit()

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
    def playTrack(self, track_id: str, source: str) -> None:
        track = self.track(track_id)
        folder = _parse_folder_id(source)
        if folder is not None:
            root_id, relative = folder
        elif track:
            root_id, relative = str(track.get("rootId", "")), _folder_from_track(track)
        else:
            root_id, relative = "", ""
        model = self._track_models.get(f"folder:{root_id}/{relative}")
        if model:
            order = model.track_ids_snapshot()
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
            order = [
                str(row["id"])
                for row in _sort_rows(
                    folder_rows,
                    str(state.get("sortKey", "index")),
                    bool(state.get("sortAscending", True)),
                )
            ]
        else:
            order = [track_id]
        self.activationRequested.emit(track_id, order)
        if self._player is not None:
            if track_id not in order:
                order.append(track_id)
            title = self._playback_source_title(source, track)
            self._player.playQueue(order, order.index(track_id), source, title)
        else:
            self._set_message("The audio runtime is unavailable.")

    def _playback_source_title(self, source: str, track: dict[str, Any]) -> str:
        folder = _parse_folder_id(source)
        if folder is not None:
            root_id, relative = folder
            if relative:
                return Path(relative).name
            root = next((row for row in self._library.roots() if row["id"] == root_id), {})
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
        self.openConvert()

    @Slot()
    def retryConversion(self) -> None:
        self._set_message("Conversion becomes available in a later step.")

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
                    root = next(item for item in self._library.roots() if item["id"] == root_id)
                    title = relative.rsplit("/", 1)[-1] if relative else str(root["name"])
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

    def _refresh_library(self) -> None:
        self._folder_model.refresh(self._expanded)
        self.explorerChanged.emit()
        self._revision += 1
        self.libraryChanged.emit()
        self._refresh_timer.start()

    def _refresh_models(self) -> None:
        self._folder_model.refresh(self._expanded)
        for tab_id, model in list(self._track_models.items()):
            state = self._tab_state(tab_id)
            if state.get("kind") != "folder":
                model.replace([])
                continue
            try:
                root_id, relative = _parse_folder_ref(str(state.get("ref", "")))
                rows = self._library.tracks_in_folder(root_id, relative)
                query = str(state.get("searchQuery", "")).casefold().strip()
                if query:
                    rows = [
                        row
                        for row in rows
                        if query
                        in " ".join(
                            str(row.get(key, ""))
                            for key in ("title", "artist", "album", "genre", "filename")
                        ).casefold()
                    ]
                model.replace(
                    _sort_rows(
                        rows,
                        str(state.get("sortKey", "index")),
                        bool(state.get("sortAscending", True)),
                    )
                )
            except ValueError:
                model.replace([])
        self.explorerChanged.emit()
        self.libraryChanged.emit()

    def _on_scan_batch(self, root_id: str, request_id: str, count: int) -> None:
        if self._requests.get(root_id) != request_id:
            return
        self._scan_counts[root_id] = self._scan_counts.get(root_id, 0) + count
        self._set_message(f"Indexed {self._scan_counts[root_id]:,} audio files…")
        self._revision += 1
        self.libraryChanged.emit()
        self._refresh_timer.start()

    def _on_scan_finished(self, root_id: str, request_id: str, result: dict[str, Any]) -> None:
        if self._requests.get(root_id) != request_id:
            return
        self._requests.pop(root_id, None)
        self._jobs_by_root.pop(root_id, None)
        self._refresh_timer.stop()
        self._refresh_models()
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
        else:
            self._set_message(
                f"Folder indexing complete: {self._scan_counts.get(root_id, 0):,} audio files."
            )
        self._persist()

    def _on_job_updated(self, _status: object) -> None:
        self.libraryChanged.emit()

    def _on_metadata_changed(self) -> None:
        self._revision += 1
        self.metadataChanged.emit()
        self.libraryChanged.emit()
        if self._player is not None and self._player.playing_id_value():
            self._player.refreshTrack(self._player.playing_id_value())
        self._refresh_timer.start()

    def _set_message(self, message: str) -> None:
        if self._message == message:
            return
        self._message = message
        self.messageChanged.emit()

    def _persist(self) -> None:
        state = {
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
        }
        try:
            self._session.save(state)
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
            self._set_message(f"Could not save this workspace: {error}")


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
    field = "seconds" if key == "duration" else key
    present = []
    missing = []
    for row in rows:
        value = row.get(field)
        if value is None or value == "":
            missing.append(row)
            continue
        try:
            sort_value: object = (
                float(value) if field in {"bpm", "seconds", "bitrate"} else str(value).casefold()
            )
        except (TypeError, ValueError):
            sort_value = str(value).casefold()
        present.append((sort_value, str(row["id"]), row))
    present.sort(key=lambda item: (item[0], item[1]), reverse=not ascending)
    return [item[2] for item in present] + sorted(missing, key=lambda row: str(row["id"]))


def _folder_from_track(track: dict[str, Any]) -> str:
    return str(track.get("relativePath", "")).rpartition("/")[0]
