"""The sync engine: when the push runs, one pass at a time (plan 126.3), and the fetch (126.4).

A pass is ``detect_changes`` and, in Auto mode, ``run_queue``. In Manual mode the pass only queues,
and the queue waits for ``apply_pending``. A pass starts when the connection becomes ``connected``,
every 60 seconds, after a library scan, when the mode changes, and when the person presses Apply.
It runs only once the first match is done. One pass runs at a time: a request made meanwhile runs
one more pass when the first one ends. Before a pass, the downloads of new items are linked once
their file is in the library (``link_pending_imports``).

The fetch (server to computer) runs on Fetch (``fetch_now``) and, when *Auto pull* is on, in the
long-poll loop of ``pull.AutoPull``. The work runs in jobs (``tasks.submit``); this object lives on
the graphical thread.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Signal

from mtee.domain.jobs import JobCancelledError
from mtee.plugins.api import JobContext, JobId, PluginContext

from . import maintenance
from .backups import is_due, run_automatic
from .client import NetworkError, RemoteClient
from .fetch import FetchResult, fetch_once, link_pending_imports
from .first_match import DONE_SETTING
from .pull import AutoPull
from .push import (
    DetectReport,
    QueueReport,
    detect_changes,
    pending_count,
    retry_failed,
    run_queue,
)
from .records import push_records
from .sources import refresh_server_only
from .store import RemoteStore
from .tasks import submit

SYNC_MODE_KEY = "sync_mode"
IDLE_DELAY_KEY = "idle_delay_s"
AUTO_PULL_KEY = "auto_pull"
AUTO = "auto"
MANUAL = "manual"
MODES = (AUTO, MANUAL)
DEFAULT_IDLE_DELAY_S = 120
MAX_IDLE_DELAY_S = 3600
PASS_INTERVAL_MS = 60_000
STATUS_ICON = "repeat"
CONNECTED = "connected"


class SyncLink(Protocol):
    """What the engine needs of the connection: its state, a client, and a status refresh."""

    @property
    def state(self) -> str: ...

    def client(self) -> RemoteClient | None: ...

    def refresh_status(self) -> None: ...


def sync_mode(context: PluginContext) -> str:
    """The mode of the push: Auto unless the setting says Manual."""
    value = context.settings.get(SYNC_MODE_KEY, AUTO)
    return value if value in MODES else AUTO


def set_sync_mode(context: PluginContext, mode: str) -> None:
    if mode not in MODES:
        raise ValueError("The sync mode must be Auto or Manual.")
    context.settings.set(SYNC_MODE_KEY, mode)


def auto_pull_on(context: PluginContext) -> bool:
    """Whether the changes of other devices are pulled on their own (off by default)."""
    return (context.settings.get(AUTO_PULL_KEY, "false") or "") == "true"


def set_auto_pull(context: PluginContext, value: bool) -> None:
    context.settings.set(AUTO_PULL_KEY, "true" if value else "false")


def idle_delay_s(context: PluginContext) -> int:
    """Seconds a file must stay unchanged before Auto mode sends it (120 by default)."""
    raw = context.settings.get(IDLE_DELAY_KEY, str(DEFAULT_IDLE_DELAY_S)) or ""
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_IDLE_DELAY_S
    return min(MAX_IDLE_DELAY_S, max(0, value))


def set_idle_delay(context: PluginContext, seconds: int) -> None:
    if not 0 <= seconds <= MAX_IDLE_DELAY_S:
        raise ValueError(f"The idle delay must be between 0 and {MAX_IDLE_DELAY_S} seconds.")
    context.settings.set(IDLE_DELAY_KEY, str(seconds))


@dataclass(frozen=True)
class PassResult:
    """What one pass did: the detection, and the run when it sent anything."""

    detected: DetectReport
    queued: QueueReport | None


def pass_sentence(result: PassResult) -> str:
    """The sentence a visible pass ends with: what was sent, and what still waits."""
    queued = result.queued
    if queued is None:
        return "Changes of this computer queued for MTEE Remote."
    parts = [f"{_count(queued.sent, 'change')} sent to MTEE Remote"]
    if queued.blocked:
        parts.append(f"{queued.blocked} blocked")
    if queued.failed:
        parts.append(f"{queued.failed} failed")
    sentence = ", ".join(parts)
    if queued.stopped:
        sentence += f"; the server could not be reached, {queued.pending} still wait"
    return sentence + "."


def _count(value: int, noun: str) -> str:
    return f"{value:,} {noun}" if value == 1 else f"{value:,} {noun}s"


class SyncEngine(QObject):
    """Runs the push passes. ``changed`` tells the Settings page that the queue or state moved."""

    changed = Signal()

    def __init__(self, context: PluginContext, link: SyncLink) -> None:
        super().__init__()
        self._context = context
        self._link = link
        self._store = RemoteStore(context)
        self._busy = False
        self._again = False
        self._again_send = False
        self._closed = False
        self._job: JobId | None = None
        self._pull = AutoPull(context, self._store)
        self._fetch_job: JobId | None = None
        self._fetching = False
        self._backup_job: JobId | None = None
        self._backing_up = False
        self._timer = QTimer(self)
        self._timer.setInterval(PASS_INTERVAL_MS)
        self._timer.timeout.connect(self.request_pass)
        self._timer.timeout.connect(self.maintain_if_due)
        self._timer.start()
        self._maintaining = False

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def fetching(self) -> bool:
        """Whether a fetch of the server's changes runs now (Fetch, or one round of the pull)."""
        return self._fetching

    @property
    def pending(self) -> int:
        """The operations waiting to be sent."""
        return pending_count(self._store)

    # -- triggers -------------------------------------------------------------------------
    def on_state(self, state: str) -> None:
        """The connection changed: a pass runs when it becomes connected; the pull follows it."""
        if state == CONNECTED:
            self.request_pass()
            self.apply_auto_pull()
        else:
            self._pull.stop()

    def on_library_scanned(self, root: Path) -> None:
        """A library folder was scanned: its new or changed tracks are checked on the next pass."""
        del root
        self.request_pass()

    def request_pass(self) -> None:
        """Run a pass now, in the mode of the settings: Auto sends, Manual only queues."""
        self._start(send=None)

    def apply_pending(self) -> None:
        """Send what is queued now, whatever the mode (the Apply button)."""
        if self._link.state != CONNECTED:
            self._context.notify("Connect to the server first.")
            return
        if not self._first_match_done():
            self._context.notify("Finish the first match first, in Settings > Remote.")
            return
        self._start(send=True)

    def retry_failed(self) -> None:
        """Queue the failed operations again and send them now (the Retry button)."""
        count = retry_failed(self._store)
        self.changed.emit()
        if count and self._link.state == CONNECTED and self._first_match_done():
            self._start(send=True)
        elif count:
            self._context.notify("Queued again; they are sent once the server is connected.")

    def apply_auto_pull(self) -> None:
        """Start the pull loop when Auto pull is on and the device is connected; else stop it."""
        client = self._link.client()
        wanted = (
            client is not None
            and self._link.state == CONNECTED
            and auto_pull_on(self._context)
            and self._first_match_done()
        )
        if client is None or not wanted:
            self._pull.stop()
            return
        self._pull.start(client)

    def fetch_now(self) -> None:
        """Fetch the changes of the server now (the Fetch button), in a job."""
        if self._closed:
            return
        if self._link.state != CONNECTED:
            self._context.notify("Connect to the server first.")
            return
        if not self._first_match_done():
            self._context.notify("Finish the first match first, in Settings > Remote.")
            return
        if self._fetching:
            self._context.notify("A fetch of the server is already running.")
            return
        client = self._link.client()
        if client is None:
            return
        self._fetching = True
        self.changed.emit()
        self._fetch_job = submit(
            self._context,
            "Fetching changes from MTEE Remote",
            lambda job: fetch_once(self._context, self._store, client, job),
            self._on_fetched,
            summary=FetchResult.summary,
        )

    def shutdown(self) -> None:
        """Stop the timer, the pull loop and the jobs that run. Called when the plugin unloads."""
        self._closed = True
        self._timer.stop()
        self._pull.stop()
        if self._job is not None:
            self._context.jobs.cancel(self._job)
            self._job = None
        if self._fetch_job is not None:
            self._context.jobs.cancel(self._fetch_job)
            self._fetch_job = None
        if self._backup_job is not None:
            self._context.jobs.cancel(self._backup_job)
            self._backup_job = None

    # -- one pass -------------------------------------------------------------------------
    def _start(self, send: bool | None) -> None:
        if self._closed or self._link.state != CONNECTED or not self._first_match_done():
            return
        if self._busy:
            self._again = True
            self._again_send = self._again_send or send is True
            return
        client = self._link.client()
        if client is None:
            return
        will_send = sync_mode(self._context) == AUTO if send is None else send
        idle = idle_delay_s(self._context)
        visible = will_send and self.pending > 0
        self._busy = True
        self.changed.emit()
        self._job = submit(
            self._context,
            "Syncing with MTEE Remote",
            lambda job: self._work(client, will_send, idle, job),
            self._on_done,
            visible=visible,
            summary=pass_sentence,
        )

    def _work(self, client: RemoteClient, send: bool, idle: int, job: JobContext) -> PassResult:
        """The pass itself, on a job thread: link the downloads, detect, then send in Auto mode."""
        link_pending_imports(self._context, self._store, job)
        refresh_server_only(self._context, self._store)
        detected = detect_changes(
            self._context, self._store, idle_delay_s=idle, now=time.time(), job=job
        )
        if not send:
            return PassResult(detected, None)
        queued = run_queue(self._context, self._store, client, job, on_progress=self._progress)
        # The records (play log, playlists, track data, settings) follow the files; their errors are
        # logged inside and never stop the file sync (plan 126.7).
        push_records(self._context, self._store, client)
        return PassResult(detected, queued)

    def _progress(self, done: int, total: int) -> None:
        """Show ``Syncing N of M`` on the header icon. Thread-safe: queued to the GUI."""
        self._context.status_item.update(
            f"Syncing {done + 1} of {total}",
            "neutral",
            progress=(done + 1) / total,
            tooltip="Sending the changes of this computer to MTEE Remote.",
            icon=STATUS_ICON,
        )

    def _on_done(self, result: PassResult | None, error: BaseException | None) -> None:
        self._busy = False
        self._job = None
        if self._closed:
            return
        if error is not None and not isinstance(error, NetworkError):
            self._context.log.warning("The sync pass failed: %s", error)
        # The header icon showed the progress of this pass: the connection state comes back.
        self._link.refresh_status()
        self._context.availability_changed(None)
        self.changed.emit()
        self._maybe_backup()
        if self._again:
            send = True if self._again_send else None
            self._again = False
            self._again_send = False
            self._start(send)

    def maintain_if_due(self) -> None:
        """Trim the queue, the log and the hash cache once a day, in a hidden job."""
        if self._closed or self._maintaining or not maintenance.is_due(self._context):
            return
        self._maintaining = True
        submit(
            self._context,
            "Tidying the MTEE Remote tables",
            lambda job: maintenance.run(self._context, self._store, job),
            self._on_maintained,
            visible=False,
        )

    def _on_maintained(self, result: object, error: BaseException | None) -> None:
        del result
        self._maintaining = False
        if error is not None and not isinstance(error, JobCancelledError):
            self._context.log.warning("The housekeeping of the Remote tables failed: %s", error)

    def _maybe_backup(self) -> None:
        """Make the automatic backup when the schedule says it is due (plan 126.8), in a job.

        Checked after every pass, so it is due within a minute of the time. Nothing runs when the
        plugin is not connected or a backup already runs.
        """
        if self._closed or self._backing_up or self._link.state != CONNECTED:
            return
        client = self._link.client()
        if client is None or not is_due(self._context):
            return
        self._backing_up = True
        self._backup_job = submit(
            self._context,
            "Backing up the database to MTEE Remote",
            lambda job: run_automatic(self._context, client, job),
            self._on_backed_up,
            summary=lambda _result: "The automatic backup of the database is on the server.",
        )

    def _on_backed_up(self, result: None, error: BaseException | None) -> None:
        self._backing_up = False
        self._backup_job = None
        if self._closed:
            return
        if error is not None and not isinstance(error, (NetworkError, JobCancelledError)):
            self._context.log.warning("The automatic backup failed: %s", error)
        self.changed.emit()

    def _on_fetched(self, result: FetchResult | None, error: BaseException | None) -> None:
        self._fetching = False
        self._fetch_job = None
        if self._closed:
            return
        # The job ends with its sentence (the result, or the readable error) in the
        # notifications of the header: nothing more is announced here.
        del result, error
        self._context.availability_changed(None)
        self.changed.emit()

    def _first_match_done(self) -> bool:
        return self._context.settings.get(DONE_SETTING, "") == "true"
