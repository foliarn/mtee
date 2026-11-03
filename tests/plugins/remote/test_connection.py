"""The connection manager against a real MTEE Remote server (plan 126.1).

The context is the real one of ``PluginHost``, over a temporary database and the real job
service; only the status item and the message line are recorded, so the tests can read them.
The checks of the link are called directly, not waited for (the timer runs every 60 seconds).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mtee.plugins.remote import tokens  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.client import RemoteClient  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.connection import (  # pyright: ignore[reportMissingImports]
    ALREADY_NOTICE,
    SIGNED_OUT_NOTICE,
    ConnectionManager,
)
from mtee.plugins.remote.manifest import MANIFEST  # pyright: ignore[reportMissingImports]
from pytestqt.qtbot import QtBot
from tests.plugins.remote.conftest import RemoteServer, free_port

from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import PluginContext, Tone
from mtee.plugins.context import PluginHost
from mtee.services.jobs import JobService

WAIT_MS = 30_000


class StatusRecorder:
    """Stands in for the status item: keeps each call, for the tests to read."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def update(
        self,
        text: str,
        tone: Tone = "neutral",
        progress: float | None = None,
        tooltip: str = "",
        icon: str | None = None,
    ) -> None:
        self.calls.append(("update", text, tone, icon))

    def clear(self) -> None:
        self.calls.append(("clear",))

    @property
    def last(self) -> tuple[object, ...]:
        return self.calls[-1]


class Env:
    """One temporary profile: its context, what it recorded, and the managers it made."""

    def __init__(self, base: Path, context: PluginContext, status: StatusRecorder) -> None:
        self.base = base
        self.context = context
        self.status = status
        self.notices: list[str] = []
        self._managers: list[ConnectionManager] = []

    def manager(self) -> ConnectionManager:
        manager = ConnectionManager(self._context_for_manager())
        self._managers.append(manager)
        return manager

    def _context_for_manager(self) -> PluginContext:
        return dataclasses.replace(
            self.context, status_item=self.status, notify=self.notices.append
        )

    def close(self) -> None:
        for manager in self._managers:
            manager.shutdown()


@pytest.fixture
def env(qtbot: QtBot, tmp_path: Path) -> Iterator[Env]:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    host = PluginHost(
        data_dir=tmp_path,
        database=database,
        settings=SettingsRepository(database),
        library=MagicMock(),
        playlists=MagicMock(),
        jobs=JobService(),
        file_moves=MagicMock(),
        recycle=MagicMock(),
        roots=MagicMock(),
        refresh_playlists=lambda: None,
    )
    created = Env(tmp_path, host.context_for(MANIFEST), StatusRecorder())
    yield created
    created.close()


def wait_for(qtbot: QtBot, manager: ConnectionManager, state: str) -> None:
    qtbot.waitUntil(lambda: manager.state == state and not manager.busy, timeout=WAIT_MS)


def settle(qtbot: QtBot, manager: ConnectionManager) -> None:
    qtbot.waitUntil(lambda: not manager.busy, timeout=WAIT_MS)


def connected_manager(
    qtbot: QtBot, env: Env, server: RemoteServer, device_name: str
) -> ConnectionManager:
    manager = env.manager()
    manager.connect(server.url, server.username, server.password, device_name)
    wait_for(qtbot, manager, "connected")
    return manager


def devices_seen_by_a_checker(server: RemoteServer, device_name: str) -> list[dict]:
    """Sign in as the admin with a checker device, read the devices, and sign that out again."""
    _, token = RemoteClient(server.url).login(server.username, server.password, device_name)
    checker = RemoteClient(server.url, token)
    try:
        return checker.devices()
    finally:
        checker.logout()


def stored_token_exists(env: Env) -> bool:
    return tokens.token_exists(env.context.data_dir)


def test_connect_signs_in_and_keeps_no_password(
    qtbot: QtBot,
    env: Env,
    remote_server: RemoteServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    manager = env.manager()
    manager.connect(
        remote_server.url, remote_server.username, remote_server.password, "Test: studio"
    )
    assert manager.state == "connecting"
    wait_for(qtbot, manager, "connected")

    assert manager.signed_in
    assert manager.server_url == remote_server.url
    assert manager.device_name == "Test: studio"
    assert "Test: studio" in [device["name"] for device in manager.devices]
    assert manager.state_text.startswith("Connected")
    settings = env.context.settings
    assert settings.get("server_url") == remote_server.url
    assert settings.get("username") == remote_server.username
    assert settings.get("device_id") == manager.device_id
    assert settings.get("device_name") == "Test: studio"
    assert env.status.last == ("update", "Connected", "neutral", "cloud")
    assert stored_token_exists(env)

    # The password is nowhere: not in a file of the profile, not in a setting, not in a log.
    secret = remote_server.password.encode("utf-8")
    for path in env.base.rglob("*"):
        if path.is_file():
            assert secret not in path.read_bytes(), path.name
    for key in ("server_url", "username", "device_id", "device_name"):
        assert remote_server.password not in str(settings.get(key, ""))
    assert remote_server.password not in caplog.text


def test_disconnect_revokes_the_device_deletes_the_token_and_clears_the_item(
    qtbot: QtBot, env: Env, remote_server: RemoteServer
) -> None:
    manager = connected_manager(qtbot, env, remote_server, "Test: leaving")
    device_id = manager.device_id

    manager.disconnect()
    wait_for(qtbot, manager, "disconnected")

    assert not manager.signed_in
    assert not stored_token_exists(env)
    assert env.context.settings.get("server_url", "") == ""
    assert env.status.last == ("clear",)
    remaining = [
        device["device_id"] for device in devices_seen_by_a_checker(remote_server, "Test: checker")
    ]
    assert device_id not in remaining


def test_an_unreachable_server_is_offline_and_keeps_nothing(qtbot: QtBot, env: Env) -> None:
    manager = env.manager()
    manager.connect(f"http://127.0.0.1:{free_port()}", "admin", "a-password", "Test: far")
    wait_for(qtbot, manager, "offline")

    assert not manager.signed_in
    assert not stored_token_exists(env)
    assert env.status.last == ("update", "Offline", "warning", "cloud-off")


def test_a_saved_connection_is_offline_when_the_server_is_down_at_start(
    qtbot: QtBot, env: Env, remote_server: RemoteServer
) -> None:
    first = connected_manager(qtbot, env, remote_server, "Test: restart")
    first.shutdown()
    env.context.settings.set("server_url", f"http://127.0.0.1:{free_port()}")

    restarted = env.manager()
    restarted.start()
    wait_for(qtbot, restarted, "offline")

    assert restarted.signed_in  # the device still exists: the link is checked again later
    assert stored_token_exists(env)
    assert env.status.last == ("update", "Offline", "warning", "cloud-off")


def test_a_saved_connection_is_connected_again_at_start(
    qtbot: QtBot, env: Env, remote_server: RemoteServer
) -> None:
    first = connected_manager(qtbot, env, remote_server, "Test: resume")
    first.shutdown()

    restarted = env.manager()
    restarted.start()
    wait_for(qtbot, restarted, "connected")

    assert restarted.device_id == first.device_id
    assert env.status.last == ("update", "Connected", "neutral", "cloud")


def test_a_token_revoked_on_another_device_signs_this_computer_out(
    qtbot: QtBot, env: Env, remote_server: RemoteServer
) -> None:
    manager = connected_manager(qtbot, env, remote_server, "Test: revoked")
    _, other_token = RemoteClient(remote_server.url).login(
        remote_server.username, remote_server.password, "Test: other"
    )
    other = RemoteClient(remote_server.url, other_token)
    other.revoke_device(manager.device_id)

    manager.check_now()
    wait_for(qtbot, manager, "disconnected")

    assert not manager.signed_in
    assert not stored_token_exists(env)
    assert SIGNED_OUT_NOTICE in env.notices
    other.logout()


def test_a_wrong_password_is_an_error_and_keeps_nothing(
    qtbot: QtBot,
    env: Env,
    remote_server: RemoteServer,
    make_user: Callable[[], tuple[str, str]],
) -> None:
    username, _ = make_user()  # its own account: the server locks a user after failed sign-ins
    manager = env.manager()
    manager.connect(remote_server.url, username, "not the password", "Test: refused")
    wait_for(qtbot, manager, "error")

    assert manager.state_text == "Wrong user name or password."
    assert not manager.signed_in
    assert not stored_token_exists(env)


def test_a_second_connect_is_refused_while_connected(
    qtbot: QtBot, env: Env, remote_server: RemoteServer
) -> None:
    manager = connected_manager(qtbot, env, remote_server, "Test: once")
    manager.connect(
        remote_server.url, remote_server.username, remote_server.password, "Test: twice"
    )

    assert ALREADY_NOTICE in env.notices
    assert manager.state == "connected"
    assert not manager.busy


def test_the_device_name_is_kept_until_the_next_connection(
    qtbot: QtBot, env: Env, remote_server: RemoteServer
) -> None:
    manager = env.manager()
    manager.set_device_name("Test: lounge")
    assert manager.device_name == "Test: lounge"
    assert env.context.settings.get("device_name") == "Test: lounge"

    manager.connect(
        remote_server.url, remote_server.username, remote_server.password, "Test: lounge"
    )
    wait_for(qtbot, manager, "connected")
    manager.set_device_name("Test: renamed")

    assert manager.device_name == "Test: lounge"
    assert "To give this computer another name, disconnect and connect again." in env.notices


def test_a_device_of_the_account_can_be_revoked_and_this_one_cannot(
    qtbot: QtBot, env: Env, remote_server: RemoteServer
) -> None:
    manager = connected_manager(qtbot, env, remote_server, "Test: keeper")
    _, spare_token = RemoteClient(remote_server.url).login(
        remote_server.username, remote_server.password, "Test: spare"
    )
    spare = RemoteClient(remote_server.url, spare_token)
    spare_id = next(d["device_id"] for d in spare.devices() if d["name"] == "Test: spare")

    manager.refresh_devices()
    settle(qtbot, manager)
    assert "Test: spare" in [device["name"] for device in manager.devices]

    manager.revoke(manager.device_id)
    assert "To sign this computer out, use Disconnect." in env.notices

    manager.revoke(spare_id)
    settle(qtbot, manager)
    assert spare_id not in [device["device_id"] for device in manager.devices]
    assert manager.state == "connected"
