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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from PySide6.QtCore import QAbstractItemModel, QObject

from mtee.domain.jobs import JobId
from mtee.models.plugin_rows_model import PluginRowsModel
from mtee.persistence.database import Database
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
    "CellValue",
    "Contribution",
    "Database",
    "FileMoveError",
    "FileMoveResult",
    "FileOperations",
    "JobContext",
    "JobId",
    "JobTask",
    "LibraryAccess",
    "LibraryScanned",
    "LibraryTrack",
    "PaneAction",
    "PlaylistAccess",
    "PlaylistEntry",
    "PlaylistMeta",
    "PluginActivity",
    "PluginContext",
    "PluginDialog",
    "PluginFactory",
    "PluginJobs",
    "PluginManifest",
    "PluginRowsModel",
    "PluginService",
    "PluginSettings",
    "SettingsPage",
    "SidebarSection",
    "StartupTask",
    "TabAction",
    "TabHeader",
    "TabKind",
    "TabRequest",
    "Tone",
    "TrackAction",
    "TrackColumn",
    "TrackListRow",
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
    ``WaitingItems``, ``PluginDialog`` and ``PlaylistMeta``, defined below. Plugin QML reaches
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

    def name(self, playlist_id: str) -> str | None:
        """Return the name of a local playlist, or ``None`` when it no longer exists."""
        ...

    def exists(self, playlist_id: str) -> bool:
        """Return whether a local playlist with this identifier still exists."""
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

    @property
    def data_dir(self) -> Path:
        """Return the folder for the plugin's own files (tokens, caches), creating it."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir

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
    corners, a width of at most 480 px, centred over the window, closed by Escape or a click
    outside) and loads the file in it with a ``Loader``; the file sets its own title, fields
    and buttons with the components of ``Mtee``, and gives its ``implicitHeight``. It
    receives ``workspace``, ``backend``, ``ref`` (the text given to ``open_dialog``) and
    ``dialog``, whose ``close()`` closes the popup. ``ref`` changes each time the dialog is
    opened, so every binding must read it again.
    """

    dialog_id: str
    content: Path
    backend: QObject | None = None


@dataclass(frozen=True, slots=True)
class PlaylistMeta(Contribution):
    """A phrase a plugin adds to the meta line of the header of every local playlist.

    ``text(playlist_id)`` returns the phrase (for example ``"linked to Spotify"``) or ``""``
    for none. The core joins the phrases of all plugins to the meta line with `` · `` and reads
    them again after ``refresh_ui``. ``text`` runs on the graphical thread while the header is
    drawn: keep it cheap.
    """

    text: Callable[[str], str]
