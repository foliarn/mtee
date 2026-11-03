"""The interface between MTEE and a plugin.

This is the only core module a plugin imports. It holds what a plugin declares in its
``manifest.py`` and what the core hands to the plugin's factory: a ``PluginContext`` that
exposes a few existing core services and nothing else. Importing the module builds no
service and no Qt object, and loads no plugin: a manifest is read before the plugin is
enabled.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from PySide6.QtCore import QAbstractItemModel, QObject

from mtee.domain.jobs import JobId
from mtee.domain.recycling import RecycleFailure, RecycleOutcome
from mtee.domain.source_tracks import (
    NonFileTrackError,
    PlayableSource,
    SourceTrack,
    SourceTrackEntry,
)
from mtee.models.plugin_rows_model import PluginRowsModel
from mtee.persistence.database import Database
from mtee.persistence.play_log_repository import PlayLogEvent
from mtee.persistence.playlists_repository import StaleRevisionError
from mtee.plugin_helper import (
    HELPER_ENVIRONMENT_VARIABLE,
    HELPER_FLAG,
    HelperSetup,
    encode_setup,
)
from mtee.services.file_move_service import FileMoveError, FileMoveResult
from mtee.services.jobs import JobContext, JobTask

__all__ = [
    "API_VERSION",
    "SUPPORTED_API_VERSIONS",
    "ActionKind",
    "Availability",
    "AvailabilityChanged",
    "CapabilityUnavailableError",
    "CellValue",
    "Contribution",
    "CreditCorrection",
    "Database",
    "DatabaseSnapshot",
    "DeleteChoice",
    "DeleteChoices",
    "DeleteRequest",
    "DeleteTone",
    "FileMoveError",
    "FileMoveResult",
    "FileOperations",
    "JobContext",
    "JobId",
    "JobTask",
    "LibraryAccess",
    "LibraryRoot",
    "LibraryScanned",
    "LibraryTrack",
    "NonFileTrackError",
    "PaneAction",
    "PlayLogAccess",
    "PlayLogEvent",
    "PlayableSource",
    "PlaylistAccess",
    "PlaylistEntry",
    "PlaylistInfo",
    "PlaylistMeta",
    "PlaylistSnapshot",
    "PluginActivity",
    "PluginContext",
    "PluginDialog",
    "PluginFactory",
    "PluginJobs",
    "PluginManifest",
    "PluginRowsModel",
    "PluginService",
    "PluginSettings",
    "RecycleFailure",
    "RecycleOutcome",
    "SettingNotSyncedError",
    "SettingsPage",
    "SidebarSection",
    "SourceTrack",
    "SourceTrackEntry",
    "StaleRevisionError",
    "StartupTask",
    "StatusItem",
    "StatusItemAccess",
    "SyncedSettings",
    "TabAction",
    "TabHeader",
    "TabKind",
    "TabRequest",
    "Tone",
    "TrackAction",
    "TrackAnalysisData",
    "TrackAvailability",
    "TrackColumn",
    "TrackData",
    "TrackDataAccess",
    "TrackListRow",
    "TrackLoudnessData",
    "TrackSource",
    "TrackSourceAccess",
    "WaitingItems",
]

# The version of the contract between the core and a plugin (see docs/plugins.md, section 9).
API_VERSION = 1
SUPPORTED_API_VERSIONS = frozenset({API_VERSION})


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """What a plugin declares about itself, in the ``MANIFEST`` of its ``manifest.py``.

    ``plugin_id`` is lowercase snake_case, equals the name of the plugin folder and never
    changes after release. ``factory`` is ``"module:function"``: the module is inside
    ``mtee.plugins.<plugin_id>`` and is imported only when the plugin is enabled.
    ``uses_network`` is shown to the user before the plugin is switched on.
    """

    plugin_id: str
    title: str
    description: str
    version: str
    api_version: int
    factory: str
    uses_network: bool = False


@dataclass(frozen=True, slots=True)
class Contribution:
    """Base of everything a plugin adds to the interface; ``PluginService`` returns them.

    The core renders contributions; a plugin only describes them as data. The kinds are
    ``PluginActivity``, ``SidebarSection``, ``TabKind``, ``TabAction``, ``TrackColumn``,
    ``TrackAction``, ``SettingsPage``, ``StartupTask``, ``LibraryScanned``,
    ``WaitingItems``, ``PluginDialog``, ``PlaylistMeta``, ``DeleteChoices``, ``TrackSource`` and
    ``StatusItem``, ``TrackAvailability``, defined below. Plugin QML reaches
    the core components with ``import Mtee``; a contribution never names a QML type.
    """


@dataclass(frozen=True, slots=True)
class LibraryTrack:
    """One library track as a plugin reads it; the values come from the stored tags."""

    track_id: str
    path: Path
    title: str
    artists: tuple[str, ...]
    album: str
    duration_us: int
    readable: bool
    isrc: str | None = None


@dataclass(frozen=True, slots=True)
class LibraryRoot:
    """A watched folder of the library: ``root_id``, the identifier that ``FileOperations``
    takes, and its ``path``. Returned by ``LibraryAccess.roots``."""

    root_id: str
    path: Path


@dataclass(frozen=True, slots=True)
class PlaylistEntry:
    """One entry of a local playlist; ``track_id`` is empty while the entry is unresolved."""

    entry_id: str
    track_id: str
    title: str
    artist: str
    available: bool


@dataclass(frozen=True, slots=True)
class PlaylistSnapshot:
    """A local playlist as read at one revision."""

    playlist_id: str
    name: str
    revision: int
    entries: tuple[PlaylistEntry, ...]


@dataclass(frozen=True, slots=True)
class PlaylistInfo:
    """One local playlist of ``PlaylistAccess.list``: its identifier, name, revision and size."""

    playlist_id: str
    name: str
    revision: int
    entry_count: int


class LibraryAccess(Protocol):
    """Read access to the library, and the scanner for the folders a plugin brings in."""

    def track_ids(self) -> list[str]:
        """Return the identifier of every readable track, in library order."""
        ...

    def tracks(self, track_ids: Sequence[str]) -> list[LibraryTrack]:
        """Return the tracks found for ``track_ids``, in the order given."""
        ...

    def add_watched_folder(self, path: Path) -> str:
        """Add ``path`` to the library, scan it, and return its root identifier.

        Graphical thread only; an empty string means the folder was refused.
        """
        ...

    def rescan(self, path: Path) -> bool:
        """Rescan the library folder that holds ``path``; ``False`` when none does.

        Graphical thread only.
        """
        ...

    def roots(self) -> list[LibraryRoot]:
        """Return the watched folders of the library, in the order the library lists them.

        Any thread. Optional capability (``API_VERSION`` stays 1): it reads the stored folders
        and changes nothing.
        """
        ...


class PlaylistAccess(Protocol):
    """Local playlists, through the core playlist service."""

    def rename(self, playlist_id: str, name: str, expected_revision: int | None = None) -> int:
        """Give a local playlist a new name, as the interface does, and return its new revision.

        With ``expected_revision`` the rename is refused with ``StaleRevisionError`` when the
        playlist changed since, and nothing is written: the check and the write are one
        transaction. Without it the rename is unconditional. The name is stripped and must be
        between 1 and 240 characters (``ValueError`` otherwise); ``LookupError`` when the
        playlist does not exist. Optional capability (``API_VERSION`` stays 1). Any thread.
        """
        ...

    def create(self, name: str, track_ids: Sequence[str] = ()) -> str:
        """Create a local playlist holding ``track_ids`` and return its identifier.

        A playlist holds a track once: a track listed twice is kept at its first place.
        """
        ...

    def name(self, playlist_id: str) -> str | None:
        """Return the name of a local playlist, or ``None`` when it no longer exists."""
        ...

    def exists(self, playlist_id: str) -> bool:
        """Return whether a local playlist with this identifier still exists."""
        ...

    def replace_entries(
        self,
        playlist_id: str,
        track_ids: Sequence[str],
        expected_revision: int | None = None,
    ) -> int:
        """Replace all the entries of a playlist with ``track_ids``, in one transaction.

        With ``expected_revision`` (the revision a prior ``read`` or ``revision`` returned)
        the replacement is refused with ``StaleRevisionError`` when the playlist changed
        since, and nothing is written: the check and the write are one transaction. Without
        it the replacement is unconditional, as before. Returns the revision after the
        change. Any thread; raises ``LookupError`` for a track or a playlist that does not
        exist.
        """
        ...

    def entries(self, playlist_id: str) -> list[PlaylistEntry]:
        """Return the entries of a playlist in order."""
        ...

    def revision(self, playlist_id: str) -> int | None:
        """Return the revision of a local playlist, or ``None`` when it no longer exists.

        A playlist starts at revision 1 and the number rises on every change made through any
        path, the interface or a plugin: entries, name, description, cover, pin, folder.
        Any thread.
        """
        ...

    def read(self, playlist_id: str) -> PlaylistSnapshot | None:
        """Return the name, the revision and the entries of a playlist, or ``None`` if gone.

        The revision is read before the entries: if the playlist changes in between, the
        revision is the older one, and a later ``replace_entries`` with it is refused rather
        than overwriting the change. Any thread.
        """
        ...

    def list(self) -> list[PlaylistInfo]:
        """Return every local playlist, in the order the interface lists them.

        Optional capability (``API_VERSION`` stays 1): it reads the stored playlists and changes
        nothing. Any thread.
        """
        ...


class PluginJobs(Protocol):
    """Submit and cancel background work on the core job service."""

    def submit(
        self, task: JobTask, *, label: str = "Background task", visible: bool = True
    ) -> JobId:
        """Queue ``task`` and return its job identifier."""
        ...

    def cancel(self, job_id: JobId) -> None:
        """Request the cancellation of a job."""
        ...


class FileOperations(Protocol):
    """The core write services for audio files. A plugin never touches a music file directly."""

    def move_track(self, track_id: str, root_id: str, relative_folder: str) -> FileMoveResult:
        """Move a track into a library folder without replacing any file."""
        ...

    def recycle(self, track_ids: Sequence[str]) -> None:
        """Ask to send tracks to the Recycle Bin; the user confirms in the usual dialog."""
        ...

    def import_file(self, source: Path, folder: Path) -> Path:
        """Move a file that is not in the library yet into a library folder; return its path.

        The file never replaces another one: when the name is taken, the next free
        ``name (2).ext``, ``name (3).ext``... is used, also when the name is taken while the
        file is being moved. A file on another volume is copied to a hidden ``.part`` file of
        ``folder`` first and put in place at the end, so the scanner never reads a
        half-written file under its final name. ``folder`` is created when it is missing.
        The library is not updated here: the scanner picks the file up at the next scan
        (``context.library.rescan``).

        Any thread. Raises ``FileMoveError`` when ``folder`` is not inside a library folder
        or ``source`` already belongs to the library (use ``move_track``), and ``OSError``
        when the file cannot be moved; ``source`` is then untouched.
        """
        ...

    def replace_content(self, track_id: str, source: Path) -> Path:
        """Put ``source`` in place of the file of a track and return the track's path.

        The track keeps its path and its identifier. Its current file goes to the Windows
        Recycle Bin through the core's trash path, so it appears in MTEE's trash history; then
        ``source`` takes its exact path and the library is refreshed from the new file (tags,
        size, revision). ``source`` must be a regular file outside every library folder. On the
        same volume it is renamed; on another volume it is copied to a hidden ``.<name>.part``
        file of the folder first, then renamed, and the source goes to the Recycle Bin once the
        replacement is recorded. Optional capability (``API_VERSION`` stays 1).

        Holds the write lease of the track: a reader (the player, an analysis) or a tag write
        waits for it, up to 10 seconds, then ``TimeoutError``. Job thread only (``RuntimeError``
        on the graphical thread). Raises ``NonFileTrackError`` for a track without a file,
        ``LookupError`` for an unknown track, ``FileNotFoundError`` when the track's file or
        ``source`` is missing, and ``ValueError`` when ``source`` is not a regular file or lies
        inside a library folder. When the replacement fails after the old file went to the
        Recycle Bin, it raises a readable error that says where the old file is (MTEE cannot
        restore it from the Recycle Bin) and that ``source`` is untouched.
        """
        ...

    def attach_file(self, track_id: str, source: Path, folder: Path) -> Path:
        """Give a source track of this plugin a local file: move ``source`` into ``folder``.

        The track keeps its ``track_id``; the file goes into the library folder ``folder`` (created
        when missing) under the next free name, never over another file, and is recorded with
        its tags (a new revision). The plugin's source row of the track is removed. A file on
        another volume goes through a hidden ``.part`` file, as in ``import_file``. On failure
        ``source`` is back where it was and the track stays a source track. Holds the write
        lease of the track. Job thread only (``RuntimeError`` on the graphical thread).
        Raises ``ValueError`` when the track is not a source track of this plugin, when
        ``source`` is not a regular file or lies in the library, or when ``folder`` is outside
        the library; ``FileNotFoundError`` when ``source`` is missing. Optional capability
        (``API_VERSION`` stays 1): ``CapabilityUnavailableError`` without it.
        """
        ...

    def read_lease(self, track_id: str) -> AbstractContextManager[Path]:
        """Hold the read lease of a track's file and yield its path, for the ``with`` block.

        The lease is the file-access coordinator's shared read lease, the one the player and
        the audio analysis hold: a tag write or a move on the same track waits for the block
        to end (or is refused when it cannot wait). Use it to hash or upload a file without
        racing a tag write. Optional capability (``API_VERSION`` stays 1).

        Call it from a job thread (``context.jobs``), never from the graphical thread:
        ``RuntimeError`` there. The lease waits up to 10 seconds for a writer to finish; past
        that it raises ``TimeoutError`` (``FileAccessTimeoutError``). Raises
        ``NonFileTrackError`` for a track without a local file, ``FileNotFoundError`` when the
        file is missing, and ``LookupError`` for an unknown track. The path is valid only inside
        the block: keep nothing from it after the block ends.
        """
        ...


class PluginSettings(Protocol):
    """A key-value store reserved to one plugin (``plugins.<id>.<key>`` in the settings)."""

    def get(self, key: str, default: str | None = None) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...

    def get_json(self, key: str, default: Any = None) -> Any: ...

    def set_json(self, key: str, value: Any) -> None: ...

    def delete(self, key: str) -> None: ...


# ------------------------------------------------------- store access for sync (plan 125.6)
# Optional capabilities of the context. None of them names a server: a plugin that keeps
# devices in step uses them, and any other plugin may too. Each goes through the repository
# or service of the core, never a SQL handle. The threading rule is written on each call.


class CapabilityUnavailableError(RuntimeError):
    """The capability is not provided by this build or this context (for example in a test)."""

    readable = True


class PlayLogAccess(Protocol):
    """The permanent listening log, to copy it to other devices and back."""

    @property
    def device_id(self) -> str:
        """The identifier of this installation; the ``device_id`` of its own events."""
        ...

    def events_since(self, cursor: str | None, limit: int) -> tuple[list[PlayLogEvent], str | None]:
        """Return up to ``limit`` events stored after ``cursor``, oldest stored first.

        The order is the order of insertion (the ``rowid`` of ``play_events``, which has no
        sequence column): an event appended later by ``append_remote`` comes after the events
        already stored, whatever its start time. ``cursor`` is ``None`` for the first call or
        the second value of the previous call; that value is the cursor to keep, and it equals
        ``cursor`` when nothing is newer. The batch holds the events of every device, each with
        its ``device_id``: a plugin that pushes this device's events filters on ``device_id``.
        A cursor is valid for one log: if the log is reset (Settings > Data & privacy) the
        numbers start again, so a caller that finds no event where it expected some starts
        from ``None``. A path never leaves the computer: ``PlayLogEvent`` has none.
        Raises ``ValueError`` for a cursor the core did not give. Any thread.
        """
        ...

    def append_remote(self, events: Sequence[PlayLogEvent]) -> int:
        """Store events listened to on other devices; return how many were new.

        Idempotent by ``event_id``: an event already stored is skipped, so sending the same
        batch twice stores it once. Each event keeps its own ``device_id``. The batch is
        all-or-nothing: an invalid event (empty id, negative duration, naive time) raises
        ``ValueError`` and nothing is stored. The log stays append-only. The statistics and
        the Profile read these events like the others. Any thread.
        """
        ...


@dataclass(frozen=True, slots=True)
class TrackAnalysisData:
    """Tempo and key as MTEE's analysis stored them for a track (the analysis layer).

    ``key_tonic`` is 0 to 11 from C, with ``key_minor``; both are ``None`` for no key. The
    ``*_user_edited`` flags say that the person set the value by hand: Analyze never replaces it.
    ``algorithm_version`` and ``analyzed_at_utc`` say how and when it was computed.
    """

    bpm: float | None = None
    key_tonic: int | None = None
    key_minor: bool | None = None
    bpm_user_edited: bool = False
    key_user_edited: bool = False
    source_duration_us: int | None = None
    algorithm_version: int | None = None
    analyzed_at_utc: str | None = None


@dataclass(frozen=True, slots=True)
class TrackLoudnessData:
    """The loudness measured by Analyze (EBU R128 integrated loudness and sample peak).

    A silent track has a ``loudness_version`` and no values.
    """

    integrated_lufs: float | None = None
    sample_peak_dbfs: float | None = None
    loudness_version: int | None = None
    source_duration_us: int | None = None


@dataclass(frozen=True, slots=True)
class CreditCorrection:
    """The person's choice for one artist credit of the track (the corrections layer).

    ``mode`` is ``"one_artist"`` (keep the credit whole) or ``"split"`` (cut every ``&`` or
    ``x`` junction). The choice is stored by credit text and applies to every track that
    holds the credit.
    """

    credit_text: str
    mode: str


@dataclass(frozen=True, slots=True)
class TrackData:
    """What MTEE stores about one track apart from its tags and its file, by layer."""

    track_id: str
    analysis: TrackAnalysisData | None = None
    loudness: TrackLoudnessData | None = None
    corrections: tuple[CreditCorrection, ...] = ()


class TrackDataAccess(Protocol):
    """Analysis, loudness and manual corrections of a track, each in its own store.

    Nothing here reads or writes an audio file or its tags. Any thread.
    """

    def read(self, track_id: str) -> TrackData:
        """Return the stored data of a track; a layer with no data is ``None`` or empty.

        ``corrections`` holds the choices stored for the artist credits of this track.
        """
        ...

    def write_analysis(self, track_id: str, analysis: TrackAnalysisData) -> None:
        """Store tempo and key computed elsewhere, as the analysis layer, with its version.

        A value the person edited on this computer keeps its value and its flag; an incoming
        ``*_user_edited`` flag is kept. The loudness is not touched. Raises ``LookupError``
        when the track is not in the library and ``ValueError`` for an invalid value.
        """
        ...

    def write_loudness(self, track_id: str, loudness: TrackLoudnessData) -> None:
        """Store a loudness measured elsewhere, with its version; tempo and key are not touched.

        Raises ``LookupError`` when the track is not in the library and ``ValueError`` for
        an invalid value.
        """
        ...

    def write_corrections(self, track_id: str, corrections: Sequence[CreditCorrection]) -> None:
        """Store the person's choices for credits of this track, in the corrections layer.

        A choice replaces the earlier choice for the same credit; no choice is removed.
        Raises ``LookupError`` when the track is not in the library and ``ValueError`` for
        a mode that does not exist or a credit the track does not hold.
        """
        ...

    def changed_since(self, cursor: str | None, limit: int) -> tuple[list[str], str | None]:
        """Return the tracks whose analysis, loudness or corrections changed after ``cursor``.

        The change log of the core is read from its start when ``cursor`` is ``None``. Up to
        ``limit`` log records are read per call, and the batch lists each track once, in the
        order of its first change. A correction changes every track that holds the credit, so a
        batch can name more tracks than ``limit``. The second value is the cursor to keep: pass it
        to the next call; it equals ``cursor`` when nothing is newer. A cursor the core did not
        give (for example one kept before a restore of the database) raises ``ValueError``: the
        caller then starts from ``None``. Optional capability (``API_VERSION`` stays 1). Any thread.
        """
        ...


class SettingNotSyncedError(ValueError):
    """A setting key that the core does not allow to travel between devices."""

    readable = True


class SyncedSettings(Protocol):
    """The settings that may be copied between devices, and only those.

    The allow-list is ``mtee.plugins.synced_settings.SYNCED_SETTINGS``; ``keys`` lists it.
    Values are the stored text: a plain string for the profile name, JSON text for the others.
    """

    @property
    def keys(self) -> frozenset[str]:
        """The keys that may travel."""
        ...

    def read(self) -> dict[str, str]:
        """Return the stored text of every allowed key that is set. Any thread."""
        ...

    def write(self, values: Mapping[str, str]) -> None:
        """Store ``values`` and apply them to the running application.

        A key outside ``keys`` raises ``SettingNotSyncedError``, and a value the setting
        cannot hold raises ``ValueError``; the whole call is checked first, so nothing is
        stored when one entry is refused. Any thread; the running application reads the new
        values on the graphical thread. The plugin's own ``subscribe`` callback is not called
        for this write.
        """
        ...

    def subscribe(self, callback: Callable[[Sequence[str]], None]) -> Callable[[], None]:
        """Call ``callback(keys)`` on the graphical thread after an allowed key changed.

        Changes made by the person, by the core or by another plugin are announced; the
        plugin's own ``write`` is not. Returns the function that cancels the subscription;
        call it in ``unload``.
        """
        ...


class DatabaseSnapshot(Protocol):
    """A consistent copy of the library database, and the way back."""

    def snapshot(self, target_path: Path) -> Path:
        """Write a consistent copy of the database to ``target_path`` and return it.

        The copy is made with the SQLite backup API, so it holds the data still in the
        write-ahead log, and it is checked after it is written. ``target_path`` must be
        inside the plugin's own folder (``context.base_dir``) and must not exist: nothing is
        overwritten (``FileExistsError``, ``ValueError`` outside the folder). The copy holds
        the person's whole library data: treat it as private. Not the graphical thread
        (``RuntimeError``): submit it with ``context.jobs``.
        """
        ...

    def request_restore(self, path: Path) -> None:
        """Offer the database at ``path`` to the restore of Settings > Data & privacy.

        The file is checked (a database of this MTEE, intact, not the one in use) and
        ``BackupValidationError`` is raised when it is refused. Otherwise Settings opens on
        Data & privacy with the usual confirmation, "Schedule restore". Nothing changes until
        the person confirms; the restore is then applied at the next start, after a safety copy
        of the current database, as for a file the person chose. The plugin never replaces the
        database. Not the graphical thread (``RuntimeError``): submit it with ``context.jobs``.
        """
        ...


class TrackSourceAccess(Protocol):
    """The tracks this plugin provides without a file (plan 125.2), and nothing else.

    Each track gets a normal ``track_id`` (a per-machine UUID) the first time its key is stored;
    the id never changes for a key, also after ``remove`` and after a restart. Views, playlists,
    the queue and the play log then treat the track like any other. The audio comes from the
    plugin's ``TrackSource.open`` when the track is played. A plugin only sees and changes its
    own keys. Any thread.
    """

    def upsert(self, tracks: Sequence[SourceTrack]) -> dict[str, str]:
        """Store ``tracks`` under their keys and return ``{source_key: track_id}``.

        Idempotent: the same call twice changes nothing. A key stored before keeps its
        ``track_id`` and becomes available again if it was removed; its metadata is replaced.
        All tracks of one call are stored together or not at all.
        """
        ...

    def adopt(self, track_id: str, entry: SourceTrack) -> str:
        """Make an existing library track without a file a source track of this plugin.

        The track keeps its ``track_id``, so playlists, the play log and the analysis still refer
        to it; ``entry.source_key`` becomes its key. Use it after the file of the track left the
        library (it was recycled). Returns the track id. Raises ``ValueError`` when the track does
        not exist, still has a file on this computer (or a library folder still lists it), belongs
        to another plugin, or when the key is taken by another track of this plugin. Calling it
        again for the same track and key changes nothing. Any thread. Optional capability
        (``API_VERSION`` stays 1): ``CapabilityUnavailableError`` without it.
        """
        ...

    def remove(self, source_keys: Sequence[str]) -> int:
        """Make the tracks unavailable and return how many were available.

        The row, the ``track_id``, the playlist entries and the play log rows are kept; the
        track is greyed out, never played, and skipped by the queue. An unknown key and a track
        already removed are ignored, so the call is idempotent. ``upsert`` brings it back.
        """
        ...

    def list(self, *, available_only: bool = False) -> list[SourceTrackEntry]:
        """Return the tracks stored for this plugin, removed ones included, sorted by key."""
        ...


class StatusItemAccess(Protocol):
    """The item this plugin shows in the status bar under the player bar (plan 125.5).

    ``update`` shows the item, or changes it; ``clear`` hides it. Both may be called from any
    thread: the change is queued to the graphical thread. The item exists only when the plugin
    declares a ``StatusItem``; without one the calls change nothing visible. ``tone`` is one of
    the tones of the contract (``Tone``); ``progress`` is a number from 0 to 1, or ``None`` for
    no progress line; ``tooltip`` is the long sentence shown on hover; ``icon``, when given,
    replaces the icon of the declaration for this update. An invalid value raises
    ``ValueError`` in the calling thread.
    """

    def update(
        self,
        text: str,
        tone: Tone = "neutral",
        progress: float | None = None,
        tooltip: str = "",
        icon: str | None = None,
    ) -> None: ...

    def clear(self) -> None: ...


class _NoStatusBar:
    """The status item of a context built without a status bar: its calls do nothing."""

    def update(
        self,
        text: str,
        tone: Tone = "neutral",
        progress: float | None = None,
        tooltip: str = "",
        icon: str | None = None,
    ) -> None:
        return None

    def clear(self) -> None:
        return None


class _UnavailablePlayLog:
    device_id = ""

    def events_since(self, cursor: str | None, limit: int) -> tuple[list[PlayLogEvent], str | None]:
        raise CapabilityUnavailableError("The play log is not available in this context.")

    def append_remote(self, events: Sequence[PlayLogEvent]) -> int:
        raise CapabilityUnavailableError("The play log is not available in this context.")


class _UnavailableTrackData:
    def read(self, track_id: str) -> TrackData:
        raise CapabilityUnavailableError("Track data is not available in this context.")

    def write_analysis(self, track_id: str, analysis: TrackAnalysisData) -> None:
        raise CapabilityUnavailableError("Track data is not available in this context.")

    def write_loudness(self, track_id: str, loudness: TrackLoudnessData) -> None:
        raise CapabilityUnavailableError("Track data is not available in this context.")

    def write_corrections(self, track_id: str, corrections: Sequence[CreditCorrection]) -> None:
        raise CapabilityUnavailableError("Track data is not available in this context.")

    def changed_since(self, cursor: str | None, limit: int) -> tuple[list[str], str | None]:
        raise CapabilityUnavailableError("Track data is not available in this context.")


class _UnavailableSyncedSettings:
    keys: frozenset[str] = frozenset()

    def read(self) -> dict[str, str]:
        raise CapabilityUnavailableError("Synced settings are not available in this context.")

    def write(self, values: Mapping[str, str]) -> None:
        raise CapabilityUnavailableError("Synced settings are not available in this context.")

    def subscribe(self, callback: Callable[[Sequence[str]], None]) -> Callable[[], None]:
        raise CapabilityUnavailableError("Synced settings are not available in this context.")


class _UnavailableTrackSources:
    def upsert(self, tracks: Sequence[SourceTrack]) -> dict[str, str]:
        raise CapabilityUnavailableError("Track sources are not available in this context.")

    def remove(self, source_keys: Sequence[str]) -> int:
        raise CapabilityUnavailableError("Track sources are not available in this context.")

    def list(self, *, available_only: bool = False) -> list[SourceTrackEntry]:
        raise CapabilityUnavailableError("Track sources are not available in this context.")

    def adopt(self, track_id: str, entry: SourceTrack) -> str:
        raise CapabilityUnavailableError("Track sources are not available in this context.")


class _UnavailableDatabaseSnapshot:
    def snapshot(self, target_path: Path) -> Path:
        raise CapabilityUnavailableError("Database snapshots are not available in this context.")

    def request_restore(self, path: Path) -> None:
        raise CapabilityUnavailableError("Database snapshots are not available in this context.")


def _unavailable_ffmpeg() -> Path:
    raise CapabilityUnavailableError("The FFmpeg runtime is not available in this context.")


class AvailabilityChanged(Protocol):
    """The call a plugin makes to tell the core that the availability of tracks changed."""

    def __call__(self, track_ids: Sequence[str] | None = None) -> None: ...


def _ignore_availability_changed(track_ids: Sequence[str] | None = None) -> None:
    """The availability hook of a context built without one: the core is not told."""


@dataclass(frozen=True, slots=True)
class PluginContext:
    """What the core gives to the factory of a plugin.

    Only existing core services are exposed. ``database`` is shared: a plugin uses only
    its own tables, whose names start with its identifier. ``base_dir`` is
    ``<data-dir>/plugin-data/<id>/``; it is created when ``data_dir`` is first read.
    ``refresh_ui`` asks the core to read the rows, the header buttons and the cells of the
    plugin again after its data changed; any thread may call it. ``run_on_gui(fn)`` runs
    ``fn`` on the graphical thread, after the current event (a queued call, also when it is
    called from the graphical thread); any thread may call it. A ``fn`` that raises is
    logged under the plugin's logger and does not stop the application.
    ``open_dialog(dialog_id, ref)`` opens one of the plugin's ``PluginDialog`` as a modal
    popup over the window; any thread may call it. ``ref`` is handed to the dialog's QML.
    ``open_tab(kind, ref)`` opens, or focuses when it is already open, a tab of one of the
    plugin's own ``TabKind`` (``kind`` must start with ``<plugin_id>.``); any thread may call
    it, the tab opens on the graphical thread.
    ``play_log``, ``track_data``, ``synced_settings`` and ``database_snapshot`` are the
    optional store capabilities for sync; ``playlists`` also reads and checks playlist
    revisions. ``track_sources`` stores the tracks the plugin provides without a file; its
    ``TrackSource`` contribution opens them. ``status_item`` shows the plugin's item in the
    status bar; its ``StatusItem`` contribution declares it. ``availability_changed(track_ids)``
    makes the core ask the ``TrackAvailability`` contribution again for those tracks (every
    track for None); any thread may call it.
    ``ffmpeg_path()`` returns the core's pinned ``ffmpeg`` executable; any thread may call it.
    ``files.read_lease`` and ``ffmpeg_path()`` raise ``CapabilityUnavailableError`` in a context
    built without them (``ffmpeg_executable`` and the file-access coordinator). ``library.roots()``
    is part of ``library``, which every context has.
    """

    plugin_id: str
    database: Database
    library: LibraryAccess
    playlists: PlaylistAccess
    jobs: PluginJobs
    files: FileOperations
    settings: PluginSettings
    base_dir: Path
    notify: Callable[[str], None]
    log: logging.Logger
    refresh_ui: Callable[[], None] = field(default=lambda: None)
    run_on_gui: Callable[[Callable[[], None]], None] = field(default=lambda call: call())
    open_dialog: Callable[[str, str], None] = field(default=lambda dialog_id, ref="": None)
    open_tab: Callable[[str, str], None] = field(default=lambda kind, ref="": None)
    # The plugin folder and the shared libraries that a helper process of this plugin needs.
    helper_setup: Callable[[], HelperSetup] = field(default=lambda: HelperSetup())
    # Optional capabilities for sync (plan 125.6); a context built without them raises
    # CapabilityUnavailableError at the first call.
    play_log: PlayLogAccess = field(default_factory=_UnavailablePlayLog)
    track_data: TrackDataAccess = field(default_factory=_UnavailableTrackData)
    synced_settings: SyncedSettings = field(default_factory=_UnavailableSyncedSettings)
    database_snapshot: DatabaseSnapshot = field(default_factory=_UnavailableDatabaseSnapshot)
    # Tracks without a file (plan 125.2).
    track_sources: TrackSourceAccess = field(default_factory=_UnavailableTrackSources)
    # The item of the status bar (plan 125.5); a context built without one ignores the calls.
    status_item: StatusItemAccess = field(default_factory=_NoStatusBar)
    # Plan 125.3: tell the core that the availability of these tracks (all, for None) changed.
    availability_changed: AvailabilityChanged = field(default=_ignore_availability_changed)
    # The core's pinned ffmpeg executable (remote plan 126.1); behind ``ffmpeg_path()``.
    ffmpeg_executable: Callable[[], Path] = field(default=_unavailable_ffmpeg)

    @property
    def data_dir(self) -> Path:
        """Return the folder for the plugin's own files (tokens, caches), creating it."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir

    def ffmpeg_path(self) -> Path:
        """Return the path of the core's pinned ``ffmpeg`` executable, from any thread.

        It is the executable the core itself runs (the vendored runtime), never one found on
        ``PATH``. Raises ``FileNotFoundError`` when the runtime is missing from the installation.
        The plugin runs it itself, with an argument list and no shell.
        """
        return self.ffmpeg_executable()

    def python_command(self, module: str, *args: str) -> list[str]:
        """Return the command line that runs ``module`` in a helper process of this plugin.

        The helper has the plugin's package and the shared libraries of the plugin on its
        import path, and it never opens a window. ``args`` become its ``sys.argv[1:]``.
        From the sources the command is ``sys.executable -I -m mtee.plugin_helper``; in the
        packaged exe it is ``MTEE.exe --plugin-helper``, because ``sys.executable`` is the exe.

        The caller must merge ``python_environment()`` into the environment of the process.
        It must not set ``PYINSTALLER_RESET_ENVIRONMENT``: a helper may reuse the files that
        MTEE unpacked for the exe.
        """
        if getattr(sys, "frozen", False):
            return [sys.executable, HELPER_FLAG, self.plugin_id, module, *args]
        return [sys.executable, "-I", "-m", "mtee.plugin_helper", self.plugin_id, module, *args]

    def python_environment(self) -> dict[str, str]:
        """Return the variables that a helper process of this plugin needs.

        Merge them into the environment of every process started with ``python_command``.
        """
        return {HELPER_ENVIRONMENT_VARIABLE: encode_setup(self.helper_setup())}


class PluginService(Protocol):
    """What a plugin's factory returns."""

    def contributions(self) -> Sequence[Contribution]:
        """Return what the plugin adds to the interface; called once, after the factory."""
        ...

    def unload(self) -> None:
        """Release threads and files. The plugin's data stays in place."""
        ...


PluginFactory = Callable[[PluginContext], PluginService]


# --------------------------------------------------------------------- UI contributions
# Data only: the core draws them with its own components and colours. The functions a
# contribution carries run on the graphical thread, except ``TabKind.content`` (rows) and
# ``TrackColumn.value_fn``, which run on a job thread while a list loads: keep them cheap and
# read only the plugin's own data. A plugin names an icon with an icon name of the core.

Tone = Literal["neutral", "secondary", "warning"]
"""Badge colour: an outline, the secondary colour, or the warning colour (14 % tint)."""

ActionKind = Literal["primary", "neutral", "ghost", "toggle"]
"""Look of a ``TabAction``: ``toggle`` is a chip that shows ``checked``."""


@dataclass(frozen=True, slots=True)
class TabRequest:
    """A tab to open: ``kind`` is one of the plugin's ``TabKind`` and ``ref`` names the content."""

    kind: str
    ref: str = ""


@dataclass(frozen=True, slots=True)
class PaneAction:
    """An icon button in the header of a sidebar pane or section."""

    action_id: str
    tip: str
    icon: str
    run: Callable[[], None]


@dataclass(frozen=True, slots=True)
class SidebarSection(Contribution):
    """A collapsible section of a sidebar pane, listing the rows of ``model``.

    ``activity`` is ``"playlists"`` (below the local playlists), ``"explorer"``, or the
    ``activity_id`` of a ``PluginActivity`` of the same plugin. ``model`` is a
    ``PluginRowsModel`` the plugin keeps up to date. ``activate`` receives the ``id`` of the
    row the user clicked and answers which tab to open, or ``None`` for none.
    """

    section_id: str
    title: str
    activity: str
    model: QAbstractItemModel
    actions: tuple[PaneAction, ...] = ()
    activate: Callable[[str], TabRequest | None] | None = None


@dataclass(frozen=True, slots=True)
class PluginActivity(Contribution):
    """An activity of its own: a button in the activity bar and a sidebar pane.

    The pane shows ``title`` with ``actions`` in its header, then the ``SidebarSection`` of
    the plugin that name this activity. ``foot`` is an optional ``PluginRowsModel`` of
    ``{"text", "tone"}`` rows drawn at the bottom of the pane.
    """

    activity_id: str
    title: str
    icon: str
    actions: tuple[PaneAction, ...] = ()
    foot: QAbstractItemModel | None = None


@dataclass(frozen=True, slots=True)
class TrackListRow:
    """One row of a plugin track list.

    A row with an empty ``track_id`` has no local file: it is greyed out, cannot be played,
    is skipped by Play, Shuffle and the queue, and offers no "Add to playlist". ``row_id`` is
    unique in the list; ``track_id`` is the library track that plays the row. ``data`` is
    handed back to the plugin's functions with the row.
    """

    row_id: str
    title: str
    artist: str = ""
    album: str = ""
    duration_seconds: float = 0.0
    track_id: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TabHeader:
    """The header of a plugin track list tab, laid out like a playlist header."""

    title: str
    kind_label: str = "Playlist"
    description: str = ""
    creator: str = ""
    meta: str = ""


@dataclass(frozen=True, slots=True)
class TabKind(Contribution):
    """A kind of editor tab. ``kind`` is ``"<plugin_id>.<name>"``; tabs are not restored.

    ``content`` is either the path of a plugin QML file, loaded in the tab with a ``Loader``
    and given ``workspace``, ``tab``, ``groupIndex``, ``bottomInset`` and ``backend``, or a
    function that returns the ``TrackListRow`` of a ref, which the core shows with its own
    track list (search, sort, selection, queue and context menu included). ``title_fn``
    gives the title of the tab for a ref; ``header`` the header of a track list tab.
    """

    kind: str
    title_fn: Callable[[str], str]
    content: Path | Callable[[str], Sequence[TrackListRow]]
    header: Callable[[str], TabHeader] | None = None
    backend: QObject | None = None
    icon: str = "playlists"


@dataclass(frozen=True, slots=True)
class TabAction(Contribution):
    """A button beside Play and Shuffle in the header of a plugin or local playlist tab.

    ``tab_kind`` is a ``TabKind.kind`` of the plugin, or ``"playlist"`` for local playlists.
    The functions receive the ref of the tab (the playlist identifier for a local one).
    ``label`` may be a function of the ref, for text such as a count. ``enabled`` returning
    ``False`` greys the button out. ``disabled_reason`` returns a sentence when the button
    cannot be used now, and ``""`` when it can: the button then looks disabled and shows the
    sentence as its tooltip, so the user learns why (for example a missing dependency).
    """

    action_id: str
    tab_kind: str
    label: str | Callable[[str], str]
    run: Callable[[str], None]
    icon: str = ""
    kind: ActionKind = "neutral"
    checked: Callable[[str], bool] | None = None
    enabled: Callable[[str], bool] | None = None
    disabled_reason: Callable[[str], str] | None = None


@dataclass(frozen=True, slots=True)
class CellValue:
    """What a plugin column shows for a row: a badge, and optionally one inline button."""

    text: str
    tone: Tone = "neutral"
    action: str = ""


@dataclass(frozen=True, slots=True)
class TrackColumn(Contribution):
    """A column of the track lists, listed in the column picker with the plugin name.

    ``value_fn`` receives the row of the list (``id``, ``trackId``, ``title``, ``artist``,
    ``album``, ``available``, ``data`` for a plugin row, and ``tabKind`` / ``tabRef``, the
    list the row is shown in) and returns ``None`` for an empty cell. ``default_visible_for``
    lists the tab kinds where the column is shown until
    the user hides it (``"playlist"`` or a ``TabKind.kind``); elsewhere it starts hidden.
    ``run_action`` is called with the row when the user presses the inline button named by
    ``CellValue.action``.
    """

    column_id: str
    title: str
    value_fn: Callable[[Mapping[str, Any]], CellValue | None]
    default_visible_for: tuple[str, ...] = ()
    width: int = 112
    run_action: Callable[[Mapping[str, Any]], None] | None = None


@dataclass(frozen=True, slots=True)
class TrackAction(Contribution):
    """An entry of the track context menu, in a captioned group before "File actions".

    ``enabled_fn`` receives the selected rows and decides whether the entry shows for them
    (``None``: always). ``run`` receives the same rows; it usually submits a job.
    """

    action_id: str
    label: str
    group: str
    run: Callable[[Sequence[Mapping[str, Any]]], None]
    enabled_fn: Callable[[Sequence[Mapping[str, Any]]], bool] | None = None


@dataclass(frozen=True, slots=True)
class SettingsPage(Contribution):
    """An extra page of Settings, after Plugins and before About.

    ``content`` is a plugin QML file given ``workspace`` and ``backend``.
    """

    page_id: str
    label: str
    content: Path
    backend: QObject | None = None


@dataclass(frozen=True, slots=True)
class StartupTask(Contribution):
    """Work submitted as a job once the plugin is registered."""

    task_id: str
    run: JobTask


@dataclass(frozen=True, slots=True)
class LibraryScanned(Contribution):
    """A function the core calls after a library scan or rescan has finished.

    ``callback`` receives the library folder (the root a folder was added with) whose scan
    completed, as a ``Path``, on the graphical thread. The tracks of the scan are already in
    the library, so ``context.library`` finds them. A scan that was cancelled, superseded by a
    newer one or interrupted is not announced. The call ends with the plugin: nothing is
    called once it is unloaded or disabled.
    """

    callback: Callable[[Path], None]


@dataclass(frozen=True, slots=True)
class WaitingItems(Contribution):
    """A group of the Tasks page and pane for work that waits for the user's answer.

    The group is drawn with ``title`` (for example ``"Waiting for you"``) and a count, in the
    style of the tag conflicts, and is hidden while ``model`` is empty. ``model`` is a
    ``PluginRowsModel`` the plugin keeps up to date; a row has ``id``, ``title`` (the item),
    ``subtitle`` (what is needed) and ``action`` (the label of its primary button, ``"Open"``
    when missing). Waiting items count in the badge of the Tasks activity.
    ``run(row_id)`` answers the primary button: it returns a ``TabRequest`` to open or ``None``.
    ``dismiss(row_id)`` answers the cross; the plugin then removes the row from its model.
    Both run on the graphical thread.
    """

    section_id: str
    title: str
    model: QAbstractItemModel
    run: Callable[[str], TabRequest | None]
    dismiss: Callable[[str], None]


@dataclass(frozen=True, slots=True)
class PluginDialog(Contribution):
    """A modal dialog the plugin opens with ``PluginContext.open_dialog(dialog_id, ref)``.

    ``content`` is a plugin QML file. The core draws the popup (surface, border, rounded
    corners, centred over the window, closed by Escape or a click outside) and loads the file
    in it with a ``Loader``; the file sets its own title, fields and buttons with the components
    of ``Mtee``, and gives its ``implicitHeight``. It receives ``workspace``, ``backend``,
    ``ref`` (the text given to ``open_dialog``) and ``dialog``, whose ``close()`` closes the
    popup. ``ref`` changes each time the dialog is opened, so every binding must read it again.

    ``width`` is the popup width in pixels, from 320 to 640 (default 480). A popup is never
    wider than the window less 16 px on each side. A value outside the range refuses the plugin.
    """

    dialog_id: str
    content: Path
    backend: QObject | None = None
    width: int = 480


@dataclass(frozen=True, slots=True)
class PlaylistMeta(Contribution):
    """A phrase a plugin adds to the meta line of the header of every local playlist.

    ``text(playlist_id)`` returns the phrase (for example ``"linked to Spotify"``) or ``""``
    for none. The core joins the phrases of all plugins to the meta line with `` · `` and reads
    them again after ``refresh_ui``. ``text`` runs on the graphical thread while the header is
    drawn: keep it cheap.
    """

    text: Callable[[str], str]


# ------------------------------------------------------------ delete choices (plan 125.4)

DeleteTone = Literal["normal", "danger"]
"""Look of a delete choice: a normal button, or the red button of the core's destructive actions."""


@dataclass(frozen=True, slots=True)
class DeleteChoice:
    """One extra action a plugin offers in the confirmation that precedes the Recycle Bin.

    ``choice_id`` is unique among the choices of the plugin for one selection. ``label`` is the
    text of the button; ``description`` is one or two sentences under the plugin's heading that
    say what the choice does, including what it does not undo. ``tone`` is ``"danger"`` for a
    choice that cannot be undone from MTEE. ``replaces_recycle`` says that, for these tracks,
    the plugin's choices stand in for the core's "Move to Recycle Bin" button, which is then
    not drawn. Pressing any plugin choice runs ``DeleteChoices.run`` and nothing else: the core
    moves no file to the Recycle Bin on its own for a plugin choice.
    """

    choice_id: str
    label: str
    description: str = ""
    tone: DeleteTone = "normal"
    replaces_recycle: bool = False


@dataclass(frozen=True, slots=True)
class DeleteChoices(Contribution):
    """Extra choices in the confirmation shown before tracks go to the Recycle Bin.

    ``offer(track_ids)`` receives the identifiers of the selected tracks and returns the
    ``DeleteChoice`` that apply to them, or nothing. It runs on the graphical thread each time
    the confirmation opens: keep it cheap and read only the plugin's own data.

    ``run(request)`` runs when the user presses a choice, on a job thread (the core submits it
    with the job service, so it shows in Tasks and ``request.job`` can be cancelled). The
    ``DeleteRequest`` carries the choice id, the identifiers that ``offer`` received and
    ``request.recycle``. It returns a short sentence that tells what was done, or ``None`` for
    the default "Done."; it raises when it fails. An exception with the class attribute
    ``readable = True`` is shown as its message alone, any other as ``ClassName: message``, as
    in Tasks. Pressing a choice moves no file by itself: a choice that must recycle files calls
    ``request.recycle``, which needs no second dialog because the user confirmed the selection
    just before. A plugin has at most one ``DeleteChoices``. If ``offer`` raises, the failure is
    logged and announced once, the plugin's choices are left out and the core action works as
    usual.
    """

    offer: Callable[[Sequence[str]], Sequence[DeleteChoice]]
    run: Callable[[DeleteRequest], str | None]


@dataclass(frozen=True, slots=True)
class DeleteRequest:
    """What a plugin receives when the user presses one of its delete choices.

    ``choice_id`` is the id the plugin gave its ``DeleteChoice``. ``track_ids`` are the
    identifiers of the selection, the ones ``offer`` received. ``job`` is the job the choice
    runs in: ``job.is_cancelled`` and ``job.raise_if_cancelled()`` tell when the user cancelled.

    ``recycle(track_ids)`` sends the given tracks' files to the Windows Recycle Bin through the
    core's own recycle path, without opening the confirmation again. Call it on the job thread
    only. Only identifiers of ``track_ids`` are accepted; any other raises ``ValueError``. The
    files are the ones the confirmation showed, and every rule of that path applies: the file
    must still be the one that was confirmed, the operation is recorded in the recycle journal,
    the file goes to the Windows Recycle Bin and is never deleted permanently, and a file that is
    in use is reported, not forced. When the Recycle Bin does not confirm a file, the rest are not
    attempted and are reported as failed. It returns a ``RecycleOutcome``: the identifiers that
    were recycled and the ones that were not, each with its reason. If the job is cancelled, the
    files already recycled stay recycled and the cancellation is raised.
    """

    choice_id: str
    track_ids: tuple[str, ...]
    job: JobContext
    _recycle: Callable[[Sequence[str]], RecycleOutcome] = field(repr=False, compare=False)

    def recycle(self, track_ids: Sequence[str]) -> RecycleOutcome:
        """Recycle the given tracks of this selection; job thread. See the class."""
        requested = tuple(dict.fromkeys(str(value) for value in track_ids))
        outside = [track_id for track_id in requested if track_id not in self.track_ids]
        if outside:
            raise ValueError(
                "These tracks are not part of this delete choice: " + ", ".join(outside)
            )
        return self._recycle(requested)


@dataclass(frozen=True, slots=True)
class TrackSource(Contribution):
    """How the core plays, and shows the cover of, the tracks this plugin stores without a file.

    ``open(source_key)`` resolves a track into a ``PlayableSource``: a local ``Path`` (a file
    the plugin downloaded) or an ``http(s)`` ``url`` with ``headers`` sent for that track only.
    It runs on a **job thread**, never on the graphical thread, because it may take a network
    round trip: it may block, but it must return or raise in a reasonable time. When it raises,
    or returns something that is not a ``PlayableSource``, the player shows an error that names
    the plugin and goes on with the next track. The core calls it again for every play and for
    the early preparation of the next track; it never keeps the result.

    ``cover(source_key)`` returns the bytes of the cover image (PNG or JPEG), or ``None``. It
    runs on an image worker thread, on demand, and may be slow; the core caches what it gets.
    A plugin has at most one ``TrackSource``.
    """

    open: Callable[[str], PlayableSource]
    cover: Callable[[str], bytes | None] | None = None


# ------------------------------------------------- track availability (plan 125.3)

Availability = Literal["local", "synced", "remote"]
"""Where a track is: "local" (its file is on this device), "synced" (on this device and kept
in step with another place) or "remote" (not on this device)."""


@dataclass(frozen=True, slots=True)
class TrackAvailability(Contribution):
    """Which tracks are not on this device, for the view filter "Hide tracks not on this device".

    ``status(track_ids)`` receives track identifiers and returns ``{track_id: availability}``.
    A track missing from the answer, or with another value, counts as ``"local"``. The core
    calls it on the graphical thread each time it shows or refilters a track list, and only
    while the filter is on: keep it cheap and read only the plugin's own data. When the answer
    for some tracks changes, the plugin calls ``PluginContext.availability_changed``. The badge
    is not drawn here: the plugin draws it with a ``TrackColumn``. At most one plugin provides
    this contribution; a second one is refused with a reason.
    """

    status: Callable[[Sequence[str]], Mapping[str, Availability]]


# ------------------------------------------------------------------ status bar (plan 125.5)


@dataclass(frozen=True, slots=True)
class StatusItem(Contribution):
    """The item the plugin shows in the status bar, the strip under the player bar.

    The strip is drawn only while at least one plugin shows an item; the items are in plugin load
    order. ``item_id`` is lowercase snake_case. ``icon`` is the name of an icon of the core. The
    text, tone, progress and tooltip come from ``PluginContext.status_item.update``, which is also
    where the item appears; ``clear`` hides it. ``on_click()`` runs on the graphical thread when
    the user clicks the item, for example to open a plugin activity or dialog; ``None`` makes the
    item a plain text. A failure of ``on_click`` is logged and announced once, as other plugin
    failures are, and the application goes on. A plugin declares at most one ``StatusItem``.
    """

    item_id: str
    icon: str
    on_click: Callable[[], None] | None = None
