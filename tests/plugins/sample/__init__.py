"""The sample plugin: one of each contribution, built on the plugin interface alone.

The contract tests (``tests/plugins/test_contract.py``) and the UI tests run it, and
``docs/plugins.md`` points to it as the model of a plugin. It records each call of its
functions in ``EVENTS`` so that a test can see what the core ran.
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.plugins.api import (
    Availability,
    CellValue,
    Contribution,
    DeleteChoice,
    DeleteChoices,
    DeleteRequest,
    JobContext,
    LibraryScanned,
    PaneAction,
    PlayableSource,
    PlayLogEvent,
    PluginActivity,
    PluginContext,
    PluginDialog,
    PluginRowsModel,
    PluginService,
    PluginSettings,
    SettingsPage,
    SidebarSection,
    SourceTrack,
    StartupTask,
    StatusItem,
    TabAction,
    TabHeader,
    TabKind,
    TabRequest,
    TrackAction,
    TrackAnalysisData,
    TrackAvailability,
    TrackColumn,
    TrackListRow,
    TrackLoudnessData,
    TrackSource,
    WaitingItems,
)

from .track_source import (
    BROKEN_KEY,
    SOURCE_KEY,
    TOKEN,
    AudioServer,
    tiny_png,
)

EVENTS: list[str] = []
# Each run of a delete choice: (choice id, track ids, thread identifier), see ``_run_delete``.
DELETE_RUNS: list[tuple[str, tuple[str, ...], int]] = []
HERE = Path(__file__).parent
LIST_KIND = "sample.list"


class SettingsBackend(QObject):
    """What the Settings page reads and changes; the values live in the plugin settings."""

    changed = Signal()

    def __init__(self, settings: PluginSettings, item_count: int) -> None:
        super().__init__()
        self._settings = settings
        self._item_count = item_count

    @Property(str, notify=changed)
    def label(self) -> str:
        return self._settings.get("label", "") or ""

    @Slot(str)
    def setLabel(self, value: str) -> None:
        self._settings.set("label", value)
        self.changed.emit()

    @Property(bool, notify=changed)
    def loud(self) -> bool:
        return bool(self._settings.get_json("loud", False))

    @Slot(bool)
    def setLoud(self, value: bool) -> None:
        self._settings.set_json("loud", value)
        self.changed.emit()

    @Property(int, notify=changed)
    def copies(self) -> int:
        stored = self._settings.get_json("copies", 1)
        return stored if isinstance(stored, int) and 1 <= stored <= 5 else 1

    @Slot(int)
    def setCopies(self, value: int) -> None:
        self._settings.set_json("copies", max(1, min(5, value)))
        self.changed.emit()

    @Property(bool, notify=changed)
    def signedIn(self) -> bool:
        return bool(self._settings.get_json("signed_in", False))

    @Slot()
    def toggleSignIn(self) -> None:
        self._settings.set_json("signed_in", not self.signedIn)
        EVENTS.append("sign in" if self.signedIn else "sign out")
        self.changed.emit()

    @Property(int, constant=True)
    def itemCount(self) -> int:
        return self._item_count


class Service:
    """The plugin service: it builds the contributions and releases what it holds."""

    def __init__(self, context: PluginContext) -> None:
        self._context = context
        self._watching = False
        self._lists = PluginRowsModel(
            [
                {"id": "all", "name": "All samples", "icon": "music", "badge": 2},
                {"id": "group", "name": "Groups", "kind": "group"},
                {"id": "missing", "name": "Missing only", "depth": 1},
            ]
        )
        self._waiting = PluginRowsModel(
            [
                {
                    "id": "w1",
                    "title": "Two Step Theory",
                    "subtitle": "Pick a match: 3 candidates. Nothing is imported until you pick.",
                    "action": "Pick…",
                },
                {
                    "id": "w2",
                    "title": "Skank Rhythm",
                    "subtitle": "Pick a match: 2 candidates.",
                },
            ]
        )
        self._foot = PluginRowsModel([{"text": "Sample is connected", "tone": "secondary"}])
        self._backend = SettingsBackend(context.settings, self._count_items())
        self._audio: AudioServer | None = None
        # The status bar item (plan 125.5): shown from the start, clicked to record the click.
        context.status_item.update("Sample: ready")

    def _count_items(self) -> int:
        cursor = self._context.database.connection().execute("SELECT COUNT(*) FROM sample_items")
        return int(cursor.fetchone()[0])

    # -- the functions the core calls
    def _rows(self, ref: str) -> list[TrackListRow]:
        """Return the rows of a list. Runs on a job thread: read only the plugin's own data."""
        EVENTS.append(f"rows {ref}")
        library_ids = self._context.library.track_ids()
        found = self._context.database.connection().execute(
            "SELECT item_id, title, artist, state FROM sample_items ORDER BY rowid"
        )
        rows: list[TrackListRow] = []
        for item in found:
            state = str(item["state"])
            if ref == "missing" and state != "missing":
                continue
            # A row with a local file plays that track; a row without one is unavailable.
            playable = library_ids[0] if state == "local" and library_ids else ""
            rows.append(
                TrackListRow(
                    row_id=str(item["item_id"]),
                    title=str(item["title"]),
                    artist=str(item["artist"]),
                    album="Sample album",
                    duration_seconds=180.0,
                    track_id=playable,
                    data={"state": state},
                )
            )
        return rows

    @staticmethod
    def _cell(row: Mapping[str, Any]) -> CellValue | None:
        """Return the badge of a row. Runs on a job thread."""
        state = (row.get("data") or {}).get("state")
        if state == "missing":
            return CellValue("Missing", "secondary", action="fetch")
        if state == "local":
            return CellValue("Local")
        return None

    @staticmethod
    def _only_missing(rows: Sequence[Mapping[str, Any]]) -> bool:
        return bool(rows) and all((row.get("data") or {}).get("state") == "missing" for row in rows)

    def _toggle_watch(self, ref: str) -> None:
        self._watching = not self._watching
        EVENTS.append("watch")

    def _pick(self, item_id: str) -> TabRequest | None:
        """The primary button of a waiting item: open the list that lets the user choose."""
        EVENTS.append(f"pick {item_id}")
        return TabRequest(LIST_KIND, "missing")

    def _dismiss(self, item_id: str) -> None:
        """The cross of a waiting item: forget it; the plugin removes the row itself."""
        EVENTS.append(f"dismiss {item_id}")
        self._waiting.replace([row for row in self._waiting.rows() if row["id"] != item_id])

    def _start(self, _job: JobContext) -> None:
        """Run as a hidden job on a worker thread; ``run_on_gui`` hands a step to the GUI."""
        EVENTS.append("startup")
        self._context.run_on_gui(lambda: EVENTS.append("gui"))

    def _status_clicked(self) -> None:
        """The status bar item was clicked; runs on the graphical thread."""
        EVENTS.append("status click")

    @staticmethod
    def _offer_delete(track_ids: Sequence[str]) -> list[DeleteChoice]:
        """Add one choice to the delete confirmation. Runs on the graphical thread."""
        EVENTS.append("delete offered " + ",".join(track_ids))
        return [
            DeleteChoice(
                "log_only",
                "Sample: log only",
                "Records the selection in the sample log. No file is moved or changed.",
            )
        ]

    @staticmethod
    def _run_delete(request: DeleteRequest) -> str:
        """Run the pressed choice on a job thread, never the graphical one."""
        DELETE_RUNS.append((request.choice_id, request.track_ids, threading.get_ident()))
        EVENTS.append(f"delete {request.choice_id} {','.join(request.track_ids)}")
        return f"Logged {len(request.track_ids)} track(s)."

    @staticmethod
    def _scanned(root: Path) -> None:
        """Called on the graphical thread after a library scan finished."""
        EVENTS.append(f"scanned {root.name}")

    def _import(self) -> None:
        """Bring a copy of the first library track in as a new file, through the core."""
        library = self._context.library
        found = library.tracks(library.track_ids()[:1])
        if not found:
            EVENTS.append("import: empty library")
            return
        incoming = self._context.data_dir / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        source = incoming / "imported.wav"
        shutil.copyfile(found[0].path, source)
        # The folder is chosen once: later imports go to the same place.
        folder = self._context.settings.get("import_folder") or str(
            found[0].path.parent / "Imported"
        )
        self._context.settings.set("import_folder", folder)
        placed = self._context.files.import_file(source, Path(folder))
        EVENTS.append(f"imported {placed.name}")
        library.rescan(placed.parent)

    def _open_dialog(self) -> None:
        """Ask the core to open the sample dialog, with a text for its QML."""
        self._context.open_dialog("note", "from the pane")

    def _make_playlist(self) -> None:
        """Create a local playlist and ask the core what it is called and whether it exists."""
        playlists = self._context.playlists
        identity = playlists.create("Sample playlist", self._context.library.track_ids()[:2])
        EVENTS.append(
            f"playlist {playlists.name(identity)} {playlists.exists(identity)} "
            f"{playlists.name('missing')} {playlists.exists('missing')}"
        )

    def sync_probe(self) -> list[str]:
        """Use each store capability once (plan 125.6); the tests call it from a job thread.

        Every call goes through the context. The summary lines are also kept in ``EVENTS``.
        """
        context = self._context
        lines: list[str] = []

        # Play log: read this device's events, then store one listening of another device.
        log = context.play_log
        events, cursor = log.events_since(None, 100)
        own = [event for event in events if event.device_id == log.device_id]
        started = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
        remote = PlayLogEvent(
            event_id="sample-remote-event",
            device_id="sample-other-device",
            track_id="sample-remote-track",
            started_at=started,
            ended_at=started + timedelta(seconds=60),
            heard_ms=60_000,
            counted=True,
            title="Heard elsewhere",
        )
        first, second = log.append_remote([remote]), log.append_remote([remote])
        lines.append(f"play log {len(own)} own, cursor {cursor}, appended {first} then {second}")

        # Playlists: read at a revision, replace only if nobody changed it, report the new one.
        track_ids = context.library.track_ids()[:2]
        playlist_id = context.playlists.create("Sample sync", track_ids)
        snapshot = context.playlists.read(playlist_id)
        if snapshot is not None:
            revised = context.playlists.replace_entries(
                playlist_id, track_ids[:1], expected_revision=snapshot.revision
            )
            lines.append(f"playlist revision {snapshot.revision} to {revised}")

        # Track data: analysis, loudness and credit choices are separate layers.
        if track_ids:
            data = context.track_data.read(track_ids[0])
            context.track_data.write_analysis(
                track_ids[0],
                TrackAnalysisData(bpm=128.0, key_tonic=7, key_minor=True, algorithm_version=2),
            )
            context.track_data.write_loudness(
                track_ids[0], TrackLoudnessData(-9.5, -0.4, loudness_version=1)
            )
            lines.append(f"track data had analysis {data.analysis is not None}")

        # Synced settings: only the keys the core allows; the plugin subscribes to changes.
        synced = context.synced_settings
        cancel = synced.subscribe(lambda keys: EVENTS.append("synced " + ",".join(keys)))
        synced.write({"profile/display_name": "Sample listener"})
        cancel()
        lines.append(f"synced settings {len(synced.keys)} keys, {len(synced.read())} set")

        # Snapshot: a consistent copy of the database inside the plugin's own folder.
        target = (
            context.data_dir / "snapshots" / f"sample-{len(list(context.data_dir.glob('*')))}.db"
        )
        copy = context.database_snapshot.snapshot(target)
        lines.append(f"snapshot {copy.name}")

        EVENTS.extend(lines)
        return lines

    def provide_tracks(self, audio: bytes, duration_us: int) -> dict[str, str]:
        """Store two tracks without a file (plan 125.2) and serve the first one.

        ``audio`` is served on 127.0.0.1 and needs the token; the second track cannot be
        opened, to show the error. Returns ``{source_key: track_id}``; any thread.
        """
        if self._audio is None:
            server = AudioServer(audio)
            server.start()
            self._audio = server
        identities = self._context.track_sources.upsert(
            [
                SourceTrack(
                    SOURCE_KEY,
                    "Served over HTTP",
                    artists=("Sample artist",),
                    album="Sample album",
                    album_artist="Sample artist",
                    track_number=1,
                    duration_us=duration_us,
                    genre=("Sample genre",),
                    year=2026,
                ),
                SourceTrack(
                    BROKEN_KEY,
                    "Cannot be opened",
                    artists=("Sample artist",),
                    album="Sample album",
                    duration_us=duration_us,
                ),
            ]
        )
        EVENTS.append(f"provided {len(identities)}")
        return identities

    @property
    def audio_server(self) -> AudioServer | None:
        """The HTTP server of the sample track, once ``provide_tracks`` started it."""
        return self._audio

    def _open_track(self, source_key: str) -> PlayableSource:
        """Resolve a track into a URL and the token header. Runs on a job thread."""
        EVENTS.append(f"open {source_key}")
        if source_key == BROKEN_KEY or self._audio is None:
            raise RuntimeError("the sample server cannot be reached")
        return PlayableSource(url=self._audio.url, headers={"Authorization": f"Bearer {TOKEN}"})

    @staticmethod
    def _cover(source_key: str) -> bytes | None:
        """Give the cover image of the first track. Runs on an image thread."""
        return tiny_png() if source_key == SOURCE_KEY else None

    def _availability(self, track_ids: Sequence[str]) -> dict[str, Availability]:
        """Mark the track served over HTTP as remote: its audio is not on this computer.

        Runs on the graphical thread; it reads only the plugin's own tracks (plan 125.3).
        """
        served = {
            entry.track_id
            for entry in self._context.track_sources.list(available_only=True)
            if entry.source_key == SOURCE_KEY
        }
        return {track_id: "remote" for track_id in track_ids if track_id in served}

    # -- the contributions
    def contributions(self) -> Sequence[Contribution]:
        return [
            PluginActivity(
                "main",
                "Sample",
                "music",
                actions=(
                    PaneAction(
                        "refresh", "Refresh the samples", "repeat", lambda: EVENTS.append("refresh")
                    ),
                    PaneAction("import", "Import a sample file", "arrow-down", self._import),
                    PaneAction(
                        "playlist", "Make a sample playlist", "playlists", self._make_playlist
                    ),
                    PaneAction("note", "Open the sample dialog", "info", self._open_dialog),
                ),
                foot=self._foot,
            ),
            SidebarSection(
                "lists",
                "Sample lists",
                "main",
                self._lists,
                activate=lambda row_id: (
                    None if row_id == "group" else TabRequest(LIST_KIND, row_id)
                ),
            ),
            TabKind(
                LIST_KIND,
                lambda ref: f"Sample {ref}",
                self._rows,
                header=lambda ref: TabHeader(
                    f"Sample {ref}", "Sample list", "Rows of the sample table.", "Sample plugin"
                ),
            ),
            TabAction(
                "fetch_all",
                LIST_KIND,
                lambda ref: "Fetch missing (2)",
                lambda ref: EVENTS.append(f"fetch_all {ref}"),
                icon="arrow-down",
                kind="primary",
            ),
            TabAction(
                "watch",
                LIST_KIND,
                "Watch",
                self._toggle_watch,
                kind="toggle",
                checked=lambda ref: self._watching,
            ),
            TrackColumn(
                "status",
                "Sample status",
                self._cell,
                default_visible_for=(LIST_KIND,),
                run_action=lambda row: EVENTS.append(f"fetch {row['id']}"),
            ),
            TrackAction(
                "mark",
                "Mark as wanted",
                "Sample",
                lambda rows: EVENTS.append("mark " + ",".join(str(row["id"]) for row in rows)),
                enabled_fn=self._only_missing,
            ),
            SettingsPage("settings", "Sample", HERE / "settings.qml", backend=self._backend),
            PluginDialog("note", HERE / "dialog.qml", backend=self._backend),
            WaitingItems("waiting", "Waiting for you", self._waiting, self._pick, self._dismiss),
            StartupTask("hello", self._start),
            LibraryScanned(self._scanned),
            DeleteChoices(self._offer_delete, self._run_delete),
            TrackSource(self._open_track, self._cover),
            TrackAvailability(self._availability),
            StatusItem("status", "cloud", on_click=self._status_clicked),
        ]

    def unload(self) -> None:
        EVENTS.append("unload")
        if self._audio is not None:
            self._audio.stop()
            self._audio = None


def create(context: PluginContext) -> PluginService:
    """Build the service; the core has already applied the plugin migrations."""
    EVENTS.append("create")
    return Service(context)
