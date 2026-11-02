"""Server trash routes: list, restore, purge (milestone 124.5). Rules in `mtee_remote/trash.py`."""

from __future__ import annotations

from typing import Any

import anyio.to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from mtee_remote import backups, trash, uploads
from mtee_remote.errors import ApiError
from mtee_remote.http import get_str, json_ok, read_json
from mtee_remote.library.service import LibraryService
from mtee_remote.security import auth, require_admin


async def list_trash(request: Request) -> JSONResponse:
    context = auth(request)
    db = request.app.state.db

    def work() -> list[dict[str, Any]]:
        return trash.list_entries(db.conn(), context.user_id)

    return json_ok({"trash": await anyio.to_thread.run_sync(work)})


async def restore_entry(request: Request) -> JSONResponse:
    """`POST /api/v1/trash/{id}/restore`: `{item}` for an item, `{backup}` for a backup."""
    context = auth(request)
    trash_id: str = request.path_params["trash_id"]
    relative_path: str | None = None
    if (await request.body()).strip():
        body = await read_json(request)
        relative_path = get_str(body, "relative_path", max_len=1100, required=False)
    db = request.app.state.db
    settings = request.app.state.settings

    def work() -> dict[str, Any]:
        if trash.entry_kind(db.conn(), context.user_id, trash_id) == "backup":
            if relative_path is not None:
                raise ApiError("bad_request", "A backup goes back to its own place.")
            backup_id = trash.restore_backup(
                db, settings, user_id=context.user_id, trash_id=trash_id
            )
            return {"backup": backups.public_by_id(db.conn(), context.user_id, backup_id)}
        item = trash.restore(
            db,
            settings,
            user_id=context.user_id,
            device_id=context.device_id,
            trash_id=trash_id,
            relative_path=relative_path,
        )
        return {"item": item}

    with uploads.exclusive(f"trash:{trash_id}"):
        result = await anyio.to_thread.run_sync(work)
    library: LibraryService | None = getattr(request.app.state, "library", None)
    if library is not None:
        library.wake_hasher()
    return json_ok(result)


async def purge_entry(request: Request) -> Response:
    """`DELETE /api/v1/trash/{id}?confirm=yes`: the only permanent delete; administrators only.

    An administrator can purge entries of their own trash only; another user's entry is 404.
    """
    context = require_admin(request)
    trash_id: str = request.path_params["trash_id"]
    if request.query_params.get("confirm") != "yes":
        raise ApiError("bad_request", "Add confirm=yes to delete this file for good.")
    db = request.app.state.db
    settings = request.app.state.settings
    with uploads.exclusive(f"trash:{trash_id}"):
        await anyio.to_thread.run_sync(
            lambda: trash.purge(db, settings, user_id=context.user_id, trash_id=trash_id)
        )
    return Response(status_code=204)


ROUTES: list[BaseRoute] = [
    Route("/api/v1/trash", list_trash, methods=["GET"]),
    Route("/api/v1/trash/{trash_id}/restore", restore_entry, methods=["POST"]),
    Route("/api/v1/trash/{trash_id}", purge_entry, methods=["DELETE"]),
]
