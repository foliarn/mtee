"""The services a plugin receives, built from the core services of the running application.

``PluginHost`` is created once the core services exist. It builds one ``PluginContext`` per
plugin, with adapters that expose only what the plugin interface lists: nothing else of the
core is reachable from a context.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository, normalize_path
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import (
    FileMoveResult,
    JobId,
    JobTask,
    LibraryTrack,
    PlaylistEntry,
    PluginContext,
    PluginManifest,
    StartupTask,
)
from mtee.plugins.loader import LoadedPlugin, PluginStatus
from mtee.services.file_move_service import FileMoveService
from mtee.services.jobs import JobService
from mtee.services.playlist_service import PlaylistService

__all__ = ["PluginHost", "RecycleRequests", "RootActions"]

PLUGIN_DATA_DIRECTORY = "plugin-data"
SETTINGS_PREFIX = "plugins"


class RootActions(Protocol):
    """The library actions of the workspace; they run on the graphical thread."""

    def addRoot(self, selected: str) -> str: ...

    def rescanRoot(self, root_id: str) -> str: ...


class RecycleRequests(Protocol):
    """The trash flow of the core: it asks the user to confirm before any file is recycled."""

    def request_recycle(self, raw_track_ids: list) -> None: ...


class PluginHost(QObject):
    """Builds the context of each plugin and carries its notices to the workspace.

    ``noticeRaised`` is the workspace message line. It is safe to emit from a job thread:
    Qt queues the signal to the graphical thread.
    """

    noticeRaised = Signal(str)
    uiRefreshRequested = Signal()
    dialogRequested = Signal(str, str)
    tabRequested = Signal(str, str)
    _callRequested = Signal(object)

    def __init__(
        self,
        *,
        data_dir: Path,
        database: Database,
        settings: SettingsRepository,
        library: LibraryRepository,
        playlists: PlaylistService,
        jobs: JobService,
        file_moves: FileMoveService,
        recycle: RecycleRequests,
        roots: RootActions,
        refresh_playlists: Callable[[], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._data_dir = data_dir
        self._database = database
        self._settings = settings
        self._library = library
        self._playlists = playlists
        self._jobs = jobs
        self._file_moves = file_moves
        self._recycle = recycle
        self._roots = roots
        self._refresh_playlists = refresh_playlists
        self._callRequested.connect(self._run_call, Qt.ConnectionType.QueuedConnection)

    def context_for(self, manifest: PluginManifest) -> PluginContext:
        """Return the context of one plugin."""
        plugin_id = manifest.plugin_id
        log = logging.getLogger(f"mtee.plugins.{plugin_id}")
        return PluginContext(
            plugin_id=plugin_id,
            database=self._database,
            library=_Library(self._library, self._roots, self._require_graphical_thread),
            playlists=_Playlists(self._playlists, self._later_refresh_playlists),
            jobs=_Jobs(self._jobs),
            files=_Files(self._file_moves, self._recycle, self._call_later),
            settings=_ScopedSettings(self._settings, plugin_id),
            base_dir=self._data_dir / PLUGIN_DATA_DIRECTORY / plugin_id,
            notify=self.notify,
            log=log,
            refresh_ui=self._request_ui_refresh,
            run_on_gui=lambda call: self._run_on_gui(call, log),
            open_dialog=lambda dialog_id, ref="": self._open_dialog(plugin_id, dialog_id, ref),
            open_tab=lambda kind, ref="": self._open_tab(plugin_id, kind, ref, log),
        )

    def run_startup_tasks(self, plugins: Sequence[LoadedPlugin]) -> None:
        """Submit the ``StartupTask`` of every running plugin as a background job."""
        for record in plugins:
            if record.status is not PluginStatus.RUNNING:
                continue
            for task in record.contributions:
                if isinstance(task, StartupTask):
                    self._jobs.submit(
                        task.run, label=f"{record.title}: {task.task_id}", visible=False
                    )

    def notify(self, text: str) -> None:
        """Show ``text`` on the workspace message line, from any thread."""
        self.noticeRaised.emit(text)

    def _request_ui_refresh(self) -> None:
        self.uiRefreshRequested.emit()

    def _open_dialog(self, plugin_id: str, dialog_id: str, ref: str) -> None:
        """Ask the window to open the dialog ``<plugin_id>.<dialog_id>``, from any thread."""
        self._call_later(lambda: self.dialogRequested.emit(f"{plugin_id}.{dialog_id}", ref))

    def _open_tab(self, plugin_id: str, kind: str, ref: str, log: logging.Logger) -> None:
        """Ask the window to open or focus a tab of the plugin's own kind, from any thread."""
        if not kind.startswith(f"{plugin_id}."):
            log.error("open_tab refused %r: a plugin opens only its own tab kinds.", kind)
            return
        self._call_later(lambda: self.tabRequested.emit(kind, ref))

    def _run_on_gui(self, call: Callable[[], None], log: logging.Logger) -> None:
        """Queue ``call`` for the graphical thread; a failure is logged, never raised there."""

        def guarded() -> None:
            try:
                call()
            except Exception:
                log.exception("A function queued with run_on_gui failed.")

        self._call_later(guarded)

    def _call_later(self, call: Callable[[], None]) -> None:
        """Run ``call`` on the graphical thread, after the current event."""
        self._callRequested.emit(call)

    def _later_refresh_playlists(self) -> None:
        self._call_later(self._refresh_playlists)

    def _require_graphical_thread(self, action: str) -> None:
        if QThread.currentThread() is not self.thread():
            raise RuntimeError(f"{action} must be called from the graphical thread.")

    @Slot(object)
    def _run_call(self, call: object) -> None:
        if callable(call):
            call()


class _ScopedSettings:
    """The settings of one plugin: its keys live under ``plugins.<id>.``."""

    def __init__(self, settings: SettingsRepository, plugin_id: str) -> None:
        self._settings = settings
        self._prefix = f"{SETTINGS_PREFIX}.{plugin_id}."

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._settings.get(self._key(key), default)

    def set(self, key: str, value: str) -> None:
        self._settings.set(self._key(key), value)

    def get_json(self, key: str, default: Any = None) -> Any:
        return self._settings.get_json(self._key(key), default)

    def set_json(self, key: str, value: Any) -> None:
        self._settings.set_json(self._key(key), value)

    def delete(self, key: str) -> None:
        self._settings.delete(self._key(key))

    def _key(self, key: str) -> str:
        if not key:
            raise ValueError("a setting key is required")
        return self._prefix + key


class _Library:
    def __init__(
        self,
        library: LibraryRepository,
        roots: RootActions,
        require_graphical_thread: Callable[[str], None],
    ) -> None:
        self._library = library
        self._roots = roots
        self._require_graphical_thread = require_graphical_thread

    def track_ids(self) -> list[str]:
        identifiers: list[str] = []
        for root in self._library.roots():
            identifiers.extend(self._library.track_ids_in_tree(str(root["id"]), ""))
        return identifiers

    def tracks(self, track_ids: Sequence[str]) -> list[LibraryTrack]:
        found: list[LibraryTrack] = []
        for track_id in dict.fromkeys(track_ids):
            source = self._library.source_record(track_id)
            if source is None:
                continue
            snapshot = source.snapshot
            found.append(
                LibraryTrack(
                    track_id=track_id,
                    path=source.path,
                    title=snapshot.title[0] if snapshot.title else source.path.stem,
                    artists=snapshot.artist,
                    album=snapshot.album[0] if snapshot.album else "",
                    duration_us=snapshot.technical.duration_us or 0,
                    readable=source.status == "readable",
                    isrc=snapshot.isrc,
                )
            )
        return found

    def add_watched_folder(self, path: Path) -> str:
        self._require_graphical_thread("add_watched_folder")
        return self._roots.addRoot(str(path))

    def rescan(self, path: Path) -> bool:
        self._require_graphical_thread("rescan")
        wanted = Path(normalize_path(path))
        for root in self._library.roots():
            if wanted.is_relative_to(Path(normalize_path(str(root["path"])))):
                self._roots.rescanRoot(str(root["id"]))
                return True
        return False


class _Playlists:
    def __init__(self, service: PlaylistService, changed: Callable[[], None]) -> None:
        self._service = service
        self._changed = changed

    def create(self, name: str, track_ids: Sequence[str] = ()) -> str:
        identity = self._service.create_playlist(name, tuple(track_ids))
        self._changed()
        return identity

    def replace_entries(self, playlist_id: str, track_ids: Sequence[str]) -> None:
        self._service.replace_entries(playlist_id, tuple(track_ids))
        self._changed()

    def name(self, playlist_id: str) -> str | None:
        return self._service.playlist_name(playlist_id)

    def exists(self, playlist_id: str) -> bool:
        return self._service.playlist_name(playlist_id) is not None

    def entries(self, playlist_id: str) -> list[PlaylistEntry]:
        return [
            PlaylistEntry(
                entry_id=str(row["entryId"]),
                track_id=str(row["trackId"]),
                title=str(row["title"]),
                artist=str(row["artist"]),
                available=bool(row["available"]),
            )
            for row in self._service.rows(playlist_id)
        ]


class _Jobs:
    def __init__(self, jobs: JobService) -> None:
        self._jobs = jobs

    def submit(
        self, task: JobTask, *, label: str = "Background task", visible: bool = True
    ) -> JobId:
        return self._jobs.submit(task, label=label, visible=visible)

    def cancel(self, job_id: JobId) -> None:
        self._jobs.cancel(job_id)


class _Files:
    def __init__(
        self,
        file_moves: FileMoveService,
        recycle: RecycleRequests,
        call_later: Callable[[Callable[[], None]], None],
    ) -> None:
        self._file_moves = file_moves
        self._recycle = recycle
        self._call_later = call_later

    def move_track(self, track_id: str, root_id: str, relative_folder: str) -> FileMoveResult:
        folder = self._file_moves.resolve_folder(root_id, relative_folder)
        return self._file_moves.move(track_id, folder)

    def recycle(self, track_ids: Sequence[str]) -> None:
        identifiers = list(track_ids)
        self._call_later(lambda: self._recycle.request_recycle(identifiers))

    def import_file(self, source: Path, folder: Path) -> Path:
        return self._file_moves.import_file(source, folder)
