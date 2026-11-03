"""Records routes: play log, playlists, track data and synced settings (milestone 126.7).

The rules live in `mtee_remote/records.py`. Every route works on the caller's own records.
"""

from __future__ import annotations

import re
from typing import Any

import anyio.to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from mtee_remote import records
from mtee_remote.db import Database
from mtee_remote.errors import ApiError
from mtee_remote.http import get_int, json_ok, read_json
from mtee_remote.security import auth

DEFAULT_LIMIT = 500
MAX_LIMIT = 1000
MAX_INT = 2**63 - 1
_DIGITS = re.compile(r"[0-9]+")


def _int_query(request: Request, name: str, minimum: int, maximum: int) -> int | None:
    """An optional whole-number query parameter; None when it is absent."""
    raw = request.query_params.get(name)
    if raw is None:
        return None
    if _DIGITS.fullmatch(raw) is None:
        raise ApiError("bad_request", f"The query parameter '{name}' must be a whole number.")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ApiError(
            "bad_request", f"The query parameter '{name}' must be from {minimum} to {maximum}."
        )
    return value


async def post_play_events(request: Request) -> JSONResponse:
    """`POST /api/v1/records/play-events` `{events: [...]}`: store new events, skip known ones."""
    context = auth(request)
    body = await read_json(request)
    events: Any = body.get("events")
    db: Database = request.app.state.db

    def work() -> dict[str, int]:
        return records.add_play_events(db, context.user_id, context.device_id, events)

    return json_ok(await anyio.to_thread.run_sync(work))


async def list_play_events(request: Request) -> JSONResponse:
    """`GET /api/v1/records/play-events?since=&limit=`: the events after a sequence number."""
    context = auth(request)
    since = _int_query(request, "since", 0, MAX_INT) or 0
    limit = _int_query(request, "limit", 1, MAX_LIMIT) or DEFAULT_LIMIT
    db: Database = request.app.state.db

    def work() -> dict[str, Any]:
        return records.list_play_events(db, context.user_id, since, limit)

    return json_ok(await anyio.to_thread.run_sync(work))


async def list_playlists(request: Request) -> JSONResponse:
    context = auth(request)
    db: Database = request.app.state.db

    def work() -> list[dict[str, Any]]:
        return records.list_playlists(db, context.user_id)

    return json_ok({"playlists": await anyio.to_thread.run_sync(work)})


async def get_playlist(request: Request) -> JSONResponse:
    context = auth(request)
    playlist_id: str = request.path_params["playlist_id"]
    db: Database = request.app.state.db

    def work() -> dict[str, Any]:
        return records.get_playlist(db, context.user_id, playlist_id)

    return json_ok(await anyio.to_thread.run_sync(work))


async def put_playlist(request: Request) -> JSONResponse:
    """`PUT /api/v1/records/playlists/{id}` `{name, entries, base_revision}`: whole playlist."""
    context = auth(request)
    playlist_id: str = request.path_params["playlist_id"]
    body = await read_json(request)
    base_revision = get_int(body, "base_revision", required=False, minimum=0)
    db: Database = request.app.state.db

    def work() -> dict[str, Any]:
        return records.put_playlist(
            db,
            context.user_id,
            context.device_id,
            playlist_id,
            name=body.get("name"),
            entries=body.get("entries"),
            base_revision=base_revision,
        )

    return json_ok(await anyio.to_thread.run_sync(work))


async def delete_playlist(request: Request) -> JSONResponse:
    """`DELETE /api/v1/records/playlists/{id}?base_revision=N`: mark the playlist deleted."""
    context = auth(request)
    playlist_id: str = request.path_params["playlist_id"]
    base_revision = _int_query(request, "base_revision", 0, MAX_INT)
    if base_revision is None:
        raise ApiError("bad_request", "The query parameter 'base_revision' is required.")
    db: Database = request.app.state.db

    def work() -> dict[str, Any]:
        return records.delete_playlist(
            db, context.user_id, context.device_id, playlist_id, base_revision
        )

    return json_ok(await anyio.to_thread.run_sync(work))


async def get_track_data(request: Request) -> JSONResponse:
    context = auth(request)
    item_id: str = request.path_params["item_id"]
    db: Database = request.app.state.db

    def work() -> dict[str, Any]:
        return records.get_track_data(db, context.user_id, item_id)

    return json_ok(await anyio.to_thread.run_sync(work))


async def put_track_data(request: Request) -> JSONResponse:
    """`PUT /api/v1/records/track-data/{item_id}` `{analysis?, loudness?, corrections?}`."""
    context = auth(request)
    item_id: str = request.path_params["item_id"]
    body = await read_json(request)
    db: Database = request.app.state.db

    def work() -> dict[str, Any]:
        return records.put_track_data(db, context.user_id, item_id, body)

    return json_ok(await anyio.to_thread.run_sync(work))


async def get_settings(request: Request) -> JSONResponse:
    context = auth(request)
    db: Database = request.app.state.db

    def work() -> dict[str, Any]:
        return records.get_settings(db, context.user_id)

    return json_ok({"settings": await anyio.to_thread.run_sync(work)})


async def put_settings(request: Request) -> JSONResponse:
    """`PUT /api/v1/records/settings` `{key: value, ...}`; `null` deletes a key."""
    context = auth(request)
    body = await read_json(request)
    db: Database = request.app.state.db

    def work() -> dict[str, Any]:
        return records.put_settings(db, context.user_id, body)

    return json_ok({"settings": await anyio.to_thread.run_sync(work)})


ROUTES: list[BaseRoute] = [
    Route("/api/v1/records/play-events", post_play_events, methods=["POST"]),
    Route("/api/v1/records/play-events", list_play_events, methods=["GET"]),
    Route("/api/v1/records/playlists", list_playlists, methods=["GET"]),
    Route("/api/v1/records/playlists/{playlist_id}", get_playlist, methods=["GET"]),
    Route("/api/v1/records/playlists/{playlist_id}", put_playlist, methods=["PUT"]),
    Route("/api/v1/records/playlists/{playlist_id}", delete_playlist, methods=["DELETE"]),
    Route("/api/v1/records/track-data/{item_id}", get_track_data, methods=["GET"]),
    Route("/api/v1/records/track-data/{item_id}", put_track_data, methods=["PUT"]),
    Route("/api/v1/records/settings", get_settings, methods=["GET"]),
    Route("/api/v1/records/settings", put_settings, methods=["PUT"]),
]
