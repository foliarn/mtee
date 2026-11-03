"""What the Settings > Remote page reads and calls: a ``QObject`` over the connection manager.

The page only shows and asks; the rules live in ``connection.py``, ``folders.py`` and
``first_match.py``. Server reads and writes run in jobs (``tasks.submit``). QML names are camel
case, as Qt requires for properties and slots (``# noqa: N802``).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.plugins.api import PluginContext

from ..backups import (
    MANUAL,
    backup_rows,
    keep_counts,
    last_automatic,
    last_backup_text,
    make_backup,
    restore,
    schedule,
    set_keep,
    set_schedule,
)
from ..client import RemoteClient
from ..connection import ConnectionManager
from ..engine import (
    SyncEngine,
    auto_pull_on,
    idle_delay_s,
    set_auto_pull,
    set_idle_delay,
    set_sync_mode,
    sync_mode,
)
from ..fetch import download_new, set_download_new
from ..first_match import REF_COMPARE, FirstMatchController
from ..folders import clean_subpath, folder_row, local_folders, watched_path
from ..records import set_travel, travel_rows
from ..store import FolderMapping, RemoteStore
from ..tasks import submit

_KIND_TEXT = {"desktop": "Windows", "phone": "Phone", "web": "Browser"}


def device_rows(raw: Sequence[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Turn the devices of the server into the maps the page shows."""
    rows: list[dict[str, Any]] = []
    for item in raw:
        kind = str(item.get("kind", ""))
        current = bool(item.get("current", False))
        rows.append(
            {
                "deviceId": str(item.get("device_id", "")),
                "name": str(item.get("name", "")),
                "kind": kind,
                "kindText": _KIND_TEXT.get(kind, "Other"),
                "lastSeen": "connected now"
                if current
                else last_seen_text(item.get("last_seen_utc"), now),
                "current": current,
            }
        )
    return rows


def last_seen_text(value: Any, now: datetime) -> str:
    """Return 'last seen 2 days ago' for a UTC timestamp of the server."""
    try:
        seen = datetime.fromisoformat(str(value))
    except ValueError:
        return "last seen at an unknown time"
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    seconds = max(0.0, (now - seen).total_seconds())
    if seconds < 120:
        return "last seen just now"
    if seconds < 3600:
        return f"last seen {int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"last seen {int(seconds // 3600)} h ago"
    days = int(seconds // 86400)
    if days < 30:
        return f"last seen {days} day ago" if days == 1 else f"last seen {days} days ago"
    return f"last seen on {seen:%Y-%m-%d}"


def _read_folders(
    context: PluginContext, store: RemoteStore, client: RemoteClient
) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    """The server roots (id and name) and the rows of the watched folders. A job thread."""
    roots = [
        {"rootId": str(root.get("root_id", "")), "name": str(root.get("name", ""))}
        for root in client.roots()
    ]
    names = {root["rootId"]: root["name"] for root in roots}
    rows = [folder_row(folder, names) for folder in local_folders(context, store.mappings())]
    return roots, rows


class SettingsBackend(QObject):
    """The backend of ``ui/settings.qml``: properties to read and slots to call."""

    changed = Signal()

    def __init__(
        self,
        context: PluginContext,
        connection: ConnectionManager,
        first_match: FirstMatchController,
        engine: SyncEngine,
    ) -> None:
        super().__init__()
        self._context = context
        self._connection = connection
        self._first_match = first_match
        self._engine = engine
        self._store = RemoteStore(context)
        self._server_roots: list[dict[str, str]] = []
        self._folder_rows: list[dict[str, object]] = []
        # The backups (plan 126.8): the list and the retention as the server last answered.
        self._backup_raw: list[dict[str, Any]] = []
        self._backup_rows: list[dict[str, object]] = []
        self._backups_loaded = False
        self._keep: dict[str, int] = {"daily": 30, "weekly": 12}
        self._backing_up = False
        self._seen_automatic = last_automatic(context)
        connection.changed.connect(self.changed.emit)
        engine.changed.connect(self.changed.emit)
        engine.changed.connect(self._on_engine_changed)
        connection.stateChanged.connect(self._on_connection_state)

    @Property(str, notify=changed)
    def serverUrl(self) -> str:  # noqa: N802
        return self._connection.server_url

    @Property(str, notify=changed)
    def userName(self) -> str:  # noqa: N802
        return self._connection.user_name

    @Property(str, notify=changed)
    def deviceName(self) -> str:  # noqa: N802
        return self._connection.device_name

    @Property(str, notify=changed)
    def state(self) -> str:
        return self._connection.state

    @Property(str, notify=changed)
    def stateText(self) -> str:  # noqa: N802
        return self._connection.state_text

    @Property(bool, notify=changed)
    def signedIn(self) -> bool:  # noqa: N802
        return self._connection.signed_in

    @Property(bool, notify=changed)
    def connected(self) -> bool:
        return self._connection.state == "connected"

    @Property(bool, notify=changed)
    def busy(self) -> bool:
        return self._connection.busy

    @Property(list, notify=changed)
    def devices(self) -> list[dict[str, Any]]:
        return device_rows(self._connection.devices, datetime.now(UTC))

    @Property(list, notify=changed)
    def serverRoots(self) -> list[dict[str, str]]:  # noqa: N802
        return list(self._server_roots)

    @Property(list, notify=changed)
    def folderRows(self) -> list[dict[str, object]]:  # noqa: N802
        return list(self._folder_rows)

    @Slot(str, str, str, str)
    def connectTo(  # noqa: N802
        self, url: str, user: str, password: str, device_name: str
    ) -> None:
        self._connection.connect(url, user, password, device_name)

    @Slot()
    def disconnectFromServer(self) -> None:  # noqa: N802
        self._connection.disconnect()

    @Slot(str)
    def revoke(self, device_id: str) -> None:
        self._connection.revoke(device_id)

    @Slot()
    def refreshDevices(self) -> None:  # noqa: N802
        self._connection.refresh_devices()

    @Slot(str)
    def setDeviceName(self, name: str) -> None:  # noqa: N802
        self._connection.set_device_name(name)

    # -- sync ----------------------------------------------------------------------------
    @Property(str, notify=changed)
    def syncMode(self) -> str:  # noqa: N802
        return sync_mode(self._context)

    @Property(int, notify=changed)
    def idleDelay(self) -> int:  # noqa: N802
        return idle_delay_s(self._context)

    @Property(int, notify=changed)
    def pendingCount(self) -> int:  # noqa: N802
        return self._engine.pending

    @Property(bool, notify=changed)
    def autoPull(self) -> bool:  # noqa: N802
        return auto_pull_on(self._context)

    @Property(bool, notify=changed)
    def downloadNew(self) -> bool:  # noqa: N802
        return download_new(self._context)

    @Property(bool, notify=changed)
    def fetching(self) -> bool:
        return self._engine.fetching

    @Property(list, notify=changed)
    def travelRows(self) -> list[dict[str, Any]]:  # noqa: N802
        """The synced settings: one row per key, with its label and whether it travels."""
        return travel_rows(self._context)

    @Slot(str, bool)
    def setTravel(self, key: str, value: bool) -> None:  # noqa: N802
        """Switch one synced setting on or off; the next pass sends or receives it."""
        try:
            set_travel(self._context, key, value)
        except ValueError as error:
            self._context.notify(str(error))
            return
        self.changed.emit()
        self._engine.request_pass()

    @Slot(str)
    def setSyncMode(self, mode: str) -> None:  # noqa: N802
        """Auto or Manual. Switching to Auto sends what is queued."""
        try:
            set_sync_mode(self._context, mode)
        except ValueError as error:
            self._context.notify(str(error))
            return
        self.changed.emit()
        if mode == "auto":
            self._engine.request_pass()

    @Slot(bool)
    def setAutoPull(self, value: bool) -> None:  # noqa: N802
        """Pull the changes of the other devices on their own, or only on Fetch."""
        set_auto_pull(self._context, value)
        self.changed.emit()
        self._engine.apply_auto_pull()

    @Slot(bool)
    def setDownloadNew(self, value: bool) -> None:  # noqa: N802
        """Download a new server track into its folder, or show it as Server only."""
        set_download_new(self._context, value)
        self.changed.emit()

    @Slot()
    def fetchNow(self) -> None:  # noqa: N802
        self._engine.fetch_now()

    @Slot(int)
    def setIdleDelayMinutes(self, minutes: int) -> None:  # noqa: N802
        """The idle delay in minutes, as the page shows it; stored in seconds."""
        try:
            set_idle_delay(self._context, minutes * 60)
        except ValueError as error:
            self._context.notify(str(error))
            return
        self.changed.emit()

    @Slot()
    def applyPending(self) -> None:  # noqa: N802
        self._engine.apply_pending()

    # -- backups (plan 126.8) ------------------------------------------------------------
    @Property(str, notify=changed)
    def backupSchedule(self) -> str:  # noqa: N802
        return schedule(self._context)

    @Property(int, notify=changed)
    def backupKeepDaily(self) -> int:  # noqa: N802
        return self._keep["daily"]

    @Property(int, notify=changed)
    def backupKeepWeekly(self) -> int:  # noqa: N802
        return self._keep["weekly"]

    @Property(list, notify=changed)
    def backups(self) -> list[dict[str, object]]:
        """The backups on the server, newest first, as rows of date, kind, device and size."""
        return list(self._backup_rows)

    @Property(str, notify=changed)
    def lastBackupText(self) -> str:  # noqa: N802
        return last_backup_text(self._backup_raw) if self._backups_loaded else ""

    @Property(bool, notify=changed)
    def backingUp(self) -> bool:  # noqa: N802
        return self._backing_up

    @Slot(str)
    def setBackupSchedule(self, value: str) -> None:  # noqa: N802
        """Daily, Weekly or Off; the next pass checks whether a backup is due."""
        try:
            set_schedule(self._context, value)
        except ValueError as error:
            self._context.notify(str(error))
            return
        self.changed.emit()
        self._engine.request_pass()

    @Slot(int)
    def setKeepDaily(self, value: int) -> None:  # noqa: N802
        self._set_keep(daily=value, weekly=self._keep["weekly"])

    @Slot(int)
    def setKeepWeekly(self, value: int) -> None:  # noqa: N802
        self._set_keep(daily=self._keep["daily"], weekly=value)

    @Slot()
    def backUpNow(self) -> None:  # noqa: N802
        """Make a manual backup now and upload it, in a job."""
        client = self._connection.client()
        if client is None:
            self._context.notify("Connect to the server first.")
            return
        if self._backing_up:
            return
        self._backing_up = True
        self.changed.emit()
        context = self._context
        submit(
            context,
            "Backing up the database to MTEE Remote",
            lambda job: make_backup(context, client, job, kind=MANUAL),
            self._on_backed_up,
        )

    @Slot()
    def refreshBackups(self) -> None:  # noqa: N802
        """Read the list of backups and the retention from the server, in a job."""
        client = self._connection.client()
        if client is None:
            return
        submit(
            self._context,
            "Reading the backups",
            lambda _job: (client.backups(), keep_counts(client)),
            self._on_backups,
            visible=False,
        )

    @Slot(str)
    def restoreBackup(self, backup_id: str) -> None:  # noqa: N802
        """Download a backup and offer it to MTEE's restore (the person confirms there)."""
        client = self._connection.client()
        if client is None:
            self._context.notify("Connect to the server first.")
            return
        context = self._context
        submit(
            context,
            "Preparing the restore of a backup",
            lambda job: restore(context, client, job, backup_id),
            self._on_restored,
        )

    @Slot(str)
    def deleteBackup(self, backup_id: str) -> None:  # noqa: N802
        """Move a backup to the server's trash; the page asked the person first."""
        client = self._connection.client()
        if client is None:
            self._context.notify("Connect to the server first.")
            return
        submit(
            self._context,
            "Deleting a backup",
            lambda _job: client.delete_backup(backup_id),
            lambda _result, error: self._after_backup_write(error),
            visible=False,
        )

    def _set_keep(self, *, daily: int, weekly: int) -> None:
        client = self._connection.client()
        if client is None:
            self._context.notify("Connect to the server first.")
            return
        self._keep = {"daily": daily, "weekly": weekly}
        self.changed.emit()
        submit(
            self._context,
            "Saving the backup retention",
            lambda _job: set_keep(client, daily=daily, weekly=weekly),
            self._on_keep,
            visible=False,
        )

    def _on_keep(self, result: dict[str, int] | None, error: BaseException | None) -> None:
        if error is not None:
            self._context.notify(str(error) or type(error).__name__)
        elif result is not None:
            self._keep = result
        self.changed.emit()
        # Retention may have moved older backups to the trash: the list is read again.
        self.refreshBackups()

    def _on_backed_up(self, _result: object, error: BaseException | None) -> None:
        self._backing_up = False
        if error is not None:
            self._context.notify(str(error) or type(error).__name__)
        else:
            self._context.notify("The database backup is on the server.")
        self.changed.emit()
        self.refreshBackups()

    def _on_restored(self, _result: Path | None, error: BaseException | None) -> None:
        # On success MTEE's Settings > Data & privacy asks the person to confirm the restore.
        if error is not None:
            self._context.notify(str(error) or type(error).__name__)

    def _after_backup_write(self, error: BaseException | None) -> None:
        if error is not None:
            self._context.notify(str(error) or type(error).__name__)
        self.refreshBackups()

    def _on_backups(
        self,
        result: tuple[list[dict[str, Any]], dict[str, int]] | None,
        error: BaseException | None,
    ) -> None:
        if error is not None or result is None:
            if error is not None:
                self._context.log.warning("Reading the backups failed: %s", error)
            return
        raw, keep = result
        self._backup_raw = raw
        self._keep = keep
        self._backups_loaded = True
        names = {
            str(device.get("device_id", "")): str(device.get("name", ""))
            for device in self._connection.devices
        }
        self._backup_rows = list(backup_rows(raw, names))
        self.changed.emit()

    def _on_engine_changed(self) -> None:
        """A backup of the schedule may have been made in the pass: the list is read again then."""
        latest = last_automatic(self._context)
        if latest != self._seen_automatic:
            self._seen_automatic = latest
            self.refreshBackups()

    def _on_connection_state(self, state: str) -> None:
        if state == "connected":
            self.refreshBackups()

    # -- folders -------------------------------------------------------------------------
    @Slot()
    def loadFolders(self) -> None:  # noqa: N802
        """Read the server folders and the watched folders, in a job."""
        client = self._connection.client()
        if client is None:
            return
        store = self._store
        context = self._context
        submit(
            context,
            "Reading the server folders",
            lambda _job: _read_folders(context, store, client),
            self._on_folders,
            visible=False,
        )

    @Slot(str, str, str)
    def saveFolder(self, path: str, root_id: str, subpath: str) -> None:  # noqa: N802
        """Link a watched folder to a server folder (and subfolder). Writes in a job."""
        try:
            local = watched_path(self._context, path)
            cleaned = clean_subpath(subpath)
        except ValueError as error:
            self._context.notify(str(error))
            return
        if not root_id:
            self._context.notify("Choose the server folder to sync with.")
            return
        mapping = FolderMapping(local, root_id, cleaned)
        store = self._store
        submit(
            self._context,
            "Saving the folder link",
            lambda _job: store.save_mapping(mapping),
            lambda _result, error: self._after_write(error),
            visible=False,
        )

    @Slot(str)
    def removeFolder(self, path: str) -> None:  # noqa: N802
        """Remove the link of a watched folder. Existing links of its tracks stay."""
        store = self._store
        submit(
            self._context,
            "Removing the folder link",
            lambda _job: store.remove_mapping(path),
            lambda _result, error: self._after_write(error),
            visible=False,
        )

    @Slot()
    def compareNow(self) -> None:  # noqa: N802
        """Run the first match again, now. It only adds links when the person starts the sync."""
        self._first_match.run(REF_COMPARE)

    def _after_write(self, error: BaseException | None) -> None:
        if error is not None:
            self._context.notify(str(error) or type(error).__name__)
        self.loadFolders()

    def _on_folders(
        self,
        result: tuple[list[dict[str, str]], list[dict[str, object]]] | None,
        error: BaseException | None,
    ) -> None:
        if error is not None or result is None:
            self._context.notify(str(error) or type(error).__name__)
            return
        self._server_roots, self._folder_rows = result
        self.changed.emit()
