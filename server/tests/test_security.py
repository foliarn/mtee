from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from conftest import MakeDevice, MakeUser
from mtee_remote import clock
from mtee_remote.errors import ApiError
from mtee_remote.security import (
    PUBLIC_PATHS,
    AuthContext,
    auth,
    hash_token,
    new_token,
    require_admin,
)

PARAM = re.compile(r"\{[^}]*\}")
UNSAFE_METHODS_SKIPPED = {"HEAD", "OPTIONS"}


def _fill(path: str) -> str:
    return PARAM.sub("x", path)


async def _whoami(request: Request) -> JSONResponse:
    context = auth(request)
    return JSONResponse(
        {
            "user_id": context.user_id,
            "username": context.username,
            "device_id": context.device_id,
            "is_admin": context.is_admin,
        }
    )


async def _admin_only(request: Request) -> JSONResponse:
    require_admin(request)
    return JSONResponse({"ok": True})


@pytest.fixture
def probe_app(app: Starlette) -> Starlette:
    """The app with two extra protected routes, to test the middleware itself."""
    app.router.routes.append(Route("/api/v1/_whoami", _whoami))
    app.router.routes.append(Route("/api/v1/_admin", _admin_only))
    return app


def _error_code(response: Any) -> str:
    return response.json()["error"]["code"]


def test_every_route_needs_a_token(probe_app: Starlette) -> None:
    """Fails if a registered route (other than the public ones) answers without a token."""
    checked = 0
    with TestClient(probe_app) as client:
        for route in probe_app.routes:
            assert isinstance(route, Route), f"Only plain routes are allowed: {route!r}"
            if route.path in PUBLIC_PATHS:
                continue
            assert route.methods is not None
            for method in sorted(route.methods - UNSAFE_METHODS_SKIPPED):
                path = _fill(route.path)
                for headers in ({}, {"Authorization": "Bearer not-a-real-token"}):
                    response = client.request(method, path, headers=headers)
                    assert response.status_code == 401, (method, route.path, headers)
                    assert _error_code(response) == "unauthorized", (method, route.path)
                    checked += 1
    assert checked >= 4  # the two probe routes, with and without a token


def test_public_paths_are_the_documented_ones() -> None:
    assert {"/health", "/api/v1/auth/login"} == PUBLIC_PATHS


def test_valid_token_reaches_the_route(
    probe_app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    user = make_user(probe_app, "alice")
    device = make_device(probe_app, user)
    with TestClient(probe_app) as client:
        response = client.get("/api/v1/_whoami", headers=device["headers"])
    assert response.status_code == 200
    assert response.json() == {
        "user_id": user["user_id"],
        "username": "alice",
        "device_id": device["device_id"],
        "is_admin": False,
    }


@pytest.mark.parametrize("header", ["Basic abc", "Bearer", "Bearer ", "token", ""])
def test_malformed_authorization_header_is_refused(probe_app: Starlette, header: str) -> None:
    with TestClient(probe_app) as client:
        response = client.get("/api/v1/_whoami", headers={"Authorization": header})
    assert response.status_code == 401
    assert _error_code(response) == "unauthorized"


def test_revoked_device_is_refused(
    probe_app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    user = make_user(probe_app, "alice")
    device = make_device(probe_app, user)
    with TestClient(probe_app) as client:
        assert client.get("/api/v1/_whoami", headers=device["headers"]).status_code == 200
        with probe_app.state.db.transaction() as tx:
            tx.conn.execute(
                "UPDATE devices SET revoked_at_utc = ? WHERE device_id = ?",
                (clock.to_iso(clock.utc_now()), device["device_id"]),
            )
        response = client.get("/api/v1/_whoami", headers=device["headers"])
    assert response.status_code == 401
    assert _error_code(response) == "unauthorized"


def test_disabled_user_is_refused(
    probe_app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    user = make_user(probe_app, "alice")
    device = make_device(probe_app, user)
    with TestClient(probe_app) as client:
        assert client.get("/api/v1/_whoami", headers=device["headers"]).status_code == 200
        with probe_app.state.db.transaction() as tx:
            tx.conn.execute("UPDATE users SET disabled = 1 WHERE user_id = ?", (user["user_id"],))
        response = client.get("/api/v1/_whoami", headers=device["headers"])
    assert response.status_code == 401


def test_admin_route_refuses_a_normal_user(
    probe_app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    normal = make_device(probe_app, make_user(probe_app, "alice"))
    admin = make_device(probe_app, make_user(probe_app, "root", is_admin=True))
    with TestClient(probe_app) as client:
        refused = client.get("/api/v1/_admin", headers=normal["headers"])
        allowed = client.get("/api/v1/_admin", headers=admin["headers"])
    assert refused.status_code == 403
    assert _error_code(refused) == "forbidden"
    assert allowed.status_code == 200


def test_last_seen_is_updated_at_most_once_a_minute(
    probe_app: Starlette,
    make_user: MakeUser,
    make_device: MakeDevice,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = make_device(probe_app, make_user(probe_app, "alice"))
    start = clock.utc_now()
    now = [start]
    monkeypatch.setattr(clock, "utc_now", lambda: now[0])

    def last_seen() -> str | None:
        row = (
            probe_app.state.db.conn()
            .execute(
                "SELECT last_seen_utc FROM devices WHERE device_id = ?", (device["device_id"],)
            )
            .fetchone()
        )
        return row["last_seen_utc"]

    assert last_seen() is None
    with TestClient(probe_app) as client:
        client.get("/api/v1/_whoami", headers=device["headers"])
        first = last_seen()
        assert first == clock.to_iso(start)
        now[0] = start + timedelta(seconds=30)
        client.get("/api/v1/_whoami", headers=device["headers"])
        assert last_seen() == first
        now[0] = start + timedelta(seconds=61)
        client.get("/api/v1/_whoami", headers=device["headers"])
        assert last_seen() == clock.to_iso(now[0])


def test_token_helpers() -> None:
    token = new_token()
    assert len(token) >= 43
    assert new_token() != token
    assert len(hash_token(token)) == 64
    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != hash_token(token + "x")


def test_auth_context_is_frozen() -> None:
    context = AuthContext(user_id="u", username="a", device_id="d", is_admin=False)
    with pytest.raises(AttributeError):
        context.is_admin = True  # type: ignore[misc]


def test_unknown_error_shapes() -> None:
    assert ApiError("quota_exceeded", "x").status == 413
    assert ApiError("path_taken", "x").status == 409
    assert ApiError("range_not_satisfiable", "x").status == 416
    assert ApiError("conflict", "x", 418).status == 418
