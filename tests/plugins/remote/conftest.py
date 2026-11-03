"""Fixtures of the remote plugin tests: a real MTEE Remote server, started once per session.

The server is the project in ``server/``, run on ``127.0.0.1`` only. Its data and its music
folder are temporary, and its one administrator gets a generated password that only this
fixture knows. The tests are skipped when ``uv`` or the server project is missing.

The server is started from its virtual environment directly, not through ``uv run``: on Windows,
stopping a ``uv run`` parent left the server it had started running. The start and the stop are
the functions below, so that a test can check that the stop really ends the process.
"""

from __future__ import annotations

import atexit
import contextlib
import ctypes
import functools
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import pytest

import mtee.plugins

ROOT = Path(__file__).resolve().parents[3]
SERVER_DIR = ROOT / "server"
PLUGIN_DIR = ROOT / "plugins"
ADMIN = "admin"
START_TIMEOUT_S = 60.0
STOP_TIMEOUT_S = 10.0
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PROCESS_FLAGS = (
    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | _NO_WINDOW
    if sys.platform == "win32"
    else 0
)

_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

# The tests import ``mtee.plugins.remote`` by its package name, as the core does, so its folder
# is on the package path while the tests are collected. Each test takes it off again: the core
# adds the folder it is given, and a copy of the package left on the path would win over it.
if str(PLUGIN_DIR) not in mtee.plugins.__path__:
    mtee.plugins.__path__.append(str(PLUGIN_DIR))


@dataclass(frozen=True)
class RemoteServer:
    """A running server: its address, the administrator and the folders it uses."""

    url: str
    username: str
    password: str
    data_dir: Path
    music_dir: Path


@dataclass
class ServerProcess:
    """A server started by :func:`start_server`: its process, its log and its Job Object.

    ``job`` is the handle of a Windows Job Object that kills the process tree when its last
    handle closes, or ``None`` when no such job could be set up (or on other systems).
    """

    process: subprocess.Popen[bytes]
    log: BinaryIO
    job: int | None

    @property
    def pid(self) -> int:
        return self.process.pid


_RUNNING: list[ServerProcess] = []
_RUNNING_LOCK = threading.Lock()
_PORTS_LOCK = threading.Lock()
_PORTS_HANDED_OUT: set[int] = set()
START_RETRIES = 5


def free_port() -> int:
    """Return a port that nothing listens on at the moment, on 127.0.0.1.

    The port comes from the system (bind to port 0). A port this process already handed out is
    not handed out again, so two threads that start servers at once never get the same port.
    Another process can still take a port between this probe and the start; :func:`start_serving`
    covers that by retrying on a new port.
    """
    with _PORTS_LOCK:
        for _ in range(100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1", 0))
                port = int(probe.getsockname()[1])
            if port not in _PORTS_HANDED_OUT:
                _PORTS_HANDED_OUT.add(port)
                return port
    raise RuntimeError("No free port was found on 127.0.0.1.")


def find_uv() -> str:
    """Return the path of ``uv``; skip the tests when it or the server project is missing."""
    found = shutil.which("uv")
    if found is None or not (SERVER_DIR / "pyproject.toml").is_file():
        pytest.skip("The MTEE Remote server tests need uv and the server project in server/.")
    return found


def server_executable() -> Path:
    """Return the ``mtee-remote`` launcher of the server's virtual environment."""
    if sys.platform == "win32":
        return SERVER_DIR / ".venv" / "Scripts" / "mtee-remote.exe"
    return SERVER_DIR / ".venv" / "bin" / "mtee-remote"


def sync_server(uv: str) -> Path:
    """Install the server's locked dependencies (quietly) and return its launcher."""
    synced = subprocess.run(
        [uv, "sync", "--directory", str(SERVER_DIR), "--locked", "--quiet"],
        capture_output=True,
        timeout=600,
        creationflags=_NO_WINDOW,
        check=False,
    )
    if synced.returncode != 0:
        pytest.fail(
            f"uv sync of the server failed: {synced.stderr.decode(errors='replace')[-800:]}"
        )
    executable = server_executable()
    if not executable.is_file():
        pytest.fail(f"The server launcher is missing after uv sync: {executable}")
    return executable


def create_admin(executable: Path, env: Mapping[str, str]) -> None:
    """Create the administrator of the server (a short-lived command)."""
    created = subprocess.run(
        [str(executable), "create-admin", "--username", ADMIN],
        env=dict(env),
        capture_output=True,
        timeout=300,
        creationflags=_PROCESS_FLAGS,
        check=False,
    )
    if created.returncode != 0:
        pytest.fail(f"create-admin failed: {created.stderr.decode(errors='replace')[-800:]}")


@functools.cache
def _kernel32() -> Any:
    """The Windows kernel functions used to own and stop the server, with their types set."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(_ExtendedLimitInformation),
        ctypes.c_uint32,
    ]
    kernel.SetInformationJobObject.restype = ctypes.c_int
    kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.AssignProcessToJobObject.restype = ctypes.c_int
    kernel.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.TerminateJobObject.restype = ctypes.c_int
    kernel.QueryInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(_BasicAccountingInformation),
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel.QueryInformationJobObject.restype = ctypes.c_int
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel.GetExitCodeProcess.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    return kernel


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _BasicAccountingInformation(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_int64),
        ("TotalKernelTime", ctypes.c_int64),
        ("ThisPeriodTotalUserTime", ctypes.c_int64),
        ("ThisPeriodTotalKernelTime", ctypes.c_int64),
        ("TotalPageFaultCount", ctypes.c_uint32),
        ("TotalProcesses", ctypes.c_uint32),
        ("ActiveProcesses", ctypes.c_uint32),
        ("TotalTerminatedProcesses", ctypes.c_uint32),
    ]


def _end_job(job: int) -> None:
    """Terminate every process still in the job, wait until none is active, then close it.

    The launcher of the server can exit while the Python process it started keeps running (and
    keeps the port open). Ending the job reaches that process too; waiting for the job to be
    empty makes sure its sockets are gone when the stop returns.
    """
    kernel = _kernel32()
    kernel.TerminateJobObject(job, 1)
    deadline = time.monotonic() + STOP_TIMEOUT_S
    try:
        while True:
            info = _BasicAccountingInformation()
            queried = kernel.QueryInformationJobObject(
                job,
                _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                ctypes.pointer(info),
                ctypes.sizeof(info),
                None,
            )
            if not queried or info.ActiveProcesses == 0:
                return
            if time.monotonic() > deadline:
                raise RuntimeError("The MTEE Remote server processes did not end in 10 seconds.")
            time.sleep(0.05)
    finally:
        kernel.CloseHandle(job)


def _kill_on_close_job(pid: int) -> int | None:
    """Put process ``pid`` in a new Job Object that kills its processes when the job closes.

    Returns the job handle, which the caller keeps until the server is stopped, or ``None`` when
    the job could not be set up. Then the stop relies on the tree kill alone.
    """
    kernel = _kernel32()
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return None
    limits = _ExtendedLimitInformation()
    limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    process = kernel.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, 0, pid)
    assigned = False
    if process:
        assigned = bool(
            kernel.SetInformationJobObject(
                job,
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.pointer(limits),
                ctypes.sizeof(limits),
            )
        ) and bool(kernel.AssignProcessToJobObject(job, process))
        kernel.CloseHandle(process)
    if assigned:
        return int(job)
    kernel.CloseHandle(job)
    return None


def pid_exists(pid: int) -> bool:
    """Tell whether process ``pid`` still runs. It never signals the process."""
    if sys.platform == "win32":
        kernel = _kernel32()
        handle = kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_uint32()
            if not kernel.GetExitCodeProcess(handle, ctypes.pointer(code)):
                return True
            return code.value == _STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_server(
    executable: Path, args: Sequence[str], env: Mapping[str, str], log_path: Path
) -> ServerProcess:
    """Start ``executable`` with ``args`` as the process itself, with its output in ``log_path``.

    The process is registered so that an interpreter exit stops it too (see :func:`stop_server`).
    """
    log = log_path.open("wb")
    try:
        process = subprocess.Popen(
            [str(executable), *args],
            env=dict(env),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=_PROCESS_FLAGS,
        )
    except BaseException:
        log.close()
        raise
    job = _kill_on_close_job(process.pid) if sys.platform == "win32" else None
    server = ServerProcess(process, log, job)
    with _RUNNING_LOCK:
        _RUNNING.append(server)
    return server


def stop_server(server: ServerProcess) -> None:
    """Stop the server and everything it started: terminate, wait, then kill the tree.

    Safe to call twice. The process is only ever the one :func:`start_server` made.
    """
    with _RUNNING_LOCK:
        _RUNNING[:] = [running for running in _RUNNING if running is not server]
    process = server.process
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                    capture_output=True,
                    timeout=60,
                    creationflags=_NO_WINDOW,
                    check=False,
                )
            else:
                process.kill()
            process.wait(timeout=STOP_TIMEOUT_S)
    # Ending the job last stops whatever of its tree is still running, then the log is closed.
    if server.job is not None:
        job, server.job = server.job, None
        _end_job(job)
    server.log.close()


def _stop_leftovers() -> None:
    """At interpreter exit, stop the servers a test session did not stop."""
    with _RUNNING_LOCK:
        running = list(_RUNNING)
    for server in running:
        with contextlib.suppress(Exception):
            stop_server(server)


atexit.register(_stop_leftovers)


def wait_until_healthy(server: ServerProcess, url: str) -> None:
    """Wait until the server answers ``/health``; fail if it exits or does not answer in time."""
    deadline = time.monotonic() + START_TIMEOUT_S
    while not _healthy(url):
        if server.process.poll() is not None:
            pytest.fail("The MTEE Remote server stopped while it was starting.")
        if time.monotonic() > deadline:
            pytest.fail("The MTEE Remote server did not answer /health in 60 seconds.")
        time.sleep(0.2)


def start_serving(
    executable: Path, env: Mapping[str, str], base: Path, *, retries: int = START_RETRIES
) -> tuple[ServerProcess, str]:
    """Start ``serve`` on a free port and wait until it runs there; return the process and URL.

    A start can lose its port to another process between :func:`free_port` and the bind (on
    Windows the second bind fails with ``WinError 10048`` and the server exits). Such a start is
    stopped and tried again on a new port, up to ``retries`` more times. The log of each attempt
    is ``base/server-<attempt>.log``.
    """
    reasons: list[str] = []
    for attempt in range(retries + 1):
        port = free_port()
        url = f"http://127.0.0.1:{port}"
        log_path = base / f"server-{attempt}.log"
        server = start_server(
            executable,
            ["serve", "--host", "127.0.0.1", "--port", str(port)],
            env,
            log_path,
        )
        reason = _await_started(server, url, log_path)
        if reason is None:
            return server, url
        stop_server(server)
        reasons.append(f"port {port}: {reason}")
    pytest.fail(
        f"The MTEE Remote server did not start after {retries + 1} attempts ({'; '.join(reasons)})."
    )


def _await_started(server: ServerProcess, url: str, log_path: Path) -> str | None:
    """Wait until this server process serves ``url``; return why it did not, or ``None``.

    The health answer alone is not enough: a server that lost the port answers with the
    server that won it. So the server must also log that it bound ``url`` itself (uvicorn logs
    ``Uvicorn running on <url>`` after its bind succeeds; a failed bind logs an error and exits).
    """
    deadline = time.monotonic() + START_TIMEOUT_S
    while True:
        if _bound_here(log_path, url) and _healthy(url):
            return None
        code = server.process.poll()
        if code is not None:
            return f"the server exited with code {code} while it was starting"
        if time.monotonic() > deadline:
            return f"it did not answer /health in {START_TIMEOUT_S:.0f} seconds"
        time.sleep(0.2)


def _bound_here(log_path: Path, url: str) -> bool:
    """Return whether the server that writes ``log_path`` logged that it runs on ``url``."""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return f"Uvicorn running on {url} " in text


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=2) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, OSError):
        return False


def _call(
    url: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> Any:
    """Call the server with the standard library only (no import of the plugin)."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(f"{url}{path}", data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


@pytest.fixture(scope="session")
def remote_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RemoteServer]:
    uv = find_uv()
    base = tmp_path_factory.mktemp("remote-server")
    data_dir = base / "data"
    music_dir = base / "music"
    (music_dir / ADMIN).mkdir(parents=True)
    password = secrets.token_urlsafe(18)
    env = {
        **os.environ,
        "MTEE_REMOTE_DATA": str(data_dir),
        "MTEE_REMOTE_MUSIC": str(music_dir),
        "MTEE_REMOTE_ADMIN_PASSWORD": password,
    }
    # The server computes the audio hash with the same ffmpeg as the plugin (plan 126.2): the
    # pinned runtime of the repository, unless the environment names another one.
    pinned_ffmpeg = ROOT / "vendor" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if "MTEE_REMOTE_FFMPEG" not in os.environ and pinned_ffmpeg.is_file():
        env["MTEE_REMOTE_FFMPEG"] = str(pinned_ffmpeg)
    executable = sync_server(uv)
    create_admin(executable, env)

    server, url = start_serving(executable, env, base)
    try:
        yield RemoteServer(url, ADMIN, password, data_dir, music_dir)
    finally:
        stop_server(server)


@pytest.fixture(autouse=True)
def fresh_plugin_import() -> Iterator[None]:
    """Give each test the plugin as the core imports it: from its own folder, once.

    The test modules import the plugin when they are collected. Without this, the contract
    tests would find the package already loaded, skip its factory module, and the copy of the
    plugin they stage would never run. So each test takes the plugin folder off the package
    path and drops the plugin modules; a test that needs the plugin adds the folder again.
    """
    for name in [name for name in sys.modules if name.startswith("mtee.plugins.remote")]:
        del sys.modules[name]
    while str(PLUGIN_DIR) in mtee.plugins.__path__:
        mtee.plugins.__path__.remove(str(PLUGIN_DIR))
    yield


@pytest.fixture
def make_user(remote_server: RemoteServer) -> Iterator[Callable[[], tuple[str, str]]]:
    """Create a fresh, non-admin user through the admin API; return ``(name, password)``.

    The server locks a user name after a few failed sign-ins and keeps the count for the whole
    session. A test that signs in with a wrong password gets its own user, so the lockout never
    leaks into another test.
    """
    session = _call(
        remote_server.url,
        "POST",
        "/api/v1/auth/login",
        body={
            "username": remote_server.username,
            "password": remote_server.password,
            "device_name": "Test: admin",
            "device_kind": "desktop",
        },
    )
    token = str(session["token"])

    def create() -> tuple[str, str]:
        username = "tester" + secrets.token_hex(4)
        password = secrets.token_urlsafe(18)
        _call(
            remote_server.url,
            "POST",
            "/api/v1/admin/users",
            body={"username": username, "password": password},
            token=token,
        )
        return username, password

    yield create
    with contextlib.suppress(Exception):
        _call(remote_server.url, "POST", "/api/v1/auth/logout", token=token)
