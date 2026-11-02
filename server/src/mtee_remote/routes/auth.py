"""Authentication routes: login and logout (milestone 124.3)."""

from __future__ import annotations

import math
from typing import Any

import anyio.to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from mtee_remote import clock
from mtee_remote.db import Database
from mtee_remote.errors import ApiError, error_response
from mtee_remote.http import get_str, json_ok, read_json
from mtee_remote.ids import new_id
from mtee_remote.passwords import (
    MAX_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    verify_password,
)
from mtee_remote.ratelimit import get_limiter
from mtee_remote.security import auth, hash_token, new_token
from mtee_remote.users import user_public

DEVICE_KINDS = ("desktop", "phone", "web")
UNAUTHORIZED_MESSAGE = "Wrong user name or password."
# Checked when a user name is unknown, so that such a login takes about as long as a wrong
# password for a real account.
DUMMY_HASH = hash_password("mtee-remote-timing-placeholder")


def _required_text(body: dict[str, Any], key: str, max_len: int) -> str:
    value = get_str(body, key, max_len=max_len)
    if value is None:  # get_str raises for a missing required field; kept for the type checker
        raise ApiError("bad_request", f"The field '{key}' is required.")
    return value


def _sign_in(
    db: Database, username: str, password: str, device_name: str, device_kind: str
) -> dict[str, Any] | None:
    """Check the password and open a device. Return None if the login is refused."""
    row = db.conn().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        verify_password(DUMMY_HASH, password)
        return None
    password_ok = verify_password(row["password_hash"], password)
    if not password_ok or row["disabled"]:
        return None
    device_id = new_id()
    token = new_token()
    now = clock.to_iso(clock.utc_now())
    with db.transaction() as tx:
        if needs_rehash(row["password_hash"]):
            tx.conn.execute(
                "UPDATE users SET password_hash = ? WHERE user_id = ?",
                (hash_password(password), row["user_id"]),
            )
        tx.conn.execute(
            "INSERT INTO devices(device_id, user_id, name, kind, token_hash, created_at_utc,"
            " last_seen_utc) VALUES (?,?,?,?,?,?,?)",
            (device_id, row["user_id"], device_name, device_kind, hash_token(token), now, now),
        )
        user = tx.conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (row["user_id"],)
        ).fetchone()
    return {"device_id": device_id, "token": token, "user": user_public(user)}


async def login(request: Request) -> JSONResponse:
    body = await read_json(request)
    username = _required_text(body, "username", 100).lower()
    password = _required_text(body, "password", MAX_PASSWORD_LENGTH)
    device_name = _required_text(body, "device_name", 100)
    device_kind = _required_text(body, "device_kind", 20)
    if device_kind not in DEVICE_KINDS:
        raise ApiError("bad_request", "The device kind must be desktop, phone or web.")

    client = request.client.host if request.client is not None else "unknown"
    keys = [f"user:{username}", f"addr:{client}"]
    limiter = get_limiter(request.app)
    wait = limiter.retry_after(keys)
    if wait is not None:
        response = error_response(
            "rate_limited", "Too many failed sign-in attempts. Try again later.", 429
        )
        response.headers["Retry-After"] = str(math.ceil(wait))
        return response

    db: Database = request.app.state.db
    result = await anyio.to_thread.run_sync(
        _sign_in, db, username, password, device_name, device_kind
    )
    if result is None:
        limiter.failure(keys)
        raise ApiError("unauthorized", UNAUTHORIZED_MESSAGE)
    limiter.success(keys)
    return json_ok(result, 201)


def _revoke_device(db: Database, device_id: str) -> None:
    with db.transaction() as tx:
        tx.conn.execute(
            "UPDATE devices SET revoked_at_utc = ? WHERE device_id = ? AND revoked_at_utc IS NULL",
            (clock.to_iso(clock.utc_now()), device_id),
        )


async def logout(request: Request) -> Response:
    context = auth(request)
    db: Database = request.app.state.db
    await anyio.to_thread.run_sync(_revoke_device, db, context.device_id)
    return Response(status_code=204)


ROUTES: list[BaseRoute] = [
    Route("/api/v1/auth/login", login, methods=["POST"]),
    Route("/api/v1/auth/logout", logout, methods=["POST"]),
]
