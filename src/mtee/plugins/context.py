"""The services a plugin receives, built from the core services of the running application.

``PluginHost`` is created once the core services exist. It builds one ``PluginContext`` per
plugin, with adapters that expose only what the plugin interface lists: nothing else of the
core is reachable from a context.
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from PySide6.QtCore import QObject, Qt, Signal, Slot

from mtee.domain.artist_index import OVERRIDE_MODES, split_credit_parts
from mtee.domain.artists import clean_name, normalize_key
from mtee.domain.musical_key import MusicalKey
from mtee.domain.source_tracks import SourceTrack, SourceTrackEntry
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.credit_override_repository import CreditOverrideRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository, normalize_path
from mtee.persistence.play_log_repository import PlayLogEvent, PlayLogRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.plugin_helper import HelperSetup
from mtee.plugins.api import (
    CapabilityUnavailableError,
    CreditCorrection,
    FileMoveResult,
    JobId,
    JobTask,
    LibraryTrack,
    PlaylistEntry,
    PlaylistSnapshot,
    PluginContext,
    PluginManifest,
    SettingNotSyncedError,
    StartupTask,
    TrackAnalysisData,
    TrackData,
    TrackLoudnessData,
)
from mtee.plugins.loader import LoadedPlugin, PluginManager, PluginStatus
from mtee.plugins.synced_settings import (
    SYNCED_SETTING_KEYS,
    normalize_synced_value,
)
from mtee.services.data_privacy import validate_backup
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
        play_log: PlayLogRepository | None = None,
        device_id: str = "",
        analysis: AnalysisRepository | None = None,
        credit_overrides: CreditOverrideRepository | None = None,
        play_log_changed: Callable[[], None] | None = None,
        settings_applied: Callable[[Sequence[str]], None] | None = None,
        restore_proposed: Callable[[Path], None] | None = None,
        source_tracks: SourceTrackRepository | None = None,
        source_tracks_changed: Callable[[Sequence[str]], None] | None = None,
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
        # The store capabilities of plan 125.6. Each is optional: a host built without one
        # gives its plugins a capability that raises CapabilityUnavailableError.
        self._play_log = play_log
        self._device_id = device_id
        self._analysis = analysis
        self._credit_overrides = credit_overrides
        self._play_log_changed = play_log_changed
        self._settings_applied = settings_applied
        self._restore_proposed = restore_proposed
        # Tracks without a file (plan 125.2). ``source_tracks_changed`` receives the track ids
        # that were added, changed, restored or removed, on the graphical thread.
        self._source_tracks = source_tracks
        self._source_tracks_changed = source_tracks_changed
        self._manager: PluginManager | None = None
        # The graphical thread is the one that builds the host. Compared by identifier: asking Qt
        # for the current thread from a plain Python thread adopts that thread into Qt.
        self._graphical_thread = threading.get_ident()
        self._callRequested.connect(self._run_call, Qt.ConnectionType.QueuedConnection)

    def attach_plugin_manager(self, manager: PluginManager) -> None:
        """Let the contexts read the helper setup of each plugin from ``manager``.

        The setup is read when a plugin asks for it, so it always matches the libraries that the
        manager chose. Call this before ``load_enabled``.
        """
        self._manager = manager

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
            helper_setup=lambda: self._helper_setup(plugin_id),
            **self._store_capabilities(plugin_id),
        )

    def _store_capabilities(self, plugin_id: str) -> dict[str, Any]:
        """Return the sync capabilities this host can provide, for the context of a plugin."""
        capabilities: dict[str, Any] = {
            "synced_settings": _Synced(
                self._settings, self._call_later, self._settings_applied or _ignore_keys
            ),
            "database_snapshot": _Snapshots(
                self._database,
                self._data_dir / PLUGIN_DATA_DIRECTORY / plugin_id,
                plugin_id,
                self._require_job_thread,
                self._call_later,
                self.notify,
                self._restore_proposed,
            ),
        }
        if self._source_tracks is not None:
            capabilities["track_sources"] = _TrackSources(
                self._source_tracks,
                plugin_id,
                self._call_later,
                self._source_tracks_changed,
            )
        if self._play_log is not None:
            capabilities["play_log"] = _PlayLog(
                self._play_log, self._device_id, self._call_later, self._play_log_changed
            )
        if self._analysis is not None and self._credit_overrides is not None:
            capabilities["track_data"] = _TrackData(
                self._analysis, self._credit_overrides, self._library
            )
        return capabilities

    def _helper_setup(self, plugin_id: str) -> HelperSetup:
        """Return the helper setup of ``plugin_id``; empty before a manager is attached."""
        if self._manager is None:
            return HelperSetup()
        return self._manager.helper_setup(plugin_id)

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
        if threading.get_ident() != self._graphical_thread:
            raise RuntimeError(f"{action} must be called from the graphical thread.")

    def _require_job_thread(self, action: str) -> None:
        if threading.get_ident() == self._graphical_thread:
            raise RuntimeError(
                f"{action} takes time and must not run on the graphical thread; "
                "submit it with context.jobs."
            )

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

    def replace_entries(
        self,
        playlist_id: str,
        track_ids: Sequence[str],
        expected_revision: int | None = None,
    ) -> int:
        revision = self._service.replace_entries(
            playlist_id, tuple(track_ids), expected_revision=expected_revision
        )
        self._changed()
        return revision

    def revision(self, playlist_id: str) -> int | None:
        return self._service.revision(playlist_id)

    def read(self, playlist_id: str) -> PlaylistSnapshot | None:
        revision = self._service.revision(playlist_id)  # before the entries, see the protocol
        name = self._service.playlist_name(playlist_id)
        if revision is None or name is None:
            return None
        return PlaylistSnapshot(
            playlist_id=playlist_id,
            name=name,
            revision=revision,
            entries=tuple(self.entries(playlist_id)),
        )

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


# ------------------------------------------------------- store access for sync (plan 125.6)


def _ignore_keys(keys: Sequence[str]) -> None:
    """Stand in for the application's reaction to synced settings written by a plugin."""


class _PlayLog:
    """The play log through its repository; this device's identifier comes from the host."""

    def __init__(
        self,
        repository: PlayLogRepository,
        device_id: str,
        call_later: Callable[[Callable[[], None]], None],
        changed: Callable[[], None] | None,
    ) -> None:
        self._repository = repository
        self._device_id = device_id
        self._call_later = call_later
        self._changed = changed

    @property
    def device_id(self) -> str:
        return self._device_id

    def events_since(self, cursor: str | None, limit: int) -> tuple[list[PlayLogEvent], str | None]:
        return self._repository.events_since(cursor, limit)

    def append_remote(self, events: Sequence[PlayLogEvent]) -> int:
        inserted = self._repository.insert_remote_events(events)
        if inserted and self._changed is not None:
            self._call_later(self._changed)  # the Profile statistics read the log again
        return inserted


class _TrackSources:
    """The tracks of one plugin that have no file; the plugin only reaches its own keys."""

    def __init__(
        self,
        repository: SourceTrackRepository,
        plugin_id: str,
        call_later: Callable[[Callable[[], None]], None],
        changed: Callable[[Sequence[str]], None] | None,
    ) -> None:
        self._repository = repository
        self._plugin_id = plugin_id
        self._call_later = call_later
        self._changed = changed

    def upsert(self, tracks: Sequence[SourceTrack]) -> dict[str, str]:
        for track in tracks:
            if not isinstance(track, SourceTrack):
                raise TypeError("upsert takes SourceTrack values.")
        identities, changed = self._repository.upsert(self._plugin_id, tracks)
        self._announce(changed)
        return identities

    def remove(self, source_keys: Sequence[str]) -> int:
        if isinstance(source_keys, str):
            raise TypeError("remove takes a sequence of keys, not one string.")
        changed = self._repository.remove(self._plugin_id, source_keys)
        self._announce(changed)
        return len(changed)

    def list(self, *, available_only: bool = False) -> list[SourceTrackEntry]:
        return self._repository.entries(self._plugin_id, available_only=available_only)

    def _announce(self, track_ids: list[str]) -> None:
        notify = self._changed
        if track_ids and notify is not None:
            self._call_later(lambda: notify(tuple(track_ids)))


class _TrackData:
    """Analysis, loudness and credit corrections of a track; each goes to its own store."""

    def __init__(
        self,
        analysis: AnalysisRepository,
        overrides: CreditOverrideRepository,
        library: LibraryRepository,
    ) -> None:
        self._analysis = analysis
        self._overrides = overrides
        self._library = library

    def read(self, track_id: str) -> TrackData:
        stored = self._analysis.get(track_id)
        analysis: TrackAnalysisData | None = None
        loudness: TrackLoudnessData | None = None
        if stored is not None:
            has_tempo_or_key = (
                stored.bpm is not None
                or stored.key is not None
                or stored.analyzed_at_utc is not None
                or stored.bpm_user_edited
                or stored.key_user_edited
            )
            if has_tempo_or_key:
                analysis = TrackAnalysisData(
                    bpm=stored.bpm,
                    key_tonic=stored.key.tonic if stored.key is not None else None,
                    key_minor=stored.key.minor if stored.key is not None else None,
                    bpm_user_edited=stored.bpm_user_edited,
                    key_user_edited=stored.key_user_edited,
                    source_duration_us=stored.source_duration_us,
                    algorithm_version=stored.algorithm_version,
                    analyzed_at_utc=stored.analyzed_at_utc,
                )
            if stored.loudness_version is not None:
                loudness = TrackLoudnessData(
                    integrated_lufs=stored.integrated_lufs,
                    sample_peak_dbfs=stored.sample_peak_dbfs,
                    loudness_version=stored.loudness_version,
                    source_duration_us=stored.source_duration_us,
                )
        keys = self._credit_keys(track_id)
        chosen = self._overrides.modes()
        corrections = tuple(
            CreditCorrection(credit_text=text, mode=mode)
            for key, (text, mode) in sorted(chosen.items())
            if key in keys
        )
        return TrackData(track_id, analysis, loudness, corrections)

    def write_analysis(self, track_id: str, analysis: TrackAnalysisData) -> None:
        self._require_track(track_id)
        if (analysis.key_tonic is None) != (analysis.key_minor is None):
            raise ValueError("a key needs both key_tonic and key_minor, or neither")
        key = (
            MusicalKey(analysis.key_tonic, analysis.key_minor)
            if analysis.key_tonic is not None and analysis.key_minor is not None
            else None
        )
        if analysis.bpm is not None and not (math.isfinite(analysis.bpm) and analysis.bpm > 0):
            raise ValueError("bpm must be a positive number")
        _check_optional_count("source_duration_us", analysis.source_duration_us)
        _check_optional_count("algorithm_version", analysis.algorithm_version)
        if analysis.analyzed_at_utc is not None:
            datetime.fromisoformat(analysis.analyzed_at_utc)  # ValueError when not a date
        self._analysis.import_analysis(
            track_id,
            bpm=analysis.bpm,
            key=key,
            bpm_user_edited=analysis.bpm_user_edited,
            key_user_edited=analysis.key_user_edited,
            source_duration_us=analysis.source_duration_us,
            algorithm_version=analysis.algorithm_version,
            analyzed_at_utc=analysis.analyzed_at_utc,
        )

    def write_loudness(self, track_id: str, loudness: TrackLoudnessData) -> None:
        self._require_track(track_id)
        for name, value in (
            ("integrated_lufs", loudness.integrated_lufs),
            ("sample_peak_dbfs", loudness.sample_peak_dbfs),
        ):
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        _check_optional_count("source_duration_us", loudness.source_duration_us)
        _check_optional_count("loudness_version", loudness.loudness_version)
        self._analysis.import_loudness(
            track_id,
            integrated_lufs=loudness.integrated_lufs,
            sample_peak_dbfs=loudness.sample_peak_dbfs,
            loudness_version=loudness.loudness_version,
            source_duration_us=loudness.source_duration_us,
        )

    def write_corrections(self, track_id: str, corrections: Sequence[CreditCorrection]) -> None:
        self._require_track(track_id)
        keys = self._credit_keys(track_id)
        for correction in corrections:
            if correction.mode not in OVERRIDE_MODES:
                raise ValueError(f"Unknown credit override mode: {correction.mode}")
            if normalize_key(correction.credit_text) not in keys:
                raise ValueError(
                    f"{correction.credit_text!r} is not an artist credit of this track."
                )
        for correction in corrections:
            self._overrides.set_mode(correction.credit_text, correction.mode)

    def _require_track(self, track_id: str) -> None:
        if self._library.snapshot_of(track_id) is None:
            raise LookupError("This track is not in the library.")

    def _credit_keys(self, track_id: str) -> set[str]:
        """Return the normalized credits of the track: each Artist value and its strong segments.

        The user's choices are stored by credit text, and the Artists view looks them up by
        the whole value and by each segment cut at a comma or ``feat``.
        """
        snapshot = self._library.snapshot_of(track_id)
        keys: set[str] = set()
        for value in snapshot.artist if snapshot is not None else ():
            if not clean_name(value):
                continue
            keys.add(normalize_key(value))
            keys.update(normalize_key(part.origin) for part in split_credit_parts(value))
        return keys


def _check_optional_count(name: str, value: int | None) -> None:
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError(f"{name} must be a whole number, zero or more")


class _Synced:
    """The allow-listed settings of ``mtee.plugins.synced_settings``; one object per plugin."""

    def __init__(
        self,
        settings: SettingsRepository,
        call_later: Callable[[Callable[[], None]], None],
        applied: Callable[[Sequence[str]], None],
    ) -> None:
        self._settings = settings
        self._call_later = call_later
        self._applied = applied
        self._subscribers: list[Callable[[Sequence[str]], None]] = []
        self._removers: list[Callable[[], None]] = []
        self._writing = threading.local()

    @property
    def keys(self) -> frozenset[str]:
        return SYNCED_SETTING_KEYS

    def read(self) -> dict[str, str]:
        stored = self._settings.all()
        return {key: stored[key] for key in sorted(SYNCED_SETTING_KEYS) if key in stored}

    def write(self, values: Mapping[str, str]) -> None:
        refused = sorted(set(values) - SYNCED_SETTING_KEYS)
        if refused:
            raise SettingNotSyncedError(
                f"{', '.join(refused)} cannot be synchronized between devices."
            )
        checked: dict[str, str] = {}
        for key, value in values.items():
            try:
                checked[key] = normalize_synced_value(key, value)
            except ValueError as error:
                raise ValueError(f"The value of {key} is not valid: {error}") from error
        self._writing.active = True
        try:
            self._settings.set_many(checked)
        finally:
            self._writing.active = False
        if checked:
            keys = tuple(checked)
            self._call_later(lambda: self._applied(keys))

    def subscribe(self, callback: Callable[[Sequence[str]], None]) -> Callable[[], None]:
        if not self._removers:
            self._removers.append(self._settings.add_listener(self._changed))
        self._subscribers.append(callback)

        def cancel() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
            if not self._subscribers:
                for remove in self._removers:
                    remove()
                self._removers.clear()

        return cancel

    def _changed(self, key: str) -> None:
        if key not in SYNCED_SETTING_KEYS or getattr(self._writing, "active", False):
            return
        for callback in list(self._subscribers):
            self._call_later(_announce(callback, key))


def _announce(callback: Callable[[Sequence[str]], None], key: str) -> Callable[[], None]:
    return lambda: callback((key,))


class _Snapshots:
    """Consistent copies of the database, and the offer of one to the restore of Settings."""

    def __init__(
        self,
        database: Database,
        base_dir: Path,
        plugin_id: str,
        require_job_thread: Callable[[str], None],
        call_later: Callable[[Callable[[], None]], None],
        notify: Callable[[str], None],
        propose: Callable[[Path], None] | None,
    ) -> None:
        self._database = database
        self._base_dir = base_dir
        self._plugin_id = plugin_id
        self._require_job_thread = require_job_thread
        self._call_later = call_later
        self._notify = notify
        self._propose = propose

    def snapshot(self, target_path: Path) -> Path:
        self._require_job_thread("snapshot")
        target = Path(target_path).resolve()
        if not target.is_relative_to(self._base_dir.resolve()):
            raise ValueError("A snapshot is written inside the plugin's own folder (base_dir).")
        return self._database.backup_to(target)

    def request_restore(self, path: Path) -> None:
        self._require_job_thread("request_restore")
        propose = self._propose
        if propose is None:
            raise CapabilityUnavailableError("This application cannot offer a restore.")
        source = Path(path).resolve()
        validate_backup(
            source,
            supported_version=self._database.supported_version,
            migrations=self._database.migrations,
            database_path=self._database.path,
        )
        self._notify(
            f"The plugin {self._plugin_id} offers a database backup to restore. "
            "Confirm it in Settings, Data & privacy."
        )
        self._call_later(lambda: propose(source))
