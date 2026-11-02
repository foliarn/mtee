"""Change journal route with long polling, and the per-device cursor (milestone 124.6)."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from typing import Any

import anyio.to_thread
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from mtee_remote.errors import ApiError
from mtee_remote.http import get_int, json_ok, read_json
from mtee_remote.security import auth

DEFAULT_LIMIT = 500
MAX_LIMIT = 1000
MAX_WAIT_S = 30.0
MAX_SINCE = 2**63 - 1
# A waiter re-reads the journal at least this often, so a change committed just before
# the wait started is seen within a second even if its notification was missed.
WAIT_SLICE_S = 1.0

_INT_TEXT = re.compile(r"[0-9]+")
_NUMBER_TEXT = re.compile(r"[0-9]*\.?[0-9]+")


def _int_param(request: Request, name: str, default: int, minimum: int, maximum: int) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    if _INT_TEXT.fullmatch(raw) is None:
        raise ApiError("bad_request", f"The query parameter '{name}' must be an integer.")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ApiError(
            "bad_request",
            f"The query parameter '{name}' must be from {minimum} to {maximum}.",
        )
    return value


def _wait_param(request: Request) -> float:
    raw = request.query_params.get("wait")
    if raw is None:
        return 0.0
    value = math.nan if _NUMBER_TEXT.fullmatch(raw) is None else float(raw)
    if not math.isfinite(value) or not 0 <= value <= MAX_WAIT_S:
        raise ApiError(
            "bad_request", f"The query parameter 'wait' must be from 0 to {MAX_WAIT_S:g}."
        )
    return value


def _read_rows(db: Any, user_id: str, since: int, limit: int) -> list[sqlite3.Row]:
    """Read up to `limit + 1` journal rows after `since` (worker thread)."""
    rows: list[sqlite3.Row] = (
        db.conn()
        .execute(
            "SELECT seq, item_id, kind, payload_json, at_utc FROM journal"
            " WHERE user_id = ? AND seq > ? ORDER BY seq LIMIT ?",
            (user_id, since, limit + 1),
        )
        .fetchall()
    )
    return rows


def _page(rows: list[sqlite3.Row], since: int, limit: int) -> dict[str, Any]:
    more = len(rows) > limit
    returned = rows[:limit]
    changes = [
        {
            "seq": row["seq"],
            "item_id": row["item_id"],
            "kind": row["kind"],
            "payload": json.loads(row["payload_json"]),
            "at_utc": row["at_utc"],
        }
        for row in returned
    ]
    next_seq = returned[-1]["seq"] if returned else since
    return {"changes": changes, "next": next_seq, "more": more}


async def list_changes(request: Request) -> Response:
    """GET /api/v1/changes?since=N&limit=M&wait=S: the caller's journal after `since`."""
    ctx = auth(request)
    since = _int_param(request, "since", 0, 0, MAX_SINCE)
    limit = _int_param(request, "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
    wait = _wait_param(request)
    db = request.app.state.db
    notifier = request.app.state.notifier

    rows = await anyio.to_thread.run_sync(_read_rows, db, ctx.user_id, since, limit)
    if not rows and wait > 0:
        deadline = time.monotonic() + wait
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await notifier.wait(ctx.user_id, min(remaining, WAIT_SLICE_S))
            rows = await anyio.to_thread.run_sync(_read_rows, db, ctx.user_id, since, limit)
            if rows:
                break
    return json_ok(_page(rows, since, limit))


def _read_cursor(db: Any, device_id: str) -> int:
    row = (
        db.conn()
        .execute("SELECT seq FROM device_cursors WHERE device_id = ?", (device_id,))
        .fetchone()
    )
    return int(row["seq"]) if row is not None else 0


async def get_cursor(request: Request) -> Response:
    """GET /api/v1/devices/me/cursor: the sequence number this device has read up to."""
    ctx = auth(request)
    seq = await anyio.to_thread.run_sync(_read_cursor, request.app.state.db, ctx.device_id)
    return json_ok({"seq": seq})


def _store_cursor(db: Any, user_id: str, device_id: str, seq: int) -> None:
    with db.transaction() as tx:
        highest = int(
            tx.conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM journal WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
        )
        if seq > highest:
            raise ApiError(
                "bad_request",
                f"The cursor {seq} is beyond the newest change ({highest}).",
            )
        tx.conn.execute(
            "INSERT INTO device_cursors(device_id, seq) VALUES (?,?)"
            " ON CONFLICT(device_id) DO UPDATE SET seq = excluded.seq",
            (device_id, seq),
        )


async def put_cursor(request: Request) -> Response:
    """PUT /api/v1/devices/me/cursor with body {"seq": N}: store the read position."""
    ctx = auth(request)
    body = await read_json(request)
    seq = get_int(body, "seq", minimum=0)
    assert seq is not None
    await anyio.to_thread.run_sync(
        _store_cursor, request.app.state.db, ctx.user_id, ctx.device_id, seq
    )
    return Response(status_code=204)


ROUTES: list[BaseRoute] = [
    Route("/api/v1/changes", list_changes, methods=["GET"]),
    Route("/api/v1/devices/me/cursor", get_cursor, methods=["GET"]),
    Route("/api/v1/devices/me/cursor", put_cursor, methods=["PUT"]),
]
