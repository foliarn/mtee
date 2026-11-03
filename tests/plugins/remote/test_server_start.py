"""The test servers start on a port of their own, also when two starts run at the same time.

Two starts that pick the same port used to fail with ``WinError 10048`` in a parallel run. The
start now retries on a new port (see ``start_serving`` in ``conftest``), and ``free_port`` never
hands out a port twice in one process. Each test stops every server it started, and checks that
its process and its port are gone.
"""

from __future__ import annotations

import os
import secrets
import socket
import threading
import time
from pathlib import Path

import pytest
from tests.plugins.remote import conftest
from tests.plugins.remote.conftest import (
    ADMIN,
    ServerProcess,
    create_admin,
    find_uv,
    free_port,
    pid_exists,
    start_serving,
    stop_server,
    sync_server,
)


def _server_env(base: Path) -> dict[str, str]:
    """A fresh data folder, music folder and administrator for one server."""
    music = base / "music"
    (music / ADMIN).mkdir(parents=True)
    return {
        **os.environ,
        "MTEE_REMOTE_DATA": str(base / "data"),
        "MTEE_REMOTE_MUSIC": str(music),
        "MTEE_REMOTE_ADMIN_PASSWORD": secrets.token_urlsafe(18),
    }


def _port_accepts(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def _port_closes(port: int, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while _port_accepts(port):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.1)
    return True


def _port_of(url: str) -> int:
    return int(url.rsplit(":", 1)[1])


def test_free_port_never_hands_out_a_port_twice() -> None:
    ports = [free_port() for _ in range(50)]

    assert len(set(ports)) == len(ports)


def test_two_servers_started_at_once_each_run_on_their_own_port(tmp_path: Path) -> None:
    executable = sync_server(find_uv())
    bases = [tmp_path / "first", tmp_path / "second"]
    envs = [_server_env(base) for base in bases]
    for env in envs:
        create_admin(executable, env)
    barrier = threading.Barrier(2)
    started: list[tuple[ServerProcess, str] | None] = [None, None]
    errors: list[BaseException] = []

    def start(index: int) -> None:
        try:
            barrier.wait(timeout=30)
            started[index] = start_serving(executable, envs[index], bases[index])
        except BaseException as error:  # reported by the test, not lost in the thread
            errors.append(error)

    threads = [threading.Thread(target=start, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=300)
    servers = [item for item in started if item is not None]
    try:
        assert errors == []
        assert len(servers) == 2
        urls = [url for _, url in servers]
        assert urls[0] != urls[1]
        for _, url in servers:
            assert conftest._healthy(url)
    finally:
        for server, _ in servers:
            stop_server(server)

    for server, url in servers:
        assert not pid_exists(server.pid)
        assert _port_closes(_port_of(url))


def test_a_start_that_loses_its_port_is_retried_on_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = sync_server(find_uv())
    bases = [tmp_path / "first", tmp_path / "second"]
    envs = [_server_env(base) for base in bases]
    for env in envs:
        create_admin(executable, env)
    shared = free_port()
    real_free_port = conftest.free_port
    lock = threading.Lock()
    calls = 0

    def colliding_port() -> int:
        # The first two starts are given the same port, as two processes could be.
        nonlocal calls
        with lock:
            calls += 1
            if calls <= 2:
                return shared
        return real_free_port()

    monkeypatch.setattr(conftest, "free_port", colliding_port)
    barrier = threading.Barrier(2)
    started: list[tuple[ServerProcess, str] | None] = [None, None]
    errors: list[BaseException] = []

    def start(index: int) -> None:
        try:
            barrier.wait(timeout=30)
            started[index] = start_serving(executable, envs[index], bases[index])
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=start, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=300)
    servers = [item for item in started if item is not None]
    try:
        assert errors == []
        assert len(servers) == 2
        urls = [url for _, url in servers]
        assert urls[0] != urls[1]
        assert shared in [_port_of(url) for url in urls]
        for _, url in servers:
            assert conftest._healthy(url)
        # Exactly one start lost the shared port and had to try again on a new one.
        retried = [(base / "server-1.log").is_file() for base in bases]
        assert sorted(retried) == [False, True]
    finally:
        for server, _ in servers:
            stop_server(server)

    for server, url in servers:
        assert not pid_exists(server.pid)
        assert _port_closes(_port_of(url))
