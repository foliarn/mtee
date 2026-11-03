"""Resumable upload routes (milestone 124.5). The rules live in `mtee_remote/uploads.py`."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, BinaryIO

import anyio
import anyio.to_thread
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from mtee_remote import backups, uploads
from mtee_remote.db import Database
from mtee_remote.errors import ApiError, error_response, file_operation
from mtee_remote.http import get_int, get_str, json_ok, read_json
from mtee_remote.library.service import LibraryService
from mtee_remote.security import auth

log = logging.getLogger(__name__)

BATCH_BYTES = 1024 * 1024
_CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)")


def _parse_content_range(header: str | None) -> tuple[int, int, int]:
    match = _CONTENT_RANGE.fullmatch((header or "").strip())
    if match is None:
        raise ApiError("bad_request", "A Content-Range header 'bytes START-END/TOTAL' is required.")
    start, end, total = (int(group) for group in match.groups())
    if start > end or end >= total:
        raise ApiError("bad_request", "The Content-Range values are not consistent.")
    return start, end, total


async def create_upload(request: Request) -> JSONResponse:
    context = auth(request)
    body = await read_json(request)
    purpose = get_str(body, "purpose", max_len=32)
    sha256 = get_str(body, "sha256", max_len=64)
    size_bytes = get_int(body, "size_bytes", minimum=0)
    assert purpose is not None and sha256 is not None and size_bytes is not None
    db: Database = request.app.state.db
    settings = request.app.state.settings

    if purpose == "backup":
        # A backup has no root, path or base item: refuse those fields rather than ignore them.
        for key in ("root_id", "relative_path", "base_item_id", "base_revision", "mode"):
            if key in body:
                raise ApiError("bad_request", f"A backup upload takes no '{key}' field.")
        label = get_str(body, "label", max_len=uploads.BACKUP_LABEL_MAX, required=False)
        kind = get_str(body, "kind", max_len=16, required=False)

        def work_backup() -> dict[str, Any]:
            return uploads.create_backup_upload(
                db,
                settings,
                user_id=context.user_id,
                device_id=context.device_id,
                size_bytes=size_bytes,
                sha256=sha256,
                label=label,
                kind="manual" if kind is None else kind,
            )

        return json_ok(await anyio.to_thread.run_sync(work_backup), 201)

    root_id = get_str(body, "root_id", max_len=64)
    relative_path = get_str(body, "relative_path", max_len=1100)
    base_item_id = get_str(body, "base_item_id", max_len=64, required=False)
    base_revision = get_int(body, "base_revision", required=False, minimum=1)
    assert root_id is not None and relative_path is not None
    splice = _read_splice(body)

    def work() -> dict[str, Any]:
        return uploads.create_upload(
            db,
            settings,
            user_id=context.user_id,
            device_id=context.device_id,
            purpose=purpose,
            root_id=root_id,
            relative_path=relative_path,
            size_bytes=size_bytes,
            sha256=sha256,
            base_item_id=base_item_id,
            base_revision=base_revision,
            splice=splice,
        )

    return json_ok(await anyio.to_thread.run_sync(work), 201)


def _read_splice(body: dict[str, Any]) -> uploads.SpliceMeta | None:
    """Read the optional tags-only mode of a create request (plan 129.2).

    `mode` is "splice" or "full" (the default). A splice names the length and SHA-256 of the
    audio payload the server already holds and how many of the bytes sent come before it.
    """
    mode = get_str(body, "mode", max_len=16, required=False)
    splice_keys = ("span_length", "span_sha256", "prefix_size")
    if mode in (None, "full"):
        for key in splice_keys:
            if key in body:
                raise ApiError("bad_request", f"The field '{key}' needs mode 'splice'.")
        return None
    if mode != "splice":
        raise ApiError("bad_request", "The mode must be 'full' or 'splice'.")
    span_length = get_int(body, "span_length", minimum=0)
    span_sha256 = get_str(body, "span_sha256", max_len=64)
    prefix_size = get_int(body, "prefix_size", minimum=0)
    assert span_length is not None and span_sha256 is not None and prefix_size is not None
    return uploads.SpliceMeta(span_length, span_sha256, prefix_size)


async def get_upload(request: Request) -> JSONResponse:
    context = auth(request)
    upload_id: str = request.path_params["upload_id"]
    db: Database = request.app.state.db
    settings = request.app.state.settings
    status = await anyio.to_thread.run_sync(
        uploads.upload_status, db, settings, context.user_id, upload_id
    )
    return json_ok(status)


@file_operation
def _prepare_chunk(
    db: Database, settings: Any, user_id: str, upload_id: str
) -> tuple[Path, int, int, str]:
    """Return `(part file, size_bytes, current part size, state)` of an upload."""
    conn = db.conn()
    row = uploads.load_upload(conn, user_id, upload_id)
    part = uploads.part_file(settings, conn, user_id, row["purpose"], upload_id)
    part.parent.mkdir(parents=True, exist_ok=True)
    return part, row["size_bytes"], uploads.part_size(part), row["state"]


@file_operation
def _open_part(part: Path) -> BinaryIO:
    return open(part, "ab")


def _write_batch(handle: BinaryIO, data: bytes) -> None:
    """Write a batch mid-stream; a full disk is `507`, not a 500."""
    try:
        handle.write(data)
    except OSError:
        log.exception("Writing an upload batch failed.")
        raise ApiError(
            "insufficient_storage", "The server could not write the file.", 507
        ) from None


def _finish_write(handle: BinaryIO, data: bytes) -> None:
    try:
        if data:
            handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()


async def put_chunk(request: Request) -> Response:
    """`PUT /api/v1/uploads/{id}`: append one chunk at the offset the client says."""
    context = auth(request)
    upload_id: str = request.path_params["upload_id"]
    start, end, total = _parse_content_range(request.headers.get("content-range"))
    db: Database = request.app.state.db
    settings = request.app.state.settings
    with uploads.exclusive(f"upload:{upload_id}"):
        part, size_bytes, current, state = await anyio.to_thread.run_sync(
            _prepare_chunk, db, settings, context.user_id, upload_id
        )
        if state != "open":
            raise ApiError("conflict", f"This upload is {state}; it accepts no more bytes.")
        if total != size_bytes:
            raise ApiError("bad_request", "The total in Content-Range is not the upload size.")
        if start != current:
            response = error_response(
                "range_not_satisfiable",
                f"The upload has {current} bytes; continue at that offset.",
                416,
            )
            response.headers["Upload-Offset"] = str(current)
            return response
        expected = end - start + 1
        taken = 0
        overflow = False
        received = 0
        buffer = bytearray()
        handle = await anyio.to_thread.run_sync(_open_part, part)
        try:
            try:
                async for chunk in request.stream():
                    room = expected - taken
                    if len(chunk) > room:
                        chunk = chunk[:room]
                        overflow = True
                    buffer += chunk
                    taken += len(chunk)
                    if overflow:
                        break
                    if len(buffer) >= BATCH_BYTES:
                        data = bytes(buffer)
                        buffer.clear()
                        await anyio.to_thread.run_sync(_write_batch, handle, data)
            except ClientDisconnect:
                pass  # keep what arrived; the client asks again with GET
        finally:
            # Keep what arrived, even when the client left or the request was cancelled.
            with anyio.CancelScope(shield=True):
                data = bytes(buffer)
                buffer.clear()
                try:
                    await anyio.to_thread.run_sync(_finish_write, handle, data)
                except OSError:
                    log.exception("Writing upload %s failed.", upload_id)
                    raise ApiError(
                        "insufficient_storage", "The server could not write the file.", 507
                    ) from None
                received = await anyio.to_thread.run_sync(uploads.part_size, part)
                await anyio.to_thread.run_sync(uploads.record_progress, db, upload_id, received)
        if overflow:
            raise ApiError("bad_request", "More bytes arrived than Content-Range announced.")
        return json_ok({"received_bytes": received})


async def commit_upload(request: Request) -> JSONResponse:
    context = auth(request)
    upload_id: str = request.path_params["upload_id"]
    raw = await request.body()
    new_path: str | None = None
    if raw.strip():
        body = await read_json(request)
        new_path = get_str(body, "relative_path", max_len=1100, required=False)
    db: Database = request.app.state.db
    settings = request.app.state.settings

    def work() -> dict[str, Any]:
        purpose = uploads.load_upload(db.conn(), context.user_id, upload_id)["purpose"]
        if purpose == "backup":
            return backups.commit_backup(
                db,
                settings,
                user_id=context.user_id,
                device_id=context.device_id,
                upload_id=upload_id,
                new_relative_path=new_path,
            )
        item = uploads.commit_upload(
            db,
            settings,
            user_id=context.user_id,
            device_id=context.device_id,
            upload_id=upload_id,
            new_relative_path=new_path,
        )
        return {"item": item}

    with uploads.exclusive(f"upload:{upload_id}"):
        result = await anyio.to_thread.run_sync(work)
    library: LibraryService | None = getattr(request.app.state, "library", None)
    if library is not None:
        library.wake_hasher()
    return json_ok(result)


async def cancel_upload(request: Request) -> Response:
    context = auth(request)
    upload_id: str = request.path_params["upload_id"]
    db: Database = request.app.state.db
    settings = request.app.state.settings
    with uploads.exclusive(f"upload:{upload_id}"):
        await anyio.to_thread.run_sync(
            uploads.cancel_upload, db, settings, context.user_id, upload_id
        )
    return Response(status_code=204)


ROUTES: list[BaseRoute] = [
    Route("/api/v1/uploads", create_upload, methods=["POST"]),
    Route("/api/v1/uploads/{upload_id}", get_upload, methods=["GET"]),
    Route("/api/v1/uploads/{upload_id}", put_chunk, methods=["PUT"]),
    Route("/api/v1/uploads/{upload_id}", cancel_upload, methods=["DELETE"]),
    Route("/api/v1/uploads/{upload_id}/commit", commit_upload, methods=["POST"]),
]
