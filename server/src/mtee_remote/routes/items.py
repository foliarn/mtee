"""Item routes: list, get (124.4); download, move and trash (124.5)."""

from __future__ import annotations

import base64
import json
import os
from pathlib import PurePosixPath
from typing import Any

import anyio.to_thread
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Route

from mtee_remote import trash
from mtee_remote.errors import ApiError
from mtee_remote.http import get_str, json_ok, read_json
from mtee_remote.library import store
from mtee_remote.paths import normalize_relative_path
from mtee_remote.security import auth
from mtee_remote.uploads import disk_path

DEFAULT_LIMIT = 500
MAX_LIMIT = 1000


def encode_cursor(root_id: str, relative_path: str) -> str:
    """Return the opaque page cursor for the item at `(root_id, relative_path)`."""
    raw = json.dumps([root_id, relative_path], ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        root_id, relative_path = json.loads(raw.decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError):
        raise ApiError("bad_request", "The 'after' cursor is not valid.") from None
    if not isinstance(root_id, str) or not isinstance(relative_path, str):
        raise ApiError("bad_request", "The 'after' cursor is not valid.")
    return root_id, relative_path


def _limit(request: Request) -> int:
    raw = request.query_params.get("limit")
    if raw is None:
        return DEFAULT_LIMIT
    try:
        value = int(raw)
    except ValueError:
        raise ApiError("bad_request", "The 'limit' must be a whole number.") from None
    if not 1 <= value <= MAX_LIMIT:
        raise ApiError("bad_request", f"The 'limit' must be between 1 and {MAX_LIMIT}.")
    return value


def _prefix(request: Request) -> str:
    """The `prefix` filter: a leading part of `relative_path`, checked like a client path."""
    raw = request.query_params.get("prefix", "")
    if not raw:
        return ""
    trailing = raw.endswith("/")
    clean = normalize_relative_path(raw.rstrip("/")) if raw.rstrip("/") else ""
    return clean + "/" if trailing and clean else clean


async def list_items(request: Request) -> JSONResponse:
    """`GET /api/v1/items?root_id=&prefix=&after=&limit=`.

    Returns the caller's present items ordered by `(root_id, relative_path)`. `prefix` keeps
    paths that start with that text (plain prefix: `rock` also matches `rockabilly/x.mp3`;
    add a trailing `/` for a folder). Paging is keyset: `next` is an opaque cursor, to be
    sent back as `after`; it is null on the last page. A cursor stays valid when items are
    added, moved or removed between pages.
    """
    context = auth(request)
    limit = _limit(request)
    prefix = _prefix(request)
    root_id = request.query_params.get("root_id") or None
    after = request.query_params.get("after")
    cursor = decode_cursor(after) if after else None
    db = request.app.state.db

    def work() -> dict[str, Any]:
        sql = f"SELECT {store.ITEM_COLUMNS} FROM items WHERE user_id = ? AND state = 'present'"
        args: list[Any] = [context.user_id]
        if root_id is not None:
            sql += " AND root_id = ?"
            args.append(root_id)
        if prefix:
            # substr instead of LIKE: no wildcard characters to escape.
            sql += " AND substr(relative_path, 1, ?) = ?"
            args += [len(prefix), prefix]
        if cursor is not None:
            sql += " AND (root_id, relative_path) > (?, ?)"
            args += list(cursor)
        sql += " ORDER BY root_id, relative_path LIMIT ?"
        args.append(limit + 1)
        rows = db.conn().execute(sql, args).fetchall()
        page = rows[:limit]
        next_cursor = (
            encode_cursor(page[-1]["root_id"], page[-1]["relative_path"])
            if len(rows) > limit
            else None
        )
        return {"items": [store.item_public(row) for row in page], "next": next_cursor}

    return json_ok(await anyio.to_thread.run_sync(work))


async def get_item(request: Request) -> JSONResponse:
    context = auth(request)
    item_id: str = request.path_params["item_id"]
    db = request.app.state.db

    def work() -> dict[str, Any] | None:
        row = (
            db.conn()
            .execute(
                f"SELECT {store.ITEM_COLUMNS} FROM items"
                " WHERE item_id = ? AND user_id = ? AND state = 'present'",
                (item_id, context.user_id),
            )
            .fetchone()
        )
        return store.item_public(row) if row is not None else None

    item = await anyio.to_thread.run_sync(work)
    if item is None:
        raise ApiError("not_found", "Unknown item.")
    return json_ok(item)


_MEDIA_TYPES = {
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
}


def media_type_for(relative_path: str) -> str:
    return _MEDIA_TYPES.get(PurePosixPath(relative_path).suffix.lower(), "application/octet-stream")


async def download_item(request: Request) -> Response:
    """`GET /api/v1/items/{id}/file`: the original bytes, with Range support.

    Starlette's `FileResponse` answers `Range` requests (206, `Content-Range`, 416 with
    `Content-Range: bytes */size`) and sets `Accept-Ranges` and `Content-Length`. The ETag is
    the SHA-256 when it is known.
    """
    context = auth(request)
    item_id: str = request.path_params["item_id"]
    db = request.app.state.db
    settings = request.app.state.settings

    def work() -> tuple[str, os.stat_result, str | None, str]:
        conn = db.conn()
        row = store.get_present_item(conn, context.user_id, item_id)
        path = disk_path(store.root_path(settings, conn, row["root_id"]), row["relative_path"])
        info = os.stat(path)
        return str(path), info, row["sha256"], row["relative_path"]

    try:
        path, info, sha256, relative = await anyio.to_thread.run_sync(work)
    except OSError:
        raise ApiError("not_found", "The file is not available.") from None
    headers = {"ETag": f'"{sha256}"'} if sha256 else {}
    return FileResponse(
        path, media_type=media_type_for(relative), headers=headers, stat_result=info
    )


async def move_item(request: Request) -> JSONResponse:
    context = auth(request)
    item_id: str = request.path_params["item_id"]
    body = await read_json(request)
    relative_path = get_str(body, "relative_path", max_len=1100)
    assert relative_path is not None
    db = request.app.state.db
    settings = request.app.state.settings

    def work() -> dict[str, Any]:
        return trash.move_item(
            db,
            settings,
            user_id=context.user_id,
            item_id=item_id,
            new_relative_path=relative_path,
        )

    return json_ok({"item": await anyio.to_thread.run_sync(work)})


async def trash_item(request: Request) -> JSONResponse:
    context = auth(request)
    item_id: str = request.path_params["item_id"]
    db = request.app.state.db
    settings = request.app.state.settings

    def work() -> str:
        return trash.trash_item(
            db, settings, user_id=context.user_id, device_id=context.device_id, item_id=item_id
        )

    return json_ok({"trash_id": await anyio.to_thread.run_sync(work)})


ROUTES: list[BaseRoute] = [
    Route("/api/v1/items", list_items, methods=["GET"]),
    Route("/api/v1/items/{item_id}", get_item, methods=["GET"]),
    Route("/api/v1/items/{item_id}/file", download_item, methods=["GET", "HEAD"]),
    Route("/api/v1/items/{item_id}/move", move_item, methods=["POST"]),
    Route("/api/v1/items/{item_id}/trash", trash_item, methods=["POST"]),
]
