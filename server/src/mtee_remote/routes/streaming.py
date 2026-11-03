"""Streaming settings routes (plan 127.3). The rules live in `mtee_remote/streaming/settings.py`.

- `GET` and `PUT /api/v1/admin/settings/streaming`: the server's settings, administrators only.
- `GET` and `PUT /api/v1/settings/streaming`: the current user's default levels.

A `PUT` takes a partial object and returns the full settings.
"""

from __future__ import annotations

from typing import Any

import anyio.to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from mtee_remote.db import Database
from mtee_remote.http import json_ok, read_json
from mtee_remote.security import auth, require_admin
from mtee_remote.streaming import settings


async def get_server_settings(request: Request) -> JSONResponse:
    require_admin(request)
    db: Database = request.app.state.db

    def work() -> dict[str, Any]:
        return settings.server_streaming_settings(db.conn())

    return json_ok(await anyio.to_thread.run_sync(work))


async def put_server_settings(request: Request) -> JSONResponse:
    """Store the given server streaming settings and return all of them.

    The settings are stored at once, but the server reads them at start: a changed value
    (`max_transcodes`, `cache_limit_gb`, `wav_to_flac`, `lossless_cap`) applies after the next
    restart of the server. Until then the running server keeps the values it started with.
    """
    require_admin(request)
    body = await read_json(request)
    db: Database = request.app.state.db

    def work() -> dict[str, Any]:
        with db.transaction() as tx:
            return settings.put_server_streaming_settings(tx, body)

    return json_ok(await anyio.to_thread.run_sync(work))


async def get_user_settings(request: Request) -> JSONResponse:
    context = auth(request)
    db: Database = request.app.state.db

    def work() -> dict[str, str]:
        return settings.user_streaming_settings(db.conn(), context.user_id)

    return json_ok(await anyio.to_thread.run_sync(work))


async def put_user_settings(request: Request) -> JSONResponse:
    context = auth(request)
    body = await read_json(request)
    db: Database = request.app.state.db

    def work() -> dict[str, str]:
        with db.transaction() as tx:
            return settings.put_user_streaming_settings(tx, context.user_id, body)

    return json_ok(await anyio.to_thread.run_sync(work))


ROUTES: list[BaseRoute] = [
    Route("/api/v1/admin/settings/streaming", get_server_settings, methods=["GET"]),
    Route("/api/v1/admin/settings/streaming", put_server_settings, methods=["PUT"]),
    Route("/api/v1/settings/streaming", get_user_settings, methods=["GET"]),
    Route("/api/v1/settings/streaming", put_user_settings, methods=["PUT"]),
]
