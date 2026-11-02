"""Administration routes: users and quotas (milestone 124.3).

Every route here needs an administrator. Deleting a user removes the account only: the
library folder and every file in it stay where they are (files are never deleted, and in
Docker a rename between mounts would fail).
"""

from __future__ import annotations

from typing import Any

import anyio.to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from mtee_remote.config import Settings
from mtee_remote.db import Database
from mtee_remote.errors import ApiError
from mtee_remote.http import get_bool, get_int, get_str, json_ok, read_json
from mtee_remote.passwords import MAX_PASSWORD_LENGTH
from mtee_remote.security import require_admin
from mtee_remote.users import create_user_row, user_public


def _required_text(body: dict[str, Any], key: str, max_len: int) -> str:
    value = get_str(body, key, max_len=max_len)
    if value is None:  # get_str raises for a missing required field; kept for the type checker
        raise ApiError("bad_request", f"The field '{key}' is required.")
    return value


def _flag(body: dict[str, Any], key: str) -> bool:
    if body[key] is None:
        raise ApiError("bad_request", f"The field '{key}' must be true or false.")
    return get_bool(body, key, False)


def _list_users(db: Database) -> list[dict[str, Any]]:
    rows = db.conn().execute("SELECT * FROM users ORDER BY username").fetchall()
    return [user_public(row) for row in rows]


async def list_users(request: Request) -> JSONResponse:
    require_admin(request)
    db: Database = request.app.state.db
    users = await anyio.to_thread.run_sync(_list_users, db)
    return json_ok({"users": users})


async def create_user(request: Request) -> JSONResponse:
    require_admin(request)
    body = await read_json(request)
    username = _required_text(body, "username", 100)
    password = _required_text(body, "password", MAX_PASSWORD_LENGTH)
    is_admin = get_bool(body, "is_admin", False)
    quota_bytes = get_int(body, "quota_bytes", required=False, minimum=0)
    db: Database = request.app.state.db
    settings: Settings = request.app.state.settings

    def create() -> dict[str, Any]:
        with db.transaction() as tx:
            user_id = create_user_row(
                tx,
                settings,
                username=username,
                password=password,
                is_admin=is_admin,
                quota_bytes=quota_bytes,
            )
            row = tx.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return user_public(row)

    created = await anyio.to_thread.run_sync(create)
    return json_ok(created, 201)


async def patch_user(request: Request) -> JSONResponse:
    context = require_admin(request)
    user_id: str = request.path_params["user_id"]
    body = await read_json(request)
    changes: dict[str, Any] = {}
    if "disabled" in body:
        changes["disabled"] = int(_flag(body, "disabled"))
    if "is_admin" in body:
        changes["is_admin"] = int(_flag(body, "is_admin"))
    if "quota_bytes" in body:
        changes["quota_bytes"] = get_int(body, "quota_bytes", required=False, minimum=0)
    if user_id == context.user_id and (
        changes.get("disabled") == 1 or changes.get("is_admin") == 0
    ):
        raise ApiError("bad_request", "You cannot disable or demote your own account.")
    if not changes:
        raise ApiError("bad_request", "No field to change was given.")
    db: Database = request.app.state.db

    def patch() -> dict[str, Any]:
        with db.transaction() as tx:
            exists = tx.conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if exists is None:
                raise ApiError("not_found", "No such user.")
            # The column names come from the fixed keys above, never from the request.
            assignments = ", ".join(f"{column} = ?" for column in changes)
            tx.conn.execute(
                f"UPDATE users SET {assignments} WHERE user_id = ?",
                (*changes.values(), user_id),
            )
            row = tx.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return user_public(row)

    updated = await anyio.to_thread.run_sync(patch)
    return json_ok(updated)


def _delete_user(db: Database, settings: Settings, user_id: str, confirm: str) -> str | None:
    """Delete the user row; return the library folder name when it exists (it is kept)."""
    with db.transaction() as tx:
        row = tx.conn.execute(
            "SELECT username, library_dir FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise ApiError("not_found", "No such user.")
        if confirm != row["username"]:
            raise ApiError("bad_request", "Type the user name to confirm the deletion.")
        tx.conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        folder = settings.music_dir / row["library_dir"]
        return row["library_dir"] if folder.is_dir() else None


async def delete_user(request: Request) -> JSONResponse:
    context = require_admin(request)
    user_id: str = request.path_params["user_id"]
    if user_id == context.user_id:
        raise ApiError("bad_request", "You cannot delete your own account.")
    confirm = request.query_params.get("confirm", "")
    db: Database = request.app.state.db
    settings: Settings = request.app.state.settings
    kept = await anyio.to_thread.run_sync(_delete_user, db, settings, user_id, confirm)
    return json_ok({"library_folder_kept": kept})


ROUTES: list[BaseRoute] = [
    Route("/api/v1/admin/users", list_users, methods=["GET"]),
    Route("/api/v1/admin/users", create_user, methods=["POST"]),
    Route("/api/v1/admin/users/{user_id}", patch_user, methods=["PATCH"]),
    Route("/api/v1/admin/users/{user_id}", delete_user, methods=["DELETE"]),
]
