"""The server helpers stop the server process they started, and its port with it.

The session fixture starts the server with the same helpers. Without this stop, every test
session left a server running (165 were found once), so the check is on the process and on the
port: both must be gone after the stop.
"""

from __future__ import annotations

import os
import secrets
import socket
import time
from pathlib import Path

from tests.plugins.remote.conftest import (
    ADMIN,
    create_admin,
    find_uv,
    free_port,
    pid_exists,
    start_server,
    stop_server,
    sync_server,
    wait_until_healthy,
)


def _port_accepts(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def _port_closes(port: int, timeout_s: float = 5.0) -> bool:
    """Wait for the port to stop accepting connections.

    Windows releases a listening socket a moment after its process has ended, so the port is
    polled for a few seconds instead of checked once. The process itself is checked at once.
    """
    deadline = time.monotonic() + timeout_s
    while _port_accepts(port):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.1)
    return True


def test_server_fixture_stops_its_process(tmp_path: Path) -> None:
    executable = sync_server(find_uv())
    data_dir = tmp_path / "data"
    music_dir = tmp_path / "music"
    (music_dir / ADMIN).mkdir(parents=True)
    env = {
        **os.environ,
        "MTEE_REMOTE_DATA": str(data_dir),
        "MTEE_REMOTE_MUSIC": str(music_dir),
        "MTEE_REMOTE_ADMIN_PASSWORD": secrets.token_urlsafe(18),
    }
    create_admin(executable, env)
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    server = start_server(
        executable,
        ["serve", "--host", "127.0.0.1", "--port", str(port)],
        env,
        tmp_path / "server.log",
    )
    try:
        wait_until_healthy(server, url)
        assert pid_exists(server.pid)
        assert _port_accepts(port)
    finally:
        stop_server(server)

    assert not pid_exists(server.pid)
    assert _port_closes(port)
