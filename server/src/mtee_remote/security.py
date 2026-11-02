"""Device tokens and the authentication middleware.

Passwords and login live elsewhere; this module only knows tokens.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import anyio.to_thread
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from mtee_remote import clock
from mtee_remote.db import Database
from mtee_remote.errors import ApiError, error_response

PUBLIC_PATHS = frozenset({"/health", "/api/v1/auth/login"})

LAST_SEEN_INTERVAL = timedelta(minutes=1)


def new_token() -> str:
    """Return a new device token (32 random bytes, URL-safe text)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest under which a token is stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    username: str
    device_id: str
    is_admin: bool


def _bearer_token(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            token = token.strip()
            if scheme.lower() == "bearer" and token:
                return token
            return None
    return None


def _lookup(db: Database, token: str) -> AuthContext | None:
    """Find the device for `token` (worker thread) and refresh `last_seen_utc` once a minute."""
    conn = db.conn()
    row = conn.execute(
        "SELECT d.device_id, d.last_seen_utc, u.user_id, u.username, u.is_admin"
        " FROM devices d JOIN users u ON u.user_id = d.user_id"
        " WHERE d.token_hash = ? AND d.revoked_at_utc IS NULL AND u.disabled = 0",
        (hash_token(token),),
    ).fetchone()
    if row is None:
        return None
    now = clock.utc_now()
    last_seen = row["last_seen_utc"]
    stale = last_seen is None
    if not stale:
        try:
            stale = now - datetime.fromisoformat(last_seen) >= LAST_SEEN_INTERVAL
        except ValueError:
            stale = True
    if stale:
        with db.transaction() as tx:
            tx.conn.execute(
                "UPDATE devices SET last_seen_utc = ? WHERE device_id = ?",
                (clock.to_iso(now), row["device_id"]),
            )
    return AuthContext(
        user_id=row["user_id"],
        username=row["username"],
        device_id=row["device_id"],
        is_admin=bool(row["is_admin"]),
    )


class AuthMiddleware:
    """Refuse every HTTP request without a valid device token, except `PUBLIC_PATHS`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
        token = _bearer_token(scope)
        context: AuthContext | None = None
        if token is not None:
            db: Database = scope["app"].state.db
            context = await anyio.to_thread.run_sync(_lookup, db, token)
        if context is None:
            response = error_response("unauthorized", "A valid device token is required.", 401)
            response.headers["WWW-Authenticate"] = "Bearer"
            await response(scope, receive, send)
            return
        state: dict[str, Any] = scope.setdefault("state", {})
        state["auth"] = context
        await self.app(scope, receive, send)


def auth(request: Request) -> AuthContext:
    """Return the caller's `AuthContext`; only valid behind `AuthMiddleware`."""
    context = getattr(request.state, "auth", None)
    if not isinstance(context, AuthContext):
        raise ApiError("unauthorized", "A valid device token is required.")
    return context


def require_admin(request: Request) -> AuthContext:
    context = auth(request)
    if not context.is_admin:
        raise ApiError("forbidden", "Administrator rights are required.")
    return context
