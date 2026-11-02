"""Device routes: list and revoke the signed-in user's devices (milestone 124.3).

The cursor route of milestone 124.6 is added to this module later.
"""

from __future__ import annotations

from typing import Any

import anyio.to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from mtee_remote import clock
from mtee_remote.db import Database
from mtee_remote.errors import ApiError
from mtee_remote.http import json_ok
from mtee_remote.security import auth


def _list_devices(db: Database, user_id: str, current_device_id: str) -> list[dict[str, Any]]:
    rows = (
        db.conn()
        .execute(
            "SELECT device_id, name, kind, created_at_utc, last_seen_utc FROM devices"
            " WHERE user_id = ? AND revoked_at_utc IS NULL"
            " ORDER BY created_at_utc, device_id",
            (user_id,),
        )
        .fetchall()
    )
    return [
        {
            "device_id": row["device_id"],
            "name": row["name"],
            "kind": row["kind"],
            "created_at_utc": row["created_at_utc"],
            "last_seen_utc": row["last_seen_utc"],
            "current": row["device_id"] == current_device_id,
        }
        for row in rows
    ]


async def list_devices(request: Request) -> JSONResponse:
    context = auth(request)
    db: Database = request.app.state.db
    devices = await anyio.to_thread.run_sync(_list_devices, db, context.user_id, context.device_id)
    return json_ok({"devices": devices})


def _revoke_device(db: Database, user_id: str, device_id: str) -> bool:
    """Revoke one of the user's live devices; return False if there is no such device."""
    with db.transaction() as tx:
        cursor = tx.conn.execute(
            "UPDATE devices SET revoked_at_utc = ?"
            " WHERE device_id = ? AND user_id = ? AND revoked_at_utc IS NULL",
            (clock.to_iso(clock.utc_now()), device_id, user_id),
        )
        return cursor.rowcount == 1


async def revoke_device(request: Request) -> Response:
    context = auth(request)
    device_id: str = request.path_params["device_id"]
    db: Database = request.app.state.db
    revoked = await anyio.to_thread.run_sync(_revoke_device, db, context.user_id, device_id)
    if not revoked:
        raise ApiError("not_found", "No such device.")
    return Response(status_code=204)


ROUTES: list[BaseRoute] = [
    Route("/api/v1/devices", list_devices, methods=["GET"]),
    Route("/api/v1/devices/{device_id}", revoke_device, methods=["DELETE"]),
]
