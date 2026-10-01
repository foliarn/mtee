"""Qt bridge for the deterministic UX prototype.

Actions in this object only change memory. The prototype intentionally has no
path access, metadata writer, player or converter behind its controls: playing
moves a fictitious position, saving changes a copy of invented tags.
"""

from __future__ import annotations

import random

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.demo.library import (
    CONVERT_BATCHES,
    FOLDERS,
    PLAYLISTS,
    TRACKS,
    DemoTrack,
)
from mtee.demo.scenarios import DEFAULT_SCENARIO, SCENARIO_NAMES, DemoScenario, load_scenario

__all__ = ["ACTIVITIES", "EDITABLE_FIELDS", "DemoWorkspace", "format_duration"]

ACTIVITIES = ("explorer", "playlists", "convert", "tasks", "plugins", "profile")
TAB_KINDS = ("folder", "playlist", "convert", "settings")
SORT_KEYS = ("index", "title", "album", "genre", "bpm", "key", "duration")
REPEAT_MODES = ("off", "all", "one")
MAX_GROUPS = 2

EDITABLE_FIELDS = (
    ("title", "Title"),
    ("artist", "Artist"),
    ("album", "Album"),
    ("genre", "Genre"),
    ("year", "Date"),
    ("trackNumber", "Track number"),
    ("bpm", "BPM"),
    ("key", "Key"),
    ("comment", "Comment"),
)
_READ_ONLY_FIELDS = (
    ("duration", "Duration"),
    ("format", "Format"),
    ("bitrate", "Bitrate"),
    ("sampleRate", "Sample rate"),
    ("size", "Size"),
    ("filename", "Filename"),
    ("path", "Path"),
)
_INITIAL_HISTORY = ("tec02", "ukg03", "dnb01")
_INITIAL_EXPANDED = ("music", "ukg")


def format_duration(seconds: int) -> str:
    """Return ``m:ss``, or ``h:mm:ss`` from one hour."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_total(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


def _format_size(megabytes: float) -> str:
    if megabytes >= 1000:
        return f"{megabytes / 1000:.1f} GB"
    return f"{megabytes:.0f} MB" if megabytes >= 10 else f"{megabytes:.1f} MB"


def _track_to_dict(track: DemoTrack) -> dict[str, object]:
    folder = next(f.name for f in FOLDERS if f.folder_id == track.folder)
    return {
        "id": track.track_id,
        "folder": track.folder,
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "genre": track.genre,
        "bpm": track.bpm,
        "key": track.key,
        "seconds": track.seconds,
        "duration": format_duration(track.seconds),
        "format": track.audio_format,
        "bitrate": track.bitrate,
        "sampleRate": track.sample_rate,
        "sizeMb": track.size_mb,
        "size": _format_size(track.size_mb),
        "filename": track.filename,
        "path": f"Music/{folder}/{track.filename}",
        "dateAdded": track.date_added,
        "cover": track.cover,
        "year": track.year,
        "trackNumber": track.track_number,
        "comment": track.comment,
    }


class DemoWorkspace(QObject):
    """State and actions exposed to QML for one demo session."""

    scenarioChanged = Signal()
    layoutChanged = Signal()
    explorerChanged = Signal()
    libraryChanged = Signal()
    selectionChanged = Signal()
    playbackChanged = Signal()
    positionChanged = Signal()
    saveStateChanged = Signal()
    conversionChanged = Signal()

    def __init__(self, scenario: str = DEFAULT_SCENARIO, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._analysis_settings: QObject | None = None
        self._tag_conflicts: QObject | None = None
        self._tracks: dict[str, dict[str, object]] = {}
        self._order: list[str] = []
        self._playlists: dict[str, dict[str, object]] = {}
        self._apply(load_scenario(scenario))

    # ----------------------------------------------------------------- state

    def _apply(self, scenario: DemoScenario) -> None:
        self._scenario = scenario
        self._tracks = {track.track_id: _track_to_dict(track) for track in TRACKS}
        self._order = [track.track_id for track in TRACKS]
        self._playlists = {
            p.playlist_id: {"id": p.playlist_id, "name": p.name, "tracks": list(p.track_ids)}
            for p in PLAYLISTS
        }
        self._revision = 0
        self._activity = scenario.activity
        self._sidebar_visible = scenario.sidebar_visible
        self._tab_state: dict[str, dict[str, object]] = {}
        self._groups: list[dict[str, object]] = []
        for tabs, active in zip(scenario.groups, scenario.active_tabs, strict=True):
            self._groups.append({"tabs": list(tabs), "active": active})
            for tab_id in tabs:
                self._ensure_tab(tab_id)
        for tab_id in scenario.artwork_tabs:
            self._ensure_tab(tab_id)["view"] = "artwork"
        self._active_group = 0
        self._right_panel = scenario.right_panel
        self._right_panel_visible = bool(scenario.right_panel)
        self._fullscreen = scenario.fullscreen
        self._island_enabled = scenario.island_enabled
        self._expanded: set[str] = set(_INITIAL_EXPANDED)
        self._selected = list(scenario.selected)
        self._anchor = self._selected[-1] if self._selected else ""
        self._playing = scenario.playing
        self._is_playing = scenario.is_playing
        self._position = float(scenario.position)
        self._volume = 72
        self._muted = False
        self._shuffle = False
        self._repeat = scenario.repeat
        self._source = scenario.playing_source
        self._queue_original = self._source_ids(scenario.playing_source)
        self._queue = list(self._queue_original)
        self._history: list[str] = list(_INITIAL_HISTORY)
        if scenario.shuffle:
            self._set_shuffle(True)
        self._save_state = "idle"
        self._save_fails = scenario.save_fails
        self._pending: dict[str, object] | None = None
        self._last_saved: dict[str, object] | None = None
        self._conversion_error = scenario.conversion_error
        self._convert_inputs = ["dnb01", "dnb02"]
        self._next_playlist = 1

    def _ensure_tab(self, tab_id: str) -> dict[str, object]:
        kind = tab_id.partition(":")[0]
        if kind not in TAB_KINDS:
            raise ValueError(f"Unsupported tab: {tab_id}")
        if tab_id not in self._tab_state:
            self._tab_state[tab_id] = {"view": "list", "sortKey": "index", "sortAscending": True}
        return self._tab_state[tab_id]

    def _tab_title(self, tab_id: str) -> str:
        kind, _, ref = tab_id.partition(":")
        if kind == "folder":
            return next((f.name for f in FOLDERS if f.folder_id == ref), ref)
        if kind == "playlist":
            playlist = self._playlists.get(ref)
            return str(playlist["name"]) if playlist else ref
        return "Convert" if kind == "convert" else "Settings"

    def _visible_order(self, source: str) -> list[str]:
        """Order of ``source`` as its tab currently shows it."""
        kind, _, ref = source.partition(":")
        state = self._tab_state.get(source)
        if state is None:
            return self._source_ids(source)
        rows = self.tabTracks(kind, ref, str(state["sortKey"]), bool(state["sortAscending"]))
        return [str(row["id"]) for row in rows]

    def _source_ids(self, source: str) -> list[str]:
        kind, _, ref = source.partition(":")
        if kind == "folder":
            return [tid for tid in self._order if self._tracks[tid]["folder"] == ref]
        if kind == "playlist" and ref in self._playlists:
            return list(self._playlists[ref]["tracks"])  # type: ignore[arg-type]
        return []

    # ------------------------------------------------------------ properties

    @Property(str, notify=scenarioChanged)
    def scenarioName(self) -> str:
        return self._scenario.name

    @Property(int, notify=libraryChanged)
    def revision(self) -> int:
        """Changes whenever tags or playlists change, to refresh function bindings."""
        return self._revision

    @Property(str, notify=layoutChanged)
    def activity(self) -> str:
        return self._activity

    @Property(bool, notify=layoutChanged)
    def sidebarVisible(self) -> bool:
        return self._sidebar_visible

    @Property(list, notify=layoutChanged)
    def groups(self) -> list[dict[str, object]]:
        result = []
        for group in self._groups:
            tabs = []
            for tab_id in group["tabs"]:  # type: ignore[union-attr]
                kind, _, ref = str(tab_id).partition(":")
                tabs.append(
                    {
                        "id": tab_id,
                        "kind": kind,
                        "ref": ref,
                        "title": self._tab_title(str(tab_id)),
                        **self._tab_state[str(tab_id)],
                    }
                )
            result.append({"tabs": tabs, "active": group["active"]})
        return result

    @Property(int, notify=layoutChanged)
    def activeGroup(self) -> int:
        return self._active_group

    @Property(str, notify=layoutChanged)
    def activeFolder(self) -> str:
        """Folder shown by the active tab, highlighted in the explorer tree."""
        active = str(self._groups[self._active_group]["active"]) if self._groups else ""
        kind, _, ref = active.partition(":")
        return ref if kind == "folder" else ""

    @Property(bool, notify=layoutChanged)
    def rightPanelVisible(self) -> bool:
        return self._right_panel_visible

    @Property(str, notify=layoutChanged)
    def rightPanelTab(self) -> str:
        return self._right_panel or "info"

    @Property(bool, notify=layoutChanged)
    def fullscreen(self) -> bool:
        return self._fullscreen

    @Property(bool, notify=layoutChanged)
    def islandEnabled(self) -> bool:
        return self._island_enabled

    @Property(QObject, constant=True)
    def playerModel(self) -> QObject:
        """Let shared player views bind to the same in-memory demo bridge."""
        return self

    @Property(QObject, constant=True)
    def waveformModel(self) -> QObject:
        return self

    @Property(str, notify=playbackChanged)
    def state(self) -> str:
        return "ready" if self._playing else "idle"

    @Property(float, notify=playbackChanged)
    def progress(self) -> float:
        return 1.0

    @Property(str, notify=playbackChanged)
    def error(self) -> str:
        return ""

    @Property(int, notify=playbackChanged)
    def durationUs(self) -> int:
        return (
            round(float(str(self._tracks[self._playing]["seconds"])) * 1_000_000)
            if self._playing
            else 0
        )

    @Property(list, notify=playbackChanged)
    def samples(self) -> list[list[float]]:
        return []

    @Slot()
    def retry(self) -> None:
        return

    @Slot(float)
    def seekRatio(self, ratio: float) -> None:
        seconds = float(str(self._tracks[self._playing]["seconds"])) if self._playing else 0.0
        self.seek(max(0.0, min(1.0, ratio)) * seconds)

    @Property(bool, constant=True)
    def hasQueueModel(self) -> bool:
        return False

    @Property(list, notify=explorerChanged)
    def explorerRows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []

        def visit(folder_id: str, depth: int) -> None:
            folder = next(f for f in FOLDERS if f.folder_id == folder_id)
            children = [f for f in FOLDERS if f.parent == folder_id]
            tracks = [tid for tid in self._order if self._tracks[tid]["folder"] == folder_id]
            expanded = folder_id in self._expanded
            rows.append(
                {
                    "kind": "folder",
                    "id": folder_id,
                    "name": folder.name,
                    "depth": depth,
                    "expanded": expanded,
                    "hasChildren": bool(children or tracks),
                }
            )
            if not expanded:
                return
            for child in children:
                visit(child.folder_id, depth + 1)
            for tid in tracks:
                rows.append(
                    {
                        "kind": "track",
                        "id": tid,
                        "name": self._tracks[tid]["title"],
                        "depth": depth + 1,
                        "expanded": False,
                        "hasChildren": False,
                    }
                )

        visit("music", 0)
        return rows

    @Property(list, notify=libraryChanged)
    def playlists(self) -> list[dict[str, object]]:
        result = []
        for playlist in self._playlists.values():
            ids = list(playlist["tracks"])  # type: ignore[call-overload]
            seconds = sum(int(self._tracks[tid]["seconds"]) for tid in ids)  # type: ignore[call-overload]
            result.append(
                {
                    "id": playlist["id"],
                    "name": playlist["name"],
                    "count": len(ids),
                    "summary": f"{len(ids)} titles · {_format_total(seconds)}",
                    "cover": self._tracks[ids[0]]["cover"] if ids else -1,
                }
            )
        return result

    @Property(list, notify=selectionChanged)
    def selectedIds(self) -> list[str]:
        return list(self._selected)

    @Property(str, notify=playbackChanged)
    def playingId(self) -> str:
        return self._playing

    @Property(dict, notify=playbackChanged)
    def playingTrack(self) -> dict[str, object]:
        return dict(self._tracks[self._playing]) if self._playing in self._tracks else {}

    @Property(str, notify=playbackChanged)
    def playingSourceTitle(self) -> str:
        return self._tab_title(self._source) if self._source else ""

    @Property(str, notify=playbackChanged)
    def playingSource(self) -> str:
        """Tab the queue was captured from, written ``kind:ref``."""
        return self._source

    @Property(str, notify=playbackChanged)
    def playingSourceKind(self) -> str:
        return self._source.partition(":")[0]

    @Property(bool, notify=playbackChanged)
    def isPlaying(self) -> bool:
        return self._is_playing

    @Property(str, notify=playbackChanged)
    def status(self) -> str:
        if not self._playing:
            return "Idle"
        return "Playing" if self._is_playing else "Paused"

    @Property(float, notify=positionChanged)
    def position(self) -> float:
        return self._position

    @Property(float, notify=playbackChanged)
    def duration(self) -> float:
        return float(self._tracks[self._playing]["seconds"]) if self._playing else 0.0  # type: ignore[arg-type]

    @Property(bool, notify=playbackChanged)
    def seekable(self) -> bool:
        return bool(self._playing)

    @Property(str, notify=playbackChanged)
    def errorMessage(self) -> str:
        return ""

    @Property(int, notify=playbackChanged)
    def volume(self) -> int:
        return self._volume

    @Property(bool, notify=playbackChanged)
    def muted(self) -> bool:
        return self._muted

    @Property(bool, notify=playbackChanged)
    def shuffle(self) -> bool:
        return self._shuffle

    @Property(str, notify=playbackChanged)
    def repeat(self) -> str:
        return self._repeat

    @Property(list, notify=playbackChanged)
    def upNext(self) -> list[dict[str, object]]:
        if self._playing not in self._queue:
            return [dict(self._tracks[tid]) for tid in self._queue if tid in self._tracks]
        index = self._queue.index(self._playing)
        return [dict(self._tracks[tid]) for tid in self._queue[index + 1 :]]

    @Property(list, notify=playbackChanged)
    def history(self) -> list[dict[str, object]]:
        return [dict(self._tracks[tid]) for tid in self._history if tid in self._tracks]

    @Property(str, notify=saveStateChanged)
    def saveState(self) -> str:
        return self._save_state

    @Property(bool, notify=conversionChanged)
    def conversionError(self) -> bool:
        return self._conversion_error

    @Property(list, notify=conversionChanged)
    def convertInputs(self) -> list[dict[str, object]]:
        return [
            {
                **self._tracks[tid],
                "status": "failed" if self._conversion_error and index == 1 else "ready",
                "destination": "",
                "summary": "The demo does not write audio files.",
            }
            for index, tid in enumerate(self._convert_inputs)
        ]

    @Property(QObject, constant=True)
    def conversionModel(self) -> QObject:
        return self

    @Property(QObject, constant=True)
    def analysisSettings(self) -> QObject:
        return self._analysis_settings if self._analysis_settings is not None else self

    @Property(QObject, constant=True)
    def tagConflicts(self) -> QObject:
        return self._tag_conflicts if self._tag_conflicts is not None else self

    def attach_analysis_settings(self, settings: QObject, conflicts: QObject | None = None) -> None:
        """Show the real Analysis settings tab; the demo never analyzes audio."""
        self._analysis_settings = settings
        self._tag_conflicts = conflicts

    @Slot(list, bool)
    def analyzeTracks(self, track_ids: list, force: bool) -> None:
        """The demo library has no audio files, so there is nothing to analyze."""

    @Slot(str, bool)
    def analyzeFolder(self, folder_id: str, force: bool) -> None:
        """The demo library has no audio files, so there is nothing to analyze."""

    @Property(list, constant=True)
    def formats(self) -> list[dict[str, str]]:
        return [
            {"id": "mp3", "name": "MP3", "quality": "320 kbps · CBR"},
            {"id": "aiff", "name": "AIFF", "quality": "16-bit PCM"},
            {"id": "flac", "name": "FLAC", "quality": "Level 5 · lossless"},
            {"id": "wav", "name": "WAV", "quality": "16-bit PCM"},
        ]

    @Property(int, notify=conversionChanged)
    def formatIndex(self) -> int:
        return 0

    @Property(str, constant=True)
    def outputFolder(self) -> str:
        return "Music/Converted"

    @Property(list, constant=True)
    def sampleRateOptions(self) -> list[str]:
        return ["Keep source", "44.1 kHz", "48 kHz"]

    @Property(str, constant=True)
    def sampleRate(self) -> str:
        return "Keep source"

    @Property(list, constant=True)
    def channelOptions(self) -> list[str]:
        return ["Keep source", "Mono", "Stereo"]

    @Property(str, constant=True)
    def channels(self) -> str:
        return "Keep source"

    @Property(list, constant=True)
    def bitDepthOptions(self) -> list[str]:
        return ["Keep source", "16-bit", "24-bit"]

    @Property(str, constant=True)
    def bitDepth(self) -> str:
        return "Keep source"

    @Property(bool, constant=True)
    def dither(self) -> bool:
        return False

    @Property(bool, constant=True)
    def copyMetadata(self) -> bool:
        return True

    @Property(bool, constant=True)
    def hasPreview(self) -> bool:
        return False

    @Property(bool, constant=True)
    def previewExecutable(self) -> bool:
        return False

    @Property(str, notify=conversionChanged)
    def previewSummary(self) -> str:
        return (
            "This review scenario uses invented files; real conversion runs in the local library."
        )

    @Property(list, constant=True)
    def convertBatches(self) -> list[dict[str, object]]:
        return [dict(batch) for batch in CONVERT_BATCHES]

    @Property(list, notify=selectionChanged)
    def infoFields(self) -> list[dict[str, object]]:
        """Editable tags of the selection; differing values are ``mixed``."""
        tracks = [self._tracks[tid] for tid in self._selected if tid in self._tracks]
        pending = self._pending if self._save_state == "error" else None
        fields = []
        for key, label in EDITABLE_FIELDS:
            values = {str(track[key]) for track in tracks}
            mixed = len(values) > 1
            value = "" if mixed or not values else values.pop()
            if pending and pending["field"] == key:
                value, mixed = str(pending["value"]), False
            fields.append({"key": key, "label": label, "value": value, "mixed": mixed})
        return fields

    @Property(list, notify=selectionChanged)
    def infoFile(self) -> list[dict[str, object]]:
        """Read-only technical details, shown for a single selected track."""
        if len(self._selected) != 1 or self._selected[0] not in self._tracks:
            return []
        track = self._tracks[self._selected[0]]
        return [{"label": label, "value": str(track[key])} for key, label in _READ_ONLY_FIELDS]

    # ---------------------------------------------------------- query slots

    @Slot(str, result=dict)
    def track(self, track_id: str) -> dict[str, object]:
        return dict(self._tracks.get(track_id, {}))

    @Slot(str, str, str, bool, int, result=list)
    def tabTracks(
        self, kind: str, ref: str, sort_key: str, ascending: bool, _revision: int = 0
    ) -> list[dict[str, object]]:
        """Tracks of a folder or playlist tab, numbered then sorted."""
        ids = self._source_ids(f"{kind}:{ref}")
        rows = []
        for number, tid in enumerate(ids, start=1):
            row = dict(self._tracks[tid])
            row["number"] = number
            rows.append(row)
        if sort_key not in ("index", ""):
            field = "seconds" if sort_key == "duration" else sort_key

            def value(row: dict[str, object]) -> tuple[int, object]:
                raw = row[field]
                if field in ("bpm", "seconds"):
                    try:
                        return (0, float(str(raw)))
                    except ValueError:
                        return (1, 0.0)
                if field == "key":
                    text = str(raw)
                    try:
                        return (0, (int(text[:-1]), text[-1]))
                    except ValueError:
                        return (1, (0, ""))
                text = str(raw).casefold()
                return (0 if text else 1, text)

            rows.sort(key=value, reverse=not ascending)
        return rows

    @Slot(str, str, int, result=str)
    def tabSummary(self, kind: str, ref: str, _revision: int = 0) -> str:
        ids = self._source_ids(f"{kind}:{ref}")
        seconds = sum(int(self._tracks[tid]["seconds"]) for tid in ids)  # type: ignore[call-overload]
        size = sum(float(self._tracks[tid]["sizeMb"]) for tid in ids)  # type: ignore[arg-type]
        return f"{len(ids)} titles · {_format_total(seconds)} · {_format_size(size)}"

    @Slot(str, int, result=list)
    def playlistsContaining(self, track_id: str, _revision: int = 0) -> list[str]:
        return [pid for pid, p in self._playlists.items() if track_id in p["tracks"]]  # type: ignore[operator]

    @staticmethod
    def scenarioNames() -> list[str]:
        """Return all names for command-line and test discovery."""
        return list(SCENARIO_NAMES)

    # ------------------------------------------------------- layout actions

    @Slot(str)
    def loadScenario(self, name: str) -> None:
        """Replace all in-memory state with a deterministic scenario."""
        self._apply(load_scenario(name))
        for signal in (
            self.scenarioChanged,
            self.layoutChanged,
            self.explorerChanged,
            self.libraryChanged,
            self.selectionChanged,
            self.playbackChanged,
            self.positionChanged,
            self.saveStateChanged,
            self.conversionChanged,
        ):
            signal.emit()

    @Slot(str)
    def setActivity(self, activity: str) -> None:
        """Show an activity in the sidebar; the active one toggles the sidebar."""
        if activity not in ACTIVITIES:
            raise ValueError(f"Unsupported activity: {activity}")
        if activity == self._activity and self._sidebar_visible and not self._fullscreen:
            self._sidebar_visible = False
        else:
            self._activity = activity
            self._sidebar_visible = True
            self._fullscreen = False
        if activity == "convert" and self._sidebar_visible:
            self._open_tab("convert:")
        self.layoutChanged.emit()

    @Slot(bool)
    def setSidebarVisible(self, visible: bool) -> None:
        if bool(visible) != self._sidebar_visible:
            self._sidebar_visible = bool(visible)
            self.layoutChanged.emit()

    @Slot()
    def toggleSidebar(self) -> None:
        self._sidebar_visible = not self._sidebar_visible
        self.layoutChanged.emit()

    def _open_tab(self, tab_id: str, group: int = -1) -> None:
        self._ensure_tab(tab_id)
        index = self._active_group if group < 0 else group
        if not self._groups:
            self._groups.append({"tabs": [], "active": ""})
            index = 0
        target = self._groups[index]
        tabs = target["tabs"]
        assert isinstance(tabs, list)
        if tab_id not in tabs:
            tabs.append(tab_id)
        target["active"] = tab_id
        self._active_group = index
        self._fullscreen = False

    @Slot(str)
    def openFolder(self, folder_id: str) -> None:
        self._open_tab(f"folder:{folder_id}")
        self.layoutChanged.emit()

    @Slot(str)
    def openPlaylist(self, playlist_id: str) -> None:
        self._open_tab(f"playlist:{playlist_id}")
        self.layoutChanged.emit()

    @Slot()
    def openConvert(self) -> None:
        self._open_tab("convert:")
        self.layoutChanged.emit()

    @Slot()
    def openSettings(self) -> None:
        self._open_tab("settings:")
        self.layoutChanged.emit()

    @Slot(int, str)
    def activateTab(self, group: int, tab_id: str) -> None:
        if 0 <= group < len(self._groups):
            self._groups[group]["active"] = tab_id
            self._active_group = group
            self.layoutChanged.emit()

    @Slot(int)
    def setActiveGroup(self, group: int) -> None:
        if 0 <= group < len(self._groups) and group != self._active_group:
            self._active_group = group
            self.layoutChanged.emit()

    @Slot(int, str)
    def closeTab(self, group: int, tab_id: str) -> None:
        if not 0 <= group < len(self._groups):
            return
        target = self._groups[group]
        tabs = target["tabs"]
        assert isinstance(tabs, list)
        if tab_id not in tabs:
            return
        index = tabs.index(tab_id)
        tabs.remove(tab_id)
        if target["active"] == tab_id:
            target["active"] = tabs[min(index, len(tabs) - 1)] if tabs else ""
        if not tabs and len(self._groups) > 1:
            self._groups.pop(group)
        self._active_group = min(self._active_group, len(self._groups) - 1)
        self.layoutChanged.emit()

    @Slot()
    def toggleSplit(self) -> None:
        """Split the editor into two groups, or join them again."""
        if len(self._groups) >= MAX_GROUPS:
            second = self._groups.pop()
            first_tabs = self._groups[0]["tabs"]
            assert isinstance(first_tabs, list)
            for tab_id in second["tabs"]:  # type: ignore[union-attr]
                if tab_id not in first_tabs:
                    first_tabs.append(tab_id)
            self._active_group = 0
        elif self._groups:
            active = str(self._groups[self._active_group]["active"])
            self._groups.append({"tabs": [active] if active else [], "active": active})
            self._active_group = len(self._groups) - 1
        self.layoutChanged.emit()

    @Slot(str, str)
    def setSort(self, tab_id: str, key: str) -> None:
        if key not in SORT_KEYS:
            raise ValueError(f"Unsupported sort key: {key}")
        state = self._ensure_tab(tab_id)
        if state["sortKey"] == key and key != "index":
            if state["sortAscending"]:
                state["sortAscending"] = False
            else:
                state["sortKey"], state["sortAscending"] = "index", True
        else:
            state["sortKey"], state["sortAscending"] = key, True
        self.layoutChanged.emit()

    @Slot(str, str)
    def setTabView(self, tab_id: str, view: str) -> None:
        if view not in ("list", "artwork"):
            raise ValueError(f"Unsupported view: {view}")
        self._ensure_tab(tab_id)["view"] = view
        self.layoutChanged.emit()

    @Slot(bool)
    def setRightPanelVisible(self, visible: bool) -> None:
        if bool(visible) != self._right_panel_visible:
            self._right_panel_visible = bool(visible)
            self.layoutChanged.emit()

    @Slot(str)
    def showRightPanel(self, tab: str) -> None:
        """Open the right panel on ``info`` or ``queue``."""
        if tab not in ("info", "queue"):
            raise ValueError(f"Unsupported panel tab: {tab}")
        self._right_panel = tab
        self._right_panel_visible = True
        self.layoutChanged.emit()

    @Slot(str)
    def toggleRightPanel(self, tab: str) -> None:
        """Open on ``tab``, or close when that tab is already shown."""
        if self._right_panel_visible and self.rightPanelTab == tab:
            self.setRightPanelVisible(False)
        else:
            self.showRightPanel(tab)

    @Slot(bool)
    def setFullscreen(self, enabled: bool) -> None:
        if bool(enabled) != self._fullscreen and (self._playing or not enabled):
            self._fullscreen = bool(enabled)
            self.layoutChanged.emit()

    @Slot(bool)
    def setIslandEnabled(self, enabled: bool) -> None:
        if bool(enabled) != self._island_enabled:
            self._island_enabled = bool(enabled)
            self.layoutChanged.emit()

    @Slot(str)
    def toggleFolder(self, folder_id: str) -> None:
        if folder_id in self._expanded:
            self._expanded.discard(folder_id)
        else:
            self._expanded.add(folder_id)
        self.explorerChanged.emit()

    # ---------------------------------------------------- selection actions

    @Slot(str, str, list)
    def selectTrack(self, track_id: str, mode: str = "single", ordered: list | None = None) -> None:
        """Select a track: ``single``, ``toggle`` (Ctrl) or ``range`` (Shift)."""
        if track_id not in self._tracks:
            return
        if mode == "toggle":
            if track_id in self._selected:
                self._selected.remove(track_id)
            else:
                self._selected.append(track_id)
            self._anchor = track_id
        elif mode == "range" and ordered and self._anchor in ordered and track_id in ordered:
            start, end = sorted((ordered.index(self._anchor), ordered.index(track_id)))
            self._selected = [str(tid) for tid in ordered[start : end + 1]]
        else:
            self._selected = [track_id]
            self._anchor = track_id
        self._reset_save_state()
        self.selectionChanged.emit()

    @Slot(list)
    def selectAll(self, ordered: list) -> None:
        self._selected = [str(tid) for tid in ordered if str(tid) in self._tracks]
        self._reset_save_state()
        self.selectionChanged.emit()

    def _reset_save_state(self) -> None:
        if self._save_state != "saving":
            self._pending = None
            self._last_saved = None
            if self._save_state != "idle":
                self._save_state = "idle"
                self.saveStateChanged.emit()

    # ----------------------------------------------------- playback actions

    @Slot(str, str)
    def playTrack(self, track_id: str, source: str) -> None:
        """Play ``track_id`` with the order of ``source`` captured as the queue."""
        if track_id not in self._tracks:
            return
        self._push_history()
        self._source = source
        self._queue_original = self._visible_order(source) or [track_id]
        self._queue = list(self._queue_original)
        if self._shuffle:
            self._set_shuffle(True, current=track_id)
        self._playing = track_id
        self._is_playing = True
        self._position = 0.0
        self.playbackChanged.emit()
        self.positionChanged.emit()

    @Slot(list, str, list)
    def enqueueTracks(self, identities: list, source: str, rows: list) -> None:
        del source, rows
        additions = [str(identity) for identity in identities if str(identity) in self._tracks]
        if not additions:
            return
        position = self._queue.index(self._playing) + 1 if self._playing in self._queue else 0
        self._queue[position:position] = additions
        self.playbackChanged.emit()

    @Slot(str)
    def enqueuePlaylist(self, identity: str) -> None:
        playlist = self._playlists.get(identity)
        if playlist is not None and isinstance(playlist.get("tracks"), list):
            self.enqueueTracks(playlist["tracks"], "playlist:" + identity, [])

    def _push_history(self) -> None:
        if self._playing:
            if self._playing in self._history:
                self._history.remove(self._playing)
            self._history.insert(0, self._playing)
            del self._history[8:]

    @Slot()
    def togglePlay(self) -> None:
        if not self._playing and self._queue:
            self._playing = self._queue[0]
            self._is_playing = True
            self.playbackChanged.emit()
            return
        if self._playing:
            self._is_playing = not self._is_playing
            self.playbackChanged.emit()

    @Slot()
    def next(self) -> None:
        if self._playing not in self._queue:
            return
        index = self._queue.index(self._playing)
        if index + 1 < len(self._queue):
            target = self._queue[index + 1]
        elif self._repeat == "all":
            target = self._queue[0]
        else:
            self._is_playing = False
            self._position = 0.0
            self.playbackChanged.emit()
            self.positionChanged.emit()
            return
        self._push_history()
        self._playing = target
        self._position = 0.0
        self.playbackChanged.emit()
        self.positionChanged.emit()

    @Slot()
    def previous(self) -> None:
        if self._position > 3 or self._playing not in self._queue:
            self.seek(0)
            return
        index = self._queue.index(self._playing)
        if index > 0:
            self._playing = self._queue[index - 1]
            self._position = 0.0
            self.playbackChanged.emit()
            self.positionChanged.emit()
        else:
            self.seek(0)

    @Slot(float)
    def seek(self, seconds: float) -> None:
        duration = float(self._tracks[self._playing]["seconds"]) if self._playing else 0.0  # type: ignore[arg-type]
        self._position = max(0.0, min(float(seconds), duration))
        self.positionChanged.emit()

    @Slot(float)
    def tick(self, seconds: float) -> None:
        """Advance the fictitious position while playing."""
        if not self._is_playing or not self._playing:
            return
        duration = float(self._tracks[self._playing]["seconds"])  # type: ignore[arg-type]
        self._position += seconds
        if self._position >= duration:
            if self._repeat == "one":
                self._position = 0.0
                self.positionChanged.emit()
            else:
                self.next()
            return
        self.positionChanged.emit()

    @Slot(int)
    def setVolume(self, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        if volume != self._volume or self._muted:
            self._volume = volume
            self._muted = False
            self.playbackChanged.emit()

    @Slot()
    def toggleMute(self) -> None:
        self._muted = not self._muted
        self.playbackChanged.emit()

    @Slot()
    def toggleShuffle(self) -> None:
        self._set_shuffle(not self._shuffle)
        self.playbackChanged.emit()

    def _set_shuffle(self, enabled: bool, current: str | None = None) -> None:
        playing = current or self._playing
        self._shuffle = enabled
        if enabled:
            rest = [tid for tid in self._queue_original if tid != playing]
            random.Random(len(rest)).shuffle(rest)
            self._queue = [playing, *rest] if playing else rest
        else:
            self._queue = list(self._queue_original)

    @Slot()
    def cycleRepeat(self) -> None:
        self._repeat = REPEAT_MODES[(REPEAT_MODES.index(self._repeat) + 1) % len(REPEAT_MODES)]
        self.playbackChanged.emit()

    # ------------------------------------------------------- editing actions

    @Slot(str, str)
    def commitField(self, field: str, value: str) -> None:
        """Start the fictitious save of one tag for the whole selection."""
        if field not in dict(EDITABLE_FIELDS) or not self._selected:
            return
        ids = [tid for tid in self._selected if tid in self._tracks]
        previous = {tid: str(self._tracks[tid][field]) for tid in ids}
        if all(old == value for old in previous.values()):
            return
        self._pending = {"field": field, "value": value, "ids": ids, "previous": previous}
        self._save_state = "saving"
        self.saveStateChanged.emit()

    @Slot()
    def finishSave(self) -> None:
        """End the fictitious save started by ``commitField``."""
        if self._save_state != "saving" or self._pending is None:
            return
        if self._save_fails:
            self._save_state = "error"
        else:
            field, value = str(self._pending["field"]), str(self._pending["value"])
            for tid in self._pending["ids"]:  # type: ignore[union-attr]
                self._tracks[str(tid)][field] = value
            self._last_saved, self._pending = self._pending, None
            self._save_state = "saved"
            self._revision += 1
            self.libraryChanged.emit()
        self.saveStateChanged.emit()
        self.selectionChanged.emit()

    @Slot()
    def retrySave(self) -> None:
        """Retry a failed save; the prototype lets the second attempt succeed."""
        if self._save_state == "error" and self._pending is not None:
            self._save_fails = False
            self._save_state = "saving"
            self.saveStateChanged.emit()

    @Slot()
    def undoSave(self) -> None:
        """Restore the values before the last save, or drop a failed edit."""
        if self._save_state == "saved" and self._last_saved is not None:
            field = str(self._last_saved["field"])
            for tid, old in self._last_saved["previous"].items():  # type: ignore[union-attr]
                self._tracks[str(tid)][field] = old
            self._revision += 1
            self.libraryChanged.emit()
        self._pending = None
        self._last_saved = None
        self._save_state = "idle"
        self.saveStateChanged.emit()
        self.selectionChanged.emit()

    @Slot(list, str)
    def togglePlaylist(self, track_ids: list, playlist_id: str) -> None:
        """Add the tracks to a playlist, or remove them when all are already in it."""
        playlist = self._playlists.get(playlist_id)
        if playlist is None:
            return
        members = playlist["tracks"]
        assert isinstance(members, list)
        ids = [str(tid) for tid in track_ids if str(tid) in self._tracks]
        if ids and all(tid in members for tid in ids):
            for tid in ids:
                members.remove(tid)
        else:
            members.extend(tid for tid in ids if tid not in members)
        self._revision += 1
        self.libraryChanged.emit()

    @Slot(list)
    def addToNewPlaylist(self, track_ids: list) -> None:
        playlist_id = f"new{self._next_playlist}"
        name = f"Untitled playlist {len(self._playlists) + 1:02d}"
        self._next_playlist += 1
        ids = [str(tid) for tid in track_ids if str(tid) in self._tracks]
        self._playlists[playlist_id] = {"id": playlist_id, "name": name, "tracks": ids}
        self._revision += 1
        self.libraryChanged.emit()

    @Slot()
    def addSelectionToConvert(self) -> None:
        added = [tid for tid in self._selected if tid not in self._convert_inputs]
        if added:
            self._convert_inputs.extend(added)
            self.conversionChanged.emit()

    @Slot()
    def next_format(self) -> None:
        return

    @Slot(list)
    def add_files(self, _files: list) -> None:
        return

    @Slot()
    def next_quality(self) -> None:
        return

    @Slot()
    def next_sample_rate(self) -> None:
        return

    @Slot()
    def next_channels(self) -> None:
        return

    @Slot()
    def next_bit_depth(self) -> None:
        return

    @Slot()
    def toggle_dither(self) -> None:
        return

    @Slot()
    def toggle_metadata(self) -> None:
        return

    @Slot()
    def set_output_folder(self, _folder: str) -> None:
        return

    @Slot()
    def open_output_folder(self) -> None:
        return

    @Slot()
    def cancel_all(self) -> None:
        return

    @Property(bool, constant=True)
    def canCancel(self) -> bool:
        return False

    @Slot()
    def retry_failed(self) -> None:
        return

    @Slot()
    def preview_or_start(self) -> None:
        return

    @Slot()
    def retryConversion(self) -> None:
        """Clear only the visible conversion error in the prototype."""
        if self._conversion_error:
            self._conversion_error = False
            self.conversionChanged.emit()
