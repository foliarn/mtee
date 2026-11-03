"""Stream, signed stream and cover routes (plan 127.2).

- `GET /api/v1/items/{id}/stream?level=&codecs=`: the item at a level, with the device token.
- `POST /api/v1/items/{id}/stream-url`: a signed path for players that cannot send headers.
- `GET /api/v1/s/{token}`: the stream of a signed path. It is public for the middleware; the
  token is checked here, and the device and user must still be allowed.
- `GET /api/v1/items/{id}/cover?size=s|m|l`: the album cover at 128, 512 or 1200 px.
- `POST /api/v1/items/{id}/prepare?level=&codecs=`: starts the transcode in the background, so
  it is cached before the stream is asked for (plan 127.4 decision). 200 when the file is
  ready, 202 while it is being made, 429 when the user has 8 prepares pending.

A client that disconnects while a transcode is pending gets status 499 (nobody reads it), and the
transcode stops when no other request waits for it (see `streaming/cache.py`). A prepare holds
its own waiter, so it is not stopped when its request ends.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import anyio.to_thread
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Route

from mtee_remote import clock
from mtee_remote.config import Settings
from mtee_remote.db import Database
from mtee_remote.errors import ApiError
from mtee_remote.http import json_ok, read_json
from mtee_remote.library import store
from mtee_remote.paths import disk_path
from mtee_remote.routes.items import media_type_for
from mtee_remote.security import auth
from mtee_remote.streaming import covers, levels
from mtee_remote.streaming.cache import TranscodeCache
from mtee_remote.streaming.signed import Claims, SignedUrls
from mtee_remote.streaming.source_info import source_info
from mtee_remote.streaming.transcode import TranscodeError
from mtee_remote.streaming.types import LEVELS, DeliveryPlan, Level, SourceInfo

log = logging.getLogger(__name__)

DEFAULT_TTL_S = 21600
MIN_TTL_S = 60
MAX_TTL_S = 86400
DISCONNECT_POLL_S = 1.0
CLIENT_CLOSED = 499
STREAM_CACHE_CONTROL = "private, max-age=86400"
COVER_CACHE_CONTROL = "private, max-age=604800"
DEFAULT_COVER_SIZE = "m"
PREPARE_LIMIT = 8
_OPUS_OUTPUT_RATE = 48000

# The background prepares of the server: task -> (user id, (SHA-256, plan key)). A task is kept
# here until it is done, so it is not garbage-collected. Created in `create_app`.
PrepareMap = dict[asyncio.Task[None], tuple[str, tuple[str, str]]]


class _ClientGoneError(Exception):
    """The client left while its transcode was pending."""


@dataclass(frozen=True, slots=True)
class _Prepared:
    path: Path
    sha256: str | None
    info: SourceInfo | None
    plan: DeliveryPlan


def _unauthorized() -> ApiError:
    return ApiError("unauthorized", "A valid device token is required.")


def _level_and_codecs(request: Request) -> tuple[Level, frozenset[str]]:
    """The `level` and `codecs` query values; bad values answer 400."""
    level = levels.parse_level(request.query_params.get("level", "original"))
    codecs = levels.parse_codecs(request.query_params.get("codecs", ""))
    return level, codecs


def _lossless_cap(cfg: dict[str, Any]) -> tuple[int, int] | None:
    cap = cfg.get("lossless_cap")
    if not cap:
        return None
    return int(cap["sample_rate"]), int(cap["bit_depth"])


def _plan(
    info: SourceInfo | None,
    relative: str,
    level: Level,
    codecs: frozenset[str],
    cfg: dict[str, Any],
) -> DeliveryPlan:
    if info is None:
        # The probe could not read the file: only the original can still be sent.
        if level != "original":
            raise ApiError("conflict", "The file could not be read as audio.")
        return DeliveryPlan.original(media_type_for(relative), "")
    return levels.plan(
        info,
        level,
        codecs,
        wav_to_flac=bool(cfg["wav_to_flac"]),
        lossless_cap=_lossless_cap(cfg),
    )


def _check_device(conn: Any, user_id: str, device_id: str) -> None:
    """A signed URL works only while its device is not revoked and its user not disabled."""
    row = conn.execute(
        "SELECT 1 FROM devices d JOIN users u ON u.user_id = d.user_id"
        " WHERE d.device_id = ? AND d.user_id = ? AND d.revoked_at_utc IS NULL AND u.disabled = 0",
        (device_id, user_id),
    ).fetchone()
    if row is None:
        raise _unauthorized()


def _prepare(
    conn: Any,
    settings: Settings,
    cfg: dict[str, Any],
    *,
    user_id: str,
    item_id: str,
    level: Level,
    codecs: frozenset[str],
    device_id: str | None,
) -> _Prepared:
    """Find the item and decide the plan (worker thread). `device_id` is set for signed URLs."""
    if device_id is not None:
        _check_device(conn, user_id, device_id)
    try:
        row = store.get_present_item(conn, user_id, item_id)
    except ApiError:
        if device_id is not None:
            raise _unauthorized() from None
        raise
    relative: str = row["relative_path"]
    path = disk_path(store.root_path(settings, conn, row["root_id"]), relative)
    if not path.is_file():
        raise ApiError("not_found", "The file is not available.")
    try:
        info: SourceInfo | None = source_info(path, row["metadata_json"])
    except RuntimeError:
        info = None
    plan = _plan(info, relative, level, codecs, cfg)
    return _Prepared(path=path, sha256=row["sha256"], info=info, plan=plan)


def _delivery_headers(info: SourceInfo | None, plan: DeliveryPlan) -> dict[str, str]:
    """The codec, rate, depth and bitrate that are delivered; a value that is unknown is omitted.

    A lossy output has no bit depth. Opus is always decoded at 48 kHz. A FLAC transcode that
    keeps the source's rate or depth reports the source's values.
    """
    if plan.send_original:
        codec = info.codec if info else None
        rate = info.sample_rate if info else None
        depth = info.bit_depth if info else None
        bitrate = info.bitrate if info else None
    else:
        codec = plan.codec
        bitrate = plan.bitrate
        source_rate = info.sample_rate if info else None
        if plan.codec == "opus":
            rate = _OPUS_OUTPUT_RATE
        else:
            rate = plan.sample_rate if plan.sample_rate is not None else source_rate
        depth = None
        if plan.codec == "flac":
            depth = (
                plan.bit_depth if plan.bit_depth is not None else (info.bit_depth if info else None)
            )
    values: dict[str, object] = {
        "X-MTEE-Codec": codec,
        "X-MTEE-Sample-Rate": rate,
        "X-MTEE-Bit-Depth": depth,
        "X-MTEE-Bitrate": bitrate,
    }
    return {name: str(value) for name, value in values.items() if value is not None}


async def _cached(request: Request, source: Path, sha256: str, plan: DeliveryPlan) -> Path:
    """Return the complete transcode, waiting for it. Cancels it when the client leaves."""
    cache: TranscodeCache = request.app.state.transcodes
    task = asyncio.ensure_future(cache.ensure(source, sha256, plan))
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=DISCONNECT_POLL_S)
            if not task.done() and await request.is_disconnected():
                task.cancel()
                await asyncio.wait({task})
                raise _ClientGoneError()
        return task.result()
    except (TranscodeError, RuntimeError) as error:
        log.warning("Transcode of %s failed: %s", source.name, error)
        raise ApiError("conversion_failed", "The file could not be converted.", 500) from error
    finally:
        if not task.done():
            task.cancel()


async def _resolve(
    request: Request,
    *,
    user_id: str,
    item_id: str,
    level: Level,
    codecs: frozenset[str],
    device_id: str | None = None,
) -> _Prepared:
    """The item, its path and its plan, for a stream or a prepare (worker thread)."""
    app = request.app
    settings: Settings = app.state.settings
    db: Database = app.state.db
    cfg: dict[str, Any] = app.state.streaming_settings

    def work() -> _Prepared:
        return _prepare(
            db.conn(),
            settings,
            cfg,
            user_id=user_id,
            item_id=item_id,
            level=level,
            codecs=codecs,
            device_id=device_id,
        )

    return await anyio.to_thread.run_sync(work)


def _transcode_hash(prepared: _Prepared) -> str:
    """The SHA-256 that keys a transcode. Without one the file is still being analysed."""
    if prepared.sha256 is None:
        raise ApiError("conflict", "The file is still being analysed; try again in a moment.")
    return prepared.sha256


async def _serve(
    request: Request,
    *,
    user_id: str,
    item_id: str,
    level: Level,
    codecs: frozenset[str],
    device_id: str | None = None,
) -> Response:
    prepared = await _resolve(
        request,
        user_id=user_id,
        item_id=item_id,
        level=level,
        codecs=codecs,
        device_id=device_id,
    )
    plan = prepared.plan
    source = prepared.path
    if not plan.send_original:
        try:
            source = await _cached(request, source, _transcode_hash(prepared), plan)
        except _ClientGoneError:
            return Response(status_code=CLIENT_CLOSED)
    headers = _delivery_headers(prepared.info, plan)
    if prepared.sha256 is not None:
        headers["ETag"] = f'"{prepared.sha256}-{plan.key}"'
    headers["Cache-Control"] = STREAM_CACHE_CONTROL
    return FileResponse(source, media_type=plan.mime, headers=headers)


async def stream_item(request: Request) -> Response:
    """`GET /api/v1/items/{id}/stream?level=&codecs=`. Bad values answer 400."""
    context = auth(request)
    item_id: str = request.path_params["item_id"]
    level, codecs = _level_and_codecs(request)
    return await _serve(
        request, user_id=context.user_id, item_id=item_id, level=level, codecs=codecs
    )


async def _prepare_in_background(
    cache: TranscodeCache, source: Path, sha256: str, plan: DeliveryPlan
) -> None:
    """Hold a waiter in the cache until the transcode is complete. Errors are logged only."""
    try:
        await cache.ensure(source, sha256, plan)
    except Exception as error:
        log.warning("Prepare of %s failed: %s", source.name, error)


def _start_prepare(
    app: Starlette,
    *,
    user_id: str,
    source: Path,
    sha256: str,
    plan: DeliveryPlan,
) -> None:
    """Start the transcode in a task that outlives the request.

    The same transcode already being prepared is not started twice. A user may have at most
    `PREPARE_LIMIT` prepares pending, else 429.
    """
    prepares: PrepareMap = app.state.prepares
    key = (sha256, plan.key)
    if any(pending == key for _owner, pending in prepares.values()):
        return
    if sum(1 for owner, _pending in prepares.values() if owner == user_id) >= PREPARE_LIMIT:
        raise ApiError(
            "rate_limited", "Too many files are being prepared. Try again when some are ready."
        )
    cache: TranscodeCache = app.state.transcodes
    task = asyncio.create_task(_prepare_in_background(cache, source, sha256, plan))
    prepares[task] = (user_id, key)
    task.add_done_callback(lambda done: prepares.pop(done, None))


async def prepare_item(request: Request) -> JSONResponse:
    """`POST /api/v1/items/{id}/prepare?level=&codecs=`: start the transcode without waiting.

    200 `{"ready": true, "transcode": false}` for the original, 200 `{"ready": true,
    "transcode": true}` when the transcode is cached, else 202 `{"ready": false,
    "transcode": true}`. The item must be the caller's, else 404; a pending hash answers 409.
    """
    context = auth(request)
    item_id: str = request.path_params["item_id"]
    level, codecs = _level_and_codecs(request)
    prepared = await _resolve(
        request, user_id=context.user_id, item_id=item_id, level=level, codecs=codecs
    )
    plan = prepared.plan
    if plan.send_original:
        return json_ok({"ready": True, "transcode": False})
    sha256 = _transcode_hash(prepared)
    cache: TranscodeCache = request.app.state.transcodes
    if cache.path_for(sha256, plan).is_file():
        return json_ok({"ready": True, "transcode": True})
    _start_prepare(
        request.app, user_id=context.user_id, source=prepared.path, sha256=sha256, plan=plan
    )
    return json_ok({"ready": False, "transcode": True}, status=202)


def _url_options(body: dict[str, Any]) -> tuple[Level, frozenset[str], int]:
    unknown = sorted(set(body) - {"level", "codecs", "ttl_seconds"})
    if unknown:
        raise ApiError("bad_request", f"Unknown field '{unknown[0]}'.")
    raw_level = body.get("level", "original")
    if not isinstance(raw_level, str):
        raise ApiError("bad_request", "The field 'level' must be a string.")
    level = levels.parse_level(raw_level)
    raw_codecs = body.get("codecs")
    if raw_codecs is None:
        codecs: frozenset[str] = frozenset()
    elif isinstance(raw_codecs, str):
        codecs = levels.parse_codecs(raw_codecs)
    elif isinstance(raw_codecs, list) and all(isinstance(code, str) for code in raw_codecs):
        codecs = levels.parse_codecs(",".join(cast(list[str], raw_codecs)))
    else:
        raise ApiError("bad_request", "The field 'codecs' must be a list of codec names.")
    ttl = body.get("ttl_seconds", DEFAULT_TTL_S)
    if isinstance(ttl, bool) or not isinstance(ttl, int) or not MIN_TTL_S <= ttl <= MAX_TTL_S:
        raise ApiError(
            "bad_request",
            f"The field 'ttl_seconds' must be a whole number from {MIN_TTL_S} to {MAX_TTL_S}.",
        )
    return level, codecs, ttl


async def create_stream_url(request: Request) -> JSONResponse:
    """`POST /api/v1/items/{id}/stream-url`, body `{level?, codecs?, ttl_seconds?}`.

    `codecs` is a list of codec names (or a comma-separated text). `ttl_seconds` is 60 to 86400
    (default 21600). The answer's `url` is a path: join it to the server address. The item must
    be present and the caller's, else 404. The token keeps the device it was made for: it stops
    working when that device is revoked.
    """
    context = auth(request)
    item_id: str = request.path_params["item_id"]
    level, codecs, ttl = _url_options(await read_json(request))
    signer: SignedUrls = request.app.state.stream_urls
    db: Database = request.app.state.db
    expires = int(clock.utc_now().timestamp()) + ttl

    def work() -> str:
        store.get_present_item(db.conn(), context.user_id, item_id)
        return signer.sign(
            Claims(
                item_id=item_id,
                user_id=context.user_id,
                device_id=context.device_id,
                level=level,
                codecs=codecs,
                expires=expires,
            )
        )

    token = await anyio.to_thread.run_sync(work)
    expires_at = clock.to_iso(datetime.fromtimestamp(expires, UTC))
    return json_ok({"url": f"/api/v1/s/{token}", "expires_at_utc": expires_at})


async def signed_stream(request: Request) -> Response:
    """`GET /api/v1/s/{token}`: the stream named by a signed token. Any failure answers 401."""
    token: str = request.path_params["token"]
    signer: SignedUrls = request.app.state.stream_urls
    claims = await anyio.to_thread.run_sync(signer.verify, token)
    if claims is None or claims.level not in LEVELS:
        raise _unauthorized()
    level = cast(Level, claims.level)
    return await _serve(
        request,
        user_id=claims.user_id,
        item_id=claims.item_id,
        level=level,
        codecs=claims.codecs,
        device_id=claims.device_id,
    )


def _cover_size(request: Request) -> int:
    size = request.query_params.get("size", DEFAULT_COVER_SIZE)
    if size not in covers.COVER_SIZES:
        raise ApiError("bad_request", "The size must be one of: s, m, l.")
    return covers.COVER_SIZES[size]


async def get_cover(request: Request) -> FileResponse:
    """`GET /api/v1/items/{id}/cover?size=s|m|l`: a JPEG, never larger than the source."""
    context = auth(request)
    item_id: str = request.path_params["item_id"]
    px = _cover_size(request)
    settings: Settings = request.app.state.settings
    db: Database = request.app.state.db
    cache_dir = settings.data_dir / "cache" / "covers"

    def work() -> tuple[Path, str]:
        conn = db.conn()
        row = store.get_present_item(conn, context.user_id, item_id)
        path = disk_path(store.root_path(settings, conn, row["root_id"]), row["relative_path"])
        if not path.is_file():
            raise ApiError("not_found", "The file is not available.")
        key: str = row["sha256"] or f"{item_id}-{row['revision']}"
        try:
            found = covers.cover_file(cache_dir, path, key, px)
        except RuntimeError as error:
            log.warning("Cover of %s failed: %s", path.name, error)
            raise ApiError("conversion_failed", "The cover could not be prepared.", 500) from error
        if found is None:
            raise ApiError("not_found", "The item has no cover.")
        return found, key

    final, key = await anyio.to_thread.run_sync(work)
    return FileResponse(
        final,
        media_type="image/jpeg",
        headers={"ETag": f'"{key}-{px}"', "Cache-Control": COVER_CACHE_CONTROL},
    )


ROUTES: list[BaseRoute] = [
    Route("/api/v1/items/{item_id}/stream", stream_item, methods=["GET"]),
    Route("/api/v1/items/{item_id}/stream-url", create_stream_url, methods=["POST"]),
    Route("/api/v1/s/{token}", signed_stream, methods=["GET"]),
    Route("/api/v1/items/{item_id}/cover", get_cover, methods=["GET"]),
    Route("/api/v1/items/{item_id}/prepare", prepare_item, methods=["POST"]),
]
