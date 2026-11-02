"""Database backup routes (milestone 124.7). The rules live in `mtee_remote/backups.py`.

Uploading a backup is `POST /api/v1/uploads` with purpose `backup` (see `routes/uploads.py`).
"""

from __future__ import annotations

import os
from typing import Any

import anyio.to_thread
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Route

from mtee_remote import backups
from mtee_remote.db import Database
from mtee_remote.errors import ApiError
from mtee_remote.http import get_int, json_ok, read_json
from mtee_remote.security import auth


async def list_backups(request: Request) -> JSONResponse:
    context = auth(request)
    db: Database = request.app.state.db

    def work() -> list[dict[str, Any]]:
        return backups.list_backups(db.conn(), context.user_id)

    return json_ok({"backups": await anyio.to_thread.run_sync(work)})


async def get_backup(request: Request) -> JSONResponse:
    context = auth(request)
    backup_id: str = request.path_params["backup_id"]
    db: Database = request.app.state.db

    def work() -> dict[str, Any]:
        return backups.public_by_id(db.conn(), context.user_id, backup_id)

    return json_ok(await anyio.to_thread.run_sync(work))


async def download_backup(request: Request) -> Response:
    """`GET /api/v1/backups/{id}/file`: the stored bytes, with Range support.

    The ETag is the SHA-256 of the backup, as for items.
    """
    context = auth(request)
    backup_id: str = request.path_params["backup_id"]
    db: Database = request.app.state.db
    settings = request.app.state.settings

    def work() -> tuple[str, os.stat_result, str]:
        path, sha256 = backups.backup_file(db, settings, context.user_id, backup_id)
        return path, os.stat(path), sha256

    try:
        path, info, sha256 = await anyio.to_thread.run_sync(work)
    except OSError:
        raise ApiError("not_found", "The file is not available.") from None
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={"ETag": f'"{sha256}"'},
        stat_result=info,
    )


async def delete_backup(request: Request) -> Response:
    context = auth(request)
    backup_id: str = request.path_params["backup_id"]
    db: Database = request.app.state.db
    settings = request.app.state.settings

    def work() -> None:
        backups.delete_backup(
            db, settings, user_id=context.user_id, device_id=context.device_id, backup_id=backup_id
        )

    await anyio.to_thread.run_sync(work)
    return Response(status_code=204)


async def get_settings(request: Request) -> JSONResponse:
    context = auth(request)
    db: Database = request.app.state.db

    def work() -> dict[str, int]:
        return backups.get_settings(db, context.user_id)

    return json_ok(await anyio.to_thread.run_sync(work))


async def put_settings(request: Request) -> JSONResponse:
    context = auth(request)
    body = await read_json(request)
    daily = get_int(body, "daily", minimum=0)
    weekly = get_int(body, "weekly", minimum=0)
    assert daily is not None and weekly is not None
    db: Database = request.app.state.db
    settings = request.app.state.settings

    def work() -> dict[str, int]:
        return backups.put_settings(
            db,
            settings,
            user_id=context.user_id,
            device_id=context.device_id,
            daily=daily,
            weekly=weekly,
        )

    return json_ok(await anyio.to_thread.run_sync(work))


ROUTES: list[BaseRoute] = [
    Route("/api/v1/backups", list_backups, methods=["GET"]),
    Route("/api/v1/backups/{backup_id}", get_backup, methods=["GET"]),
    Route("/api/v1/backups/{backup_id}/file", download_backup, methods=["GET"]),
    Route("/api/v1/backups/{backup_id}", delete_backup, methods=["DELETE"]),
    Route("/api/v1/settings/backups", get_settings, methods=["GET"]),
    Route("/api/v1/settings/backups", put_settings, methods=["PUT"]),
]
