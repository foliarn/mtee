"""The remote plugin: the connection to MTEE Remote (plans 126.1 to 126.4).

The factory builds the connection, its Settings > Remote page, its status item and the first-match
dialog, and checks a saved connection in a job. The first match runs when the connection is made
and no match has been done yet, and on demand from the Folders group. Once matched, the push runs
from the computer to the server, and the fetch (on Fetch, or the Auto pull loop) brings the changes
of the other devices in. Server-only tracks are track sources, played after a download. The delete
choices and the track menu actions (Free up space, Download) are in ``offload`` (plan 126.5).
Nothing else runs until the plugin is switched on and MTEE restarts.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mtee.plugins.api import (
    CapabilityUnavailableError,
    Contribution,
    LibraryScanned,
    PluginContext,
    PluginDialog,
    PluginService,
    SettingsPage,
    StatusItem,
    TabKind,
    TrackAvailability,
    TrackSource,
    WaitingItems,
)

from .activity import RemoteActivity
from .availability import availability_column, availability_status
from .conflicts import TAB_KIND, ConflictFeature
from .connection import ConnectionManager
from .engine import SyncEngine
from .explorer import ServerFolders
from .first_match import DIALOG_ID, FirstMatchController
from .offload import OffloadService
from .sources import ServerTracks
from .store import RemoteStore
from .ui.conflict_backend import ConflictBackend
from .ui.first_match_backend import FirstMatchBackend
from .ui.settings_backend import SettingsBackend

HERE = Path(__file__).parent
PAGE_QML = HERE / "ui" / "settings.qml"
DIALOG_QML = HERE / "ui" / "first_match.qml"
CONFLICT_QML = HERE / "ui" / "conflict.qml"


class RemoteService:
    """What the factory returns: the contributions, and the release of the connection."""

    def __init__(self, context: PluginContext) -> None:
        self._context = context
        self._connection = ConnectionManager(context)
        self._first_backend = FirstMatchBackend()
        self._first_match = FirstMatchController(context, self._connection, self._first_backend)
        self._engine = SyncEngine(context, self._connection)
        self._backend = SettingsBackend(context, self._connection, self._first_match, self._engine)
        self._connection.stateChanged.connect(self._first_match.on_state)
        self._connection.stateChanged.connect(self._engine.on_state)
        store = RemoteStore(context)
        self._server_tracks = ServerTracks(context, store, self._connection)
        offload = OffloadService(context, store, self._connection)
        # The conflicts (plan 126.6): the Tasks group, their tab, and the status item's count.
        self._conflicts = ConflictFeature(
            context,
            store,
            self._connection,
            lambda: self._connection.device_name,
            self._connection.refresh_status,
        )
        self._connection.set_open_conflicts(self._conflicts.open_count)
        # The global choice of the first-match summary settles the same-audio pairs (plan 129.3).
        self._first_match.set_settle(self._conflicts.settle)
        # A setting that travels, changed by the person or another plugin, is sent on the next pass.
        self._unsubscribe_settings = _watch_synced_settings(context, self._engine)
        self._conflict_backend = ConflictBackend(self._conflicts)
        self._engine.changed.connect(self._conflicts.refresh)
        # The Remote activity and Explorer > Server (plan 126.9): read again after each pass, fetch
        # and resolution. A conflict change is read on the next turn, once the conflicts have rows.
        self._activity = RemoteActivity(
            context, store, self._engine, self._conflicts, self._connection
        )
        self._folders = ServerFolders(context, store)
        self._engine.changed.connect(self._activity.refresh)
        self._engine.changed.connect(self._folders.refresh)
        self._conflicts.changed.connect(
            lambda _conflict_id: context.run_on_gui(self._activity.refresh)
        )
        self._connection.stateChanged.connect(lambda _state: self._activity.refresh())
        self._contributions: list[Contribution] = [
            SettingsPage("remote", "Remote", PAGE_QML, backend=self._backend),
            StatusItem("connection", "cloud-off", on_click=self._open_first_conflict),
            PluginDialog(DIALOG_ID, DIALOG_QML, backend=self._first_backend, width=640),
            LibraryScanned(self._on_library_scanned),
            TrackSource(open=self._server_tracks.open, cover=self._server_tracks.cover),
            TrackAvailability(status=availability_status(context, store)),
            availability_column(context, store),
            offload.delete_choices(),
            *offload.track_actions(),
            WaitingItems(
                "conflicts",
                "Remote conflicts",
                self._conflicts.model,
                run=self._conflicts.run_waiting,
                dismiss=self._conflicts.dismiss_waiting,
            ),
            TabKind(
                TAB_KIND,
                title_fn=self._conflicts.tab_title,
                content=CONFLICT_QML,
                backend=self._conflict_backend,
                icon="alert",
            ),
            *self._activity.contributions(),
            *self._folders.contributions(),
        ]
        self._conflicts.refresh()
        self._activity.refresh()
        self._folders.refresh()
        self._connection.start()

    def _on_library_scanned(self, root: Path) -> None:
        self._engine.on_library_scanned(root)
        self._conflicts.refresh()

    def _open_first_conflict(self) -> None:
        """The status item's click: the tab of the first open conflict, when there is one."""
        rows = self._conflicts.model.rows()
        if rows:
            self._context.open_tab(TAB_KIND, str(rows[0]["id"]))

    def contributions(self) -> list[Contribution]:
        return list(self._contributions)

    def unload(self) -> None:
        if self._unsubscribe_settings is not None:
            self._unsubscribe_settings()
        self._engine.shutdown()
        self._first_match.shutdown()
        self._connection.shutdown()


def _watch_synced_settings(context: PluginContext, engine: SyncEngine) -> Callable[[], None] | None:
    """Ask for a pass when a synced setting changes (plan 126.7); None when the core has none."""
    try:
        return context.synced_settings.subscribe(lambda keys: engine.request_pass())
    except CapabilityUnavailableError:
        return None


def create(context: PluginContext) -> PluginService:
    return RemoteService(context)
