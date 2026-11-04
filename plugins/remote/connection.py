"""The connection to MTEE Remote: sign in, sign out, the check of the link and the status item.

The manager lives on the graphical thread. Every call to the server runs in a job of
``context.jobs``; the job hands its result back with ``context.run_on_gui``, and only the
graphical thread changes the state. The password is passed to the job in a cell that the job
empties before it calls the server; it is never stored, logged or written to the settings.
"""

from __future__ import annotations

import contextlib
import platform
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, TypeVar
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QTimer, Signal

from mtee.plugins.api import JobContext, JobId, PluginContext

from .client import ApiError, NetworkError, RemoteClient
from .tasks import result_summary
from .tokens import TokenError, delete_token, load_token, save_token, token_exists

STATES = ("disconnected", "connecting", "connected", "offline", "error")
CHECK_INTERVAL_MS = 60_000
# Seconds to wait before the next check after 1, 2, then 3 or more failed checks.
RETRY_DELAYS = (60.0, 120.0, 300.0)
SETTING_KEYS = ("server_url", "username", "device_id", "device_name")
SIGNED_OUT_NOTICE = "This computer was signed out of the server."
BUSY_NOTICE = "Wait for the current operation to finish, then try again."
ALREADY_NOTICE = "This computer is already connected. Disconnect first."
OFFLINE_TOOLTIP = "The server cannot be reached. MTEE tries again by itself."
NOT_CONNECTED = "Not connected."

T = TypeVar("T")


@dataclass(frozen=True)
class _Session:
    """What a sign-in gives the graphical thread."""

    url: str
    username: str
    device_id: str
    device_name: str
    token: str
    version: str = ""
    devices: tuple[dict[str, Any], ...] = ()
    offline: str = ""  # set when the device exists but the server could not be read after it


@dataclass(frozen=True)
class _Check:
    """What a check of the link gives the graphical thread.

    ``kind`` is ``connected``, ``offline``, ``signed_out``, ``none`` (no token to check) or
    ``failed`` (the server refused for another reason; ``message`` says why).
    """

    kind: str
    token: str | None = None
    version: str = ""
    devices: tuple[dict[str, Any], ...] = ()
    message: str = ""


class ConnectionManager(QObject):
    """The state of the link to the server, and the operations that change it."""

    # The new state, one of STATES.
    stateChanged = Signal(str)  # noqa: N815
    changed = Signal()  # something the settings page shows has changed

    def __init__(self, context: PluginContext) -> None:
        super().__init__()
        self._context = context
        self._state = "disconnected"
        self._state_text = NOT_CONNECTED
        self._token: str | None = None
        self._server_url = ""
        self._username = ""
        self._device_id = ""
        self._device_name = ""
        self._server_version = ""
        self._devices: list[dict[str, Any]] = []
        self._busy = 0
        self._jobs: set[JobId] = set()
        self._failures = 0
        self._next_check = 0.0
        self._closed = False
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._open_conflicts: Callable[[], int] = lambda: 0

    def set_open_conflicts(self, count: Callable[[], int]) -> None:
        """The function that counts the conflicts waiting for the person (the status shows it)."""
        self._open_conflicts = count

    # -- what the page and the status item read -------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def state_text(self) -> str:
        return self._state_text

    @property
    def signed_in(self) -> bool:
        """Whether a device token is held, so that the device exists on the server."""
        return self._token is not None

    @property
    def busy(self) -> bool:
        return self._busy > 0

    def client(self) -> RemoteClient | None:
        """A client for the server with this device's token, or None when no device is held."""
        if self._token is None or not self._server_url:
            return None
        return RemoteClient(self._server_url, self._token)

    @property
    def server_url(self) -> str:
        return self._server_url

    @property
    def user_name(self) -> str:
        return self._username

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def device_name(self) -> str:
        """The name of this computer on the server, or the one for the next connection."""
        return self._device_name or platform.node()

    @property
    def server_version(self) -> str:
        return self._server_version

    @property
    def devices(self) -> list[dict[str, Any]]:
        """The devices of the account as the server listed them."""
        return list(self._devices)

    # -- life cycle ------------------------------------------------------------------------
    def start(self) -> None:
        """Read the saved connection; when a token is stored, check it in a job."""
        self._server_url = self._setting("server_url")
        self._username = self._setting("username")
        self._device_id = self._setting("device_id")
        self._device_name = self._setting("device_name")
        if not token_exists(self._context.data_dir):
            self._set_state("disconnected", NOT_CONNECTED)
            return
        if not self._server_url:
            self._forget_token()
            self._set_state("disconnected", NOT_CONNECTED)
            return
        self._set_state("connecting", "Checking the connection to the server…")
        self._start_check(token=None, label="Checking MTEE Remote", visible=False)

    def shutdown(self) -> None:
        """Stop the timer and cancel the jobs that run. Called when the plugin unloads."""
        self._closed = True
        self._timer.stop()
        for job_id in list(self._jobs):
            self._context.jobs.cancel(job_id)
        self._jobs.clear()

    # -- user operations -------------------------------------------------------------------
    # The name is the one the spec gives; it overrides the static QObject.connect on purpose.
    def connect(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, url: str, username: str, password: str, device_name: str
    ) -> None:
        """Sign in to ``url`` and register this computer as a device, in a job."""
        if self.signed_in:
            self._notify(ALREADY_NOTICE)
            return
        if self.busy:
            self._notify(BUSY_NOTICE)
            return
        user = username.strip()
        if not user or not password:
            self._notify("Enter the user name and the password to connect.")
            return
        try:
            client = RemoteClient(url)
        except ValueError as error:
            self._set_state("error", str(error))
            return
        name = device_name.strip() or platform.node()
        # The password moves into this cell: the job takes it out, and the cell is left empty.
        secret: dict[str, str] = {"password": password}
        data_dir = self._context.data_dir
        self._set_state("connecting", "Connecting to the server…")
        self._run(
            "Connecting to MTEE Remote",
            lambda: _connect_work(client.base_url, user, secret, name, data_dir),
            self._on_connected,
            summary=connected_sentence,
        )

    # Likewise: the name is the spec's, and it overrides the static QObject.disconnect.
    def disconnect(self) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Revoke this device on the server, delete the token and clear the settings."""
        if self.busy:
            self._notify(BUSY_NOTICE)
            return
        token = self._token
        if token is None:
            self._clear_settings()
            self._set_state("disconnected", NOT_CONNECTED)
            return
        url = self._server_url
        data_dir = self._context.data_dir
        self._run(
            "Signing out of MTEE Remote",
            lambda: _disconnect_work(url, token, data_dir),
            self._on_disconnected,
            summary=lambda message: message or "This computer is signed out of MTEE Remote.",
        )

    def check_now(self) -> None:
        """Check the link in a job now; the timer goes through the backoff first."""
        if self._token is None or self.busy:
            return
        self._start_check(token=self._token, label="Checking MTEE Remote", visible=False)

    def refresh_status(self) -> None:
        """Show the current state in the status item again (a sync pass may have changed it)."""
        self._show_status()

    def refresh_devices(self) -> None:
        """Read the devices of the account in a job."""
        if self._token is None or self.busy:
            return
        self._start_check(
            token=self._token, label="Reading the devices", visible=False, health=False
        )

    def revoke(self, device_id: str) -> None:
        """Revoke another device of the account. This computer signs out with disconnect."""
        if self._token is None:
            self._notify("Connect to the server first.")
            return
        if self.busy:
            self._notify(BUSY_NOTICE)
            return
        if device_id == self._device_id:
            self._notify("To sign this computer out, use Disconnect.")
            return
        self._start_check(
            token=self._token,
            label="Revoking a device",
            visible=True,
            health=False,
            action=lambda client: client.revoke_device(device_id),
        )

    def set_device_name(self, name: str) -> None:
        """Keep the name for the next connection. Once connected, the name is fixed."""
        value = name.strip()
        if not value:
            return
        if self._token is not None:
            self._notify("To give this computer another name, disconnect and connect again.")
            return
        self._device_name = value
        self._context.settings.set("device_name", value)
        self.changed.emit()

    # -- results of the jobs (graphical thread) --------------------------------------------
    def _on_connected(self, session: _Session | None, error: BaseException | None) -> None:
        if error is not None:
            if isinstance(error, NetworkError):
                self._set_state("offline", str(error))
            else:
                self._set_state("error", str(error) or type(error).__name__)
            return
        assert session is not None
        self._token = session.token
        self._server_url = session.url
        self._username = session.username
        self._device_id = session.device_id
        self._device_name = session.device_name
        self._context.settings.set("server_url", session.url)
        self._context.settings.set("username", session.username)
        self._context.settings.set("device_id", session.device_id)
        self._context.settings.set("device_name", session.device_name)
        self._server_version = session.version
        self._devices = list(session.devices)
        if session.offline:
            self._schedule_retry()
            self._set_state("offline", session.offline)
            return
        self._failures = 0
        self._next_check = 0.0
        self._set_state("connected", self._connected_text())

    def _on_disconnected(self, message: str | None, error: BaseException | None) -> None:
        # The job ends with the sentence of ``_disconnect_work``, or the readable error.
        del message, error
        self._forget_session()
        self._clear_settings()
        self._set_state("disconnected", NOT_CONNECTED)

    def _on_check(self, check: _Check | None, error: BaseException | None) -> None:
        if error is not None:
            self._set_state("error", str(error) or type(error).__name__)
            return
        assert check is not None
        if check.kind == "connected":
            self._token = check.token
            self._server_version = check.version or self._server_version
            self._devices = list(check.devices)
            self._failures = 0
            self._next_check = 0.0
            self._set_state("connected", self._connected_text())
        elif check.kind == "offline":
            self._token = check.token
            self._schedule_retry()
            self._set_state("offline", check.message)
        elif check.kind == "signed_out":
            self._forget_session()
            self._set_state("disconnected", NOT_CONNECTED)
            self._notify(SIGNED_OUT_NOTICE)
        elif check.kind == "none":
            self._forget_session()
            self._set_state("disconnected", NOT_CONNECTED)
            if check.message:
                self._notify(check.message)
        else:  # failed: the server refused, and the token is still good
            if check.token is not None:
                self._token = check.token
            if self._state == "connecting":
                self._set_state("error", check.message)
            else:
                self._notify(check.message)
                self.changed.emit()

    # -- internals -------------------------------------------------------------------------
    def _start_check(
        self,
        *,
        token: str | None,
        label: str,
        visible: bool,
        health: bool = True,
        action: Callable[[RemoteClient], None] | None = None,
    ) -> None:
        url = self._server_url
        data_dir = self._context.data_dir
        self._run(
            label,
            lambda: _check_work(url, data_dir, token, health, action),
            self._on_check,
            visible=visible,
        )

    def _run(
        self,
        label: str,
        work: Callable[[], T],
        done: Callable[[T | None, BaseException | None], None],
        *,
        visible: bool = True,
        summary: Callable[[T], str] | None = None,
    ) -> None:
        """Submit ``work`` as a job; ``done`` runs on the graphical thread with its result.

        ``summary(result)`` is the sentence a visible job ends with (see ``tasks.submit``).
        """
        self._busy += 1
        self.changed.emit()
        holder: list[JobId] = []
        results: list[T] = []

        def finish(result: T | None, error: BaseException | None) -> None:
            self._busy -= 1
            if holder:
                self._jobs.discard(holder[0])
            if not self._closed:
                done(result, error)
            self.changed.emit()

        def task(_job: JobContext) -> None:
            try:
                result = work()
            except BaseException as error:
                failure = error
                self._context.run_on_gui(lambda: finish(None, failure))
                raise  # the Tasks window shows the readable sentence of the error
            results.append(result)
            self._context.run_on_gui(lambda: finish(result, None))

        if summary is None:
            job_id = self._context.jobs.submit(task, label=label, visible=visible)
        else:
            job_id = self._context.jobs.submit(
                task, label=label, visible=visible, summary=result_summary(results, summary)
            )
        holder.append(job_id)
        self._jobs.add(job_id)

    def _tick(self) -> None:
        """The timer: check the link, unless the backoff after a failure says to wait."""
        if self._token is None or self.busy:
            return
        if monotonic() < self._next_check:
            return
        self.check_now()

    def _schedule_retry(self) -> None:
        self._failures += 1
        delay = RETRY_DELAYS[min(self._failures, len(RETRY_DELAYS)) - 1]
        self._next_check = monotonic() + delay

    def _set_state(self, state: str, text: str) -> None:
        if state not in STATES:
            raise ValueError(f"Unknown state {state}")
        changed_state = state != self._state
        self._state = state
        self._state_text = text
        if self._token is not None and not self._timer.isActive():
            self._timer.start()
        elif self._token is None and self._timer.isActive():
            self._timer.stop()
        self._show_status()
        if changed_state:
            self.stateChanged.emit(state)
        self.changed.emit()

    def _show_status(self) -> None:
        status = self._context.status_item
        waiting = self._open_conflicts()
        if waiting:
            # Conflicts wait for the person: they take the status text, whatever the link state.
            status.update(
                f"{waiting} conflict{'' if waiting == 1 else 's'}",
                "warning",
                tooltip="Open the Remote activity to resolve them.",
                icon="alert",
            )
            return
        if self._state == "connected":
            status.update(
                "Connected",
                "neutral",
                tooltip=f"Connected to {self._server_url} as {self._username}.",
                icon="cloud",
            )
        elif self._state == "offline":
            status.update("Offline", "warning", tooltip=OFFLINE_TOOLTIP, icon="cloud-off")
        elif self._state == "connecting":
            status.update("Connecting…", "neutral", tooltip=self._state_text, icon="cloud")
        else:
            status.clear()

    def _connected_text(self) -> str:
        if self._server_version:
            return f"Connected. Server {self._server_version}."
        return "Connected."

    def _forget_token(self) -> None:
        self._token = None
        with contextlib.suppress(TokenError, OSError):
            delete_token(self._context.data_dir)

    def _forget_session(self) -> None:
        """Drop the token and this device, keeping the address and the user name."""
        self._forget_token()
        self._device_id = ""
        self._context.settings.delete("device_id")
        self._devices = []
        self._server_version = ""
        self._failures = 0
        self._next_check = 0.0

    def _clear_settings(self) -> None:
        for key in SETTING_KEYS:
            self._context.settings.delete(key)
        self._server_url = ""
        self._username = ""
        self._device_id = ""
        self._device_name = ""

    def _setting(self, key: str) -> str:
        return self._context.settings.get(key, "") or ""

    def _notify(self, text: str) -> None:
        self._context.notify(text)


def _connect_work(
    url: str, username: str, secret: dict[str, str], device_name: str, data_dir: Path
) -> _Session:
    """Sign in, save the token, then read the server. Runs on a job thread."""
    password = secret.pop("password", "")
    anonymous = RemoteClient(url)
    device_id, token = anonymous.login(username, password, device_name)
    del password
    try:
        save_token(data_dir, token)
    except BaseException:
        _discard(url, token, data_dir)
        raise
    authed = RemoteClient(url, token)
    try:
        version = str(anonymous.health().get("version", ""))
        devices = tuple(authed.devices())
    except NetworkError as error:
        # The device exists and its token is saved: the link is kept, and checked again later.
        return _Session(url, username, device_id, device_name, token, offline=str(error))
    except BaseException:
        _discard(url, token, data_dir)
        raise
    return _Session(url, username, device_id, device_name, token, version, devices)


def _discard(url: str, token: str, data_dir: Path) -> None:
    """Undo a sign-in that did not finish: revoke the device and delete the token."""
    with contextlib.suppress(Exception):
        RemoteClient(url, token).logout()
    _discard_local(data_dir)


def connected_sentence(session: _Session) -> str:
    """The sentence the connect job ends with."""
    host = urlsplit(session.url).hostname or session.url
    if session.offline:
        return f"Signed in to {host} as {session.device_name}, but the server is offline now."
    return f"Connected to {host} as {session.device_name}."


def _disconnect_work(url: str, token: str, data_dir: Path) -> str:
    """Revoke this device and delete the token. Returns the sentence to show, or an empty one."""
    try:
        RemoteClient(url, token).logout()
        return ""
    except ApiError as error:
        if error.status == 401:
            return ""  # the device was already revoked elsewhere
        return (
            "Signed out on this computer. The server did not confirm it: "
            f"{error.message} Remove this computer from the device list if it is still there."
        )
    except NetworkError:
        return (
            "Signed out on this computer. The server could not be reached, so this device is "
            "still listed there: revoke it from the device list when the server is back."
        )
    finally:
        _discard_local(data_dir)


def _check_work(
    url: str,
    data_dir: Path,
    token: str | None,
    health: bool,
    action: Callable[[RemoteClient], None] | None,
) -> _Check:
    """Check the link, run ``action`` and read the devices. Runs on a job thread."""
    if token is None:
        try:
            token = load_token(data_dir)
        except TokenError as error:
            _discard_local(data_dir)
            return _Check("none", message=str(error))
        if token is None:
            return _Check("none")
    client = RemoteClient(url, token)
    try:
        version = ""
        if health:
            version = str(RemoteClient(url).health().get("version", ""))
        if action is not None:
            action(client)
        devices = tuple(client.devices())
    except NetworkError as error:
        return _Check("offline", token=token, message=str(error))
    except ApiError as error:
        if error.status == 401:
            _discard_local(data_dir)
            return _Check("signed_out")
        return _Check("failed", token=token, message=error.message)
    return _Check("connected", token=token, version=version, devices=devices)


def _discard_local(data_dir: Path) -> None:
    """Delete the stored token; a failure here is not reported, the token is forgotten anyway."""
    with contextlib.suppress(Exception):
        delete_token(data_dir)
