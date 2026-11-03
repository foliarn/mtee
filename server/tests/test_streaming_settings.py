"""Streaming settings (plan 127.3): server settings (admin), and each user's default levels."""

from __future__ import annotations

from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from conftest import MakeDevice, MakeUser

ADMIN = "/api/v1/admin/settings/streaming"
USER = "/api/v1/settings/streaming"

SERVER_DEFAULTS: dict[str, Any] = {
    "max_transcodes": 2,
    "cache_limit_gb": 20,
    "wav_to_flac": True,
    "lossless_cap": None,
}
USER_DEFAULTS: dict[str, str] = {
    "default_level_wifi": "lossless",
    "default_level_mobile": "320",
}


@pytest.fixture
def admin(app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> dict[str, Any]:
    user = make_user(app, "boss", is_admin=True)
    return {**user, "headers": make_device(app, user)["headers"]}


@pytest.fixture
def alice(app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> dict[str, Any]:
    user = make_user(app, "alice")
    return {**user, "headers": make_device(app, user)["headers"]}


@pytest.fixture
def bob(app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> dict[str, Any]:
    user = make_user(app, "bob")
    return {**user, "headers": make_device(app, user)["headers"]}


def _error(response: Any) -> dict[str, str]:
    error: dict[str, str] = response.json()["error"]
    return error


# -- server settings -------------------------------------------------------------------------


def test_the_server_settings_start_at_their_defaults(
    client: TestClient, admin: dict[str, Any]
) -> None:
    response = client.get(ADMIN, headers=admin["headers"])
    assert response.status_code == 200
    assert response.json() == SERVER_DEFAULTS


def test_a_partial_put_returns_the_full_settings(client: TestClient, admin: dict[str, Any]) -> None:
    headers = admin["headers"]
    response = client.put(ADMIN, json={"max_transcodes": 4}, headers=headers)
    assert response.status_code == 200
    assert response.json() == {**SERVER_DEFAULTS, "max_transcodes": 4}
    assert client.get(ADMIN, headers=headers).json() == {**SERVER_DEFAULTS, "max_transcodes": 4}


def test_every_server_setting_is_stored(client: TestClient, admin: dict[str, Any]) -> None:
    headers = admin["headers"]
    body = {
        "max_transcodes": 8,
        "cache_limit_gb": 1000,
        "wav_to_flac": False,
        "lossless_cap": {"sample_rate": 96000, "bit_depth": 24},
    }
    response = client.put(ADMIN, json=body, headers=headers)
    assert response.status_code == 200
    assert response.json() == body
    assert client.get(ADMIN, headers=headers).json() == body


def test_the_lossless_cap_can_be_cleared(client: TestClient, admin: dict[str, Any]) -> None:
    headers = admin["headers"]
    client.put(
        ADMIN, json={"lossless_cap": {"sample_rate": 48000, "bit_depth": 16}}, headers=headers
    )
    response = client.put(ADMIN, json={"lossless_cap": None}, headers=headers)
    assert response.json()["lossless_cap"] is None


@pytest.mark.parametrize(
    ("body", "names"),
    [
        ({"max_transcodes": 0}, "max_transcodes"),
        ({"max_transcodes": 9}, "max_transcodes"),
        ({"max_transcodes": "2"}, "max_transcodes"),
        ({"max_transcodes": True}, "max_transcodes"),
        ({"max_transcodes": None}, "max_transcodes"),
        ({"cache_limit_gb": 0}, "cache_limit_gb"),
        ({"cache_limit_gb": 1001}, "cache_limit_gb"),
        ({"cache_limit_gb": 2.5}, "cache_limit_gb"),
        ({"wav_to_flac": "yes"}, "wav_to_flac"),
        ({"wav_to_flac": None}, "wav_to_flac"),
        ({"lossless_cap": {"sample_rate": 96000}}, "lossless_cap"),
        ({"lossless_cap": {"sample_rate": 96000, "bit_depth": 24, "x": 1}}, "lossless_cap"),
        ({"lossless_cap": {"sample_rate": 96000, "bit_depth": 20}}, "bit_depth"),
        ({"lossless_cap": {"sample_rate": 1, "bit_depth": 24}}, "sample_rate"),
        ({"lossless_cap": "96k"}, "lossless_cap"),
        ({"streaming_mode": "fast"}, "streaming_mode"),
    ],
)
def test_an_invalid_server_value_is_refused_naming_its_key(
    client: TestClient, admin: dict[str, Any], body: dict[str, Any], names: str
) -> None:
    response = client.put(ADMIN, json=body, headers=admin["headers"])
    assert response.status_code == 400
    assert _error(response)["code"] == "bad_request"
    assert names in _error(response)["message"]


def test_a_refused_put_stores_nothing(client: TestClient, admin: dict[str, Any]) -> None:
    headers = admin["headers"]
    response = client.put(ADMIN, json={"max_transcodes": 3, "cache_limit_gb": 0}, headers=headers)
    assert response.status_code == 400
    assert client.get(ADMIN, headers=headers).json() == SERVER_DEFAULTS


def test_a_body_that_is_not_an_object_is_refused(client: TestClient, admin: dict[str, Any]) -> None:
    response = client.put(ADMIN, content=b"[1, 2]", headers=admin["headers"])
    assert response.status_code == 400
    assert _error(response)["code"] == "bad_request"


def test_the_server_settings_are_for_administrators_only(
    client: TestClient, alice: dict[str, Any]
) -> None:
    assert client.get(ADMIN, headers=alice["headers"]).status_code == 403
    response = client.put(ADMIN, json={"max_transcodes": 4}, headers=alice["headers"])
    assert response.status_code == 403
    assert _error(response)["code"] == "forbidden"


# -- default levels per user -----------------------------------------------------------------


def test_a_user_starts_at_the_default_levels(client: TestClient, alice: dict[str, Any]) -> None:
    response = client.get(USER, headers=alice["headers"])
    assert response.status_code == 200
    assert response.json() == USER_DEFAULTS


def test_a_partial_put_keeps_the_other_level(client: TestClient, alice: dict[str, Any]) -> None:
    headers = alice["headers"]
    response = client.put(USER, json={"default_level_mobile": "128"}, headers=headers)
    assert response.status_code == 200
    assert response.json() == {**USER_DEFAULTS, "default_level_mobile": "128"}
    assert client.get(USER, headers=headers).json() == response.json()


def test_each_user_has_their_own_levels(
    client: TestClient, alice: dict[str, Any], bob: dict[str, Any]
) -> None:
    client.put(USER, json={"default_level_wifi": "original"}, headers=alice["headers"])
    assert client.get(USER, headers=bob["headers"]).json() == USER_DEFAULTS
    assert client.get(USER, headers=alice["headers"]).json()["default_level_wifi"] == "original"


def test_the_server_settings_do_not_change_the_user_levels(
    client: TestClient, admin: dict[str, Any], alice: dict[str, Any]
) -> None:
    client.put(ADMIN, json={"wav_to_flac": False}, headers=admin["headers"])
    assert client.get(USER, headers=alice["headers"]).json() == USER_DEFAULTS


@pytest.mark.parametrize(
    ("body", "names"),
    [
        ({"default_level_wifi": "flac"}, "default_level_wifi"),
        ({"default_level_mobile": "256"}, "default_level_mobile"),
        ({"default_level_mobile": None}, "default_level_mobile"),
        ({"default_level_mobile": 320}, "default_level_mobile"),
        ({"default_level_other": "320"}, "default_level_other"),
    ],
)
def test_an_invalid_level_is_refused_naming_its_key(
    client: TestClient, alice: dict[str, Any], body: dict[str, Any], names: str
) -> None:
    response = client.put(USER, json=body, headers=alice["headers"])
    assert response.status_code == 400
    assert _error(response)["code"] == "bad_request"
    assert names in _error(response)["message"]
    assert client.get(USER, headers=alice["headers"]).json() == USER_DEFAULTS


def test_every_level_is_accepted_as_a_default(client: TestClient, alice: dict[str, Any]) -> None:
    for level in ("original", "lossless", "320", "128"):
        response = client.put(USER, json={"default_level_wifi": level}, headers=alice["headers"])
        assert response.json()["default_level_wifi"] == level


# -- the routes need a token -----------------------------------------------------------------


@pytest.mark.parametrize("path", [ADMIN, USER])
def test_the_streaming_routes_need_a_token(client: TestClient, path: str) -> None:
    for response in (
        client.get(path),
        client.put(path, json={}),
        client.get(path, headers={"Authorization": "Bearer not-a-real-token"}),
    ):
        assert response.status_code == 401
        assert _error(response)["code"] == "unauthorized"
