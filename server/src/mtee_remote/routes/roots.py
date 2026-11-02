"""Library root routes: create, list, scan, status (milestone 124.4)."""

from __future__ import annotations

from typing import Any

import anyio.to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from mtee_remote import clock
from mtee_remote.errors import ApiError
from mtee_remote.http import get_str, json_ok, read_json
from mtee_remote.ids import new_id
from mtee_remote.library import store
from mtee_remote.library.service import LibraryService
from mtee_remote.paths import normalize_relative_path
from mtee_remote.security import auth

_ROOT_SELECT = (
    "SELECT r.root_id, r.name, r.relative_dir, r.adopted, COUNT(i.item_id) AS item_count,"
    " COALESCE(SUM(i.size_bytes), 0) AS total_bytes FROM roots r"
    " LEFT JOIN items i ON i.root_id = r.root_id AND i.state = 'present'"
    " WHERE r.user_id = ?"
)


def _root_json(row: Any) -> dict[str, Any]:
    return {
        "root_id": row["root_id"],
        "name": row["name"],
        "relative_dir": row["relative_dir"],
        "adopted": bool(row["adopted"]),
        "item_count": row["item_count"],
        "total_bytes": row["total_bytes"],
    }


async def list_roots(request: Request) -> JSONResponse:
    context = auth(request)
    db = request.app.state.db

    def work() -> list[dict[str, Any]]:
        rows = db.conn().execute(
            _ROOT_SELECT + " GROUP BY r.root_id ORDER BY r.name", (context.user_id,)
        )
        return [_root_json(row) for row in rows]

    return json_ok({"roots": await anyio.to_thread.run_sync(work)})


async def create_root(request: Request) -> JSONResponse:
    context = auth(request)
    body = await read_json(request)
    raw = get_str(body, "name", max_len=255)
    assert raw is not None
    name = normalize_relative_path(raw)
    if "/" in name:
        raise ApiError("bad_request", "A root name is a single folder name, without '/'.")
    db = request.app.state.db
    settings = request.app.state.settings

    def work() -> dict[str, Any]:
        with db.transaction() as tx:
            library_dir = tx.conn.execute(
                "SELECT library_dir FROM users WHERE user_id = ?", (context.user_id,)
            ).fetchone()["library_dir"]
            for row in tx.conn.execute(
                "SELECT name, relative_dir FROM roots WHERE user_id = ?", (context.user_id,)
            ):
                if row["relative_dir"] == "":
                    raise ApiError("conflict", "The whole library folder is already a root.")
                if row["name"] == name or store.roots_overlap(row["relative_dir"], name):
                    raise ApiError("conflict", "A root with that name or folder already exists.")
            folder = store.user_library_dir(settings, library_dir) / name
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                raise ApiError("bad_request", "The folder could not be created.") from None
            root_id = new_id()
            tx.conn.execute(
                "INSERT INTO roots(root_id, user_id, name, relative_dir, adopted, created_at_utc)"
                " VALUES (?,?,?,?,0,?)",
                (root_id, context.user_id, name, name, clock.to_iso(clock.utc_now())),
            )
        return {
            "root_id": root_id,
            "name": name,
            "relative_dir": name,
            "adopted": False,
            "item_count": 0,
            "total_bytes": 0,
        }

    return json_ok(await anyio.to_thread.run_sync(work), status=201)


async def scan_root_route(request: Request) -> JSONResponse:
    context = auth(request)
    root_id: str = request.path_params["root_id"]
    db = request.app.state.db

    def work() -> bool:
        row = (
            db.conn()
            .execute(
                "SELECT 1 FROM roots WHERE root_id = ? AND user_id = ?", (root_id, context.user_id)
            )
            .fetchone()
        )
        return row is not None

    if not await anyio.to_thread.run_sync(work):
        raise ApiError("not_found", "Unknown root.")
    library: LibraryService = request.app.state.library
    library.request_scan(root_id)
    return json_ok({"queued": True}, status=202)


async def library_status(request: Request) -> JSONResponse:
    auth(request)
    library: LibraryService = request.app.state.library
    return json_ok(await anyio.to_thread.run_sync(library.status))


ROUTES: list[BaseRoute] = [
    Route("/api/v1/roots", list_roots, methods=["GET"]),
    Route("/api/v1/roots", create_root, methods=["POST"]),
    Route("/api/v1/roots/{root_id}/scan", scan_root_route, methods=["POST"]),
    Route("/api/v1/library/status", library_status, methods=["GET"]),
]
