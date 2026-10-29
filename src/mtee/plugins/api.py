"""The interface between MTEE and a plugin.

This is the only core module a plugin imports. It holds what a plugin declares in its
``manifest.py`` and what the core hands to the plugin's factory: a ``PluginContext`` that
exposes a few existing core services and nothing else. Importing the module builds no
service and no Qt object, and loads no plugin: a manifest is read before the plugin is
enabled.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from mtee.domain.jobs import JobId
from mtee.persistence.database import Database
from mtee.services.file_move_service import FileMoveResult
from mtee.services.jobs import JobContext, JobTask

__all__ = [
    "API_VERSION",
    "SUPPORTED_API_VERSIONS",
    "Contribution",
    "Database",
    "FileMoveResult",
    "FileOperations",
    "JobContext",
    "JobId",
    "JobTask",
    "LibraryAccess",
    "LibraryTrack",
    "PlaylistAccess",
    "PlaylistEntry",
    "PluginContext",
    "PluginFactory",
    "PluginJobs",
    "PluginManifest",
    "PluginService",
    "PluginSettings",
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

    The core renders contributions; a plugin only describes them as data. The kinds
    (sidebar section, tab kind, track column, track action, Settings page, startup task)
    are subclasses defined with the interface contributions of step 121.5.
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


@dataclass(frozen=True, slots=True)
class PlaylistEntry:
    """One entry of a local playlist; ``track_id`` is empty while the entry is unresolved."""

    entry_id: str
    track_id: str
    title: str
    artist: str
    available: bool


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


class PlaylistAccess(Protocol):
    """Local playlists, through the core playlist service."""

    def create(self, name: str, track_ids: Sequence[str] = ()) -> str:
        """Create a local playlist holding ``track_ids`` and return its identifier.

        A playlist holds a track once: a track listed twice is kept at its first place.
        """
        ...

    def replace_entries(self, playlist_id: str, track_ids: Sequence[str]) -> None:
        """Replace all the entries of a playlist with ``track_ids``, in one transaction."""
        ...

    def entries(self, playlist_id: str) -> list[PlaylistEntry]:
        """Return the entries of a playlist in order."""
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


class PluginSettings(Protocol):
    """A key-value store reserved to one plugin (``plugins.<id>.<key>`` in the settings)."""

    def get(self, key: str, default: str | None = None) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...

    def get_json(self, key: str, default: Any = None) -> Any: ...

    def set_json(self, key: str, value: Any) -> None: ...

    def delete(self, key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class PluginContext:
    """What the core gives to the factory of a plugin.

    Only existing core services are exposed. ``database`` is shared: a plugin uses only
    its own tables, whose names start with its identifier. ``base_dir`` is
    ``<data-dir>/plugins/<id>/``; it is created when ``data_dir`` is first read.
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

    @property
    def data_dir(self) -> Path:
        """Return the folder for the plugin's own files (tokens, caches), creating it."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir


class PluginService(Protocol):
    """What a plugin's factory returns."""

    def contributions(self) -> Sequence[Contribution]:
        """Return what the plugin adds to the interface; called once, after the factory."""
        ...

    def unload(self) -> None:
        """Release threads and files. The plugin's data stays in place."""
        ...


PluginFactory = Callable[[PluginContext], PluginService]
