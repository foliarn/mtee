"""The HTTP client against a real MTEE Remote server (plan 126.1).

The server is started once for the session by ``conftest.py``. The wrong-password checks are
kept few: the server counts failed sign-ins and refuses after five of them.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from mtee.plugins.remote.client import (  # pyright: ignore[reportMissingImports]
    ApiError,
    NetworkError,
    RemoteClient,
)
from tests.plugins.remote.conftest import RemoteServer, free_port


def _login(server: RemoteServer, device_name: str) -> tuple[str, str]:
    return RemoteClient(server.url).login(server.username, server.password, device_name)


def test_health_answers_with_the_version(remote_server: RemoteServer) -> None:
    health = RemoteClient(remote_server.url).health()
    assert health["status"] == "ok"
    assert health["version"]


def test_a_login_gives_a_token_that_reads_the_devices(remote_server: RemoteServer) -> None:
    device_id, token = _login(remote_server, "Test: login")
    devices = RemoteClient(remote_server.url, token).devices()
    own = [device for device in devices if device["device_id"] == device_id]
    assert len(own) == 1
    assert own[0]["name"] == "Test: login"
    assert own[0]["current"] is True
    RemoteClient(remote_server.url, token).logout()


def test_a_wrong_password_is_refused_with_the_server_code(
    remote_server: RemoteServer, make_user: Callable[[], tuple[str, str]]
) -> None:
    username, _ = make_user()  # its own account: the server locks a user after failed sign-ins
    with pytest.raises(ApiError) as caught:
        RemoteClient(remote_server.url).login(username, "not the password", "Test: wrong")
    assert caught.value.status == 401
    assert caught.value.code == "unauthorized"
    assert "not the password" not in caught.value.message


def test_a_device_can_revoke_another_device(remote_server: RemoteServer) -> None:
    first_id, first_token = _login(remote_server, "Test: first")
    second_id, second_token = _login(remote_server, "Test: second")
    RemoteClient(remote_server.url, first_token).revoke_device(second_id)

    remaining = [
        device["device_id"] for device in RemoteClient(remote_server.url, first_token).devices()
    ]
    assert first_id in remaining
    assert second_id not in remaining
    with pytest.raises(ApiError) as caught:
        RemoteClient(remote_server.url, second_token).devices()
    assert caught.value.status == 401
    RemoteClient(remote_server.url, first_token).logout()


def test_a_logout_makes_the_token_refused(remote_server: RemoteServer) -> None:
    _, token = _login(remote_server, "Test: logout")
    RemoteClient(remote_server.url, token).logout()
    with pytest.raises(ApiError) as caught:
        RemoteClient(remote_server.url, token).devices()
    assert caught.value.status == 401


def test_the_roots_and_the_library_status_are_read(remote_server: RemoteServer) -> None:
    _, token = _login(remote_server, "Test: reads")
    client = RemoteClient(remote_server.url, token)
    assert isinstance(client.roots(), list)
    assert isinstance(client.library_status(), dict)
    client.logout()


@pytest.mark.parametrize(
    "address",
    [
        "music.example.net",
        "ftp://music.example.net",
        "http://music.example.net",
        "http://192.168.1.10:8080",
        "http://127.0.0.1",
        "https://",
        "https://user:secret@music.example.net",
        "https://music.example.net/?token=1",
    ],
)
def test_a_bad_address_is_refused(address: str) -> None:
    with pytest.raises(ValueError):
        RemoteClient(address)


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("https://music.example.net/", "https://music.example.net"),
        ("  https://music.example.net  ", "https://music.example.net"),
        ("http://127.0.0.1:8080/", "http://127.0.0.1:8080"),
        ("http://localhost:9000", "http://localhost:9000"),
    ],
)
def test_a_good_address_is_kept_without_its_trailing_slash(address: str, expected: str) -> None:
    assert RemoteClient(address).base_url == expected


def test_a_closed_port_is_a_readable_network_error() -> None:
    client = RemoteClient(f"http://127.0.0.1:{free_port()}", timeout=5)
    with pytest.raises(NetworkError) as caught:
        client.health()
    assert NetworkError.readable is True
    assert "cannot be reached" in str(caught.value)
