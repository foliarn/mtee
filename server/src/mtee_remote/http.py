"""Small request helpers shared by the route modules."""

from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from mtee_remote.errors import ApiError


async def read_json(request: Request) -> dict[str, Any]:
    """Read the request body as a JSON object, or raise 400 `bad_request`."""
    raw = await request.body()
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ApiError("bad_request", "The body must be a JSON object.") from None
    if not isinstance(body, dict):
        raise ApiError("bad_request", "The body must be a JSON object.")
    return body


def get_str(
    body: dict[str, Any], key: str, *, max_len: int = 500, required: bool = True
) -> str | None:
    value = body.get(key)
    if value is None:
        if required:
            raise ApiError("bad_request", f"The field '{key}' is required.")
        return None
    if not isinstance(value, str):
        raise ApiError("bad_request", f"The field '{key}' must be a string.")
    if required and not value:
        raise ApiError("bad_request", f"The field '{key}' must not be empty.")
    if len(value) > max_len:
        raise ApiError("bad_request", f"The field '{key}' is longer than {max_len} characters.")
    return value


def get_int(
    body: dict[str, Any], key: str, *, required: bool = True, minimum: int | None = None
) -> int | None:
    value = body.get(key)
    if value is None:
        if required:
            raise ApiError("bad_request", f"The field '{key}' is required.")
        return None
    # bool is a subclass of int in Python; a JSON true is not a number here.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError("bad_request", f"The field '{key}' must be an integer.")
    if minimum is not None and value < minimum:
        raise ApiError("bad_request", f"The field '{key}' must be at least {minimum}.")
    return value


def get_bool(body: dict[str, Any], key: str, default: bool) -> bool:
    value = body.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ApiError("bad_request", f"The field '{key}' must be true or false.")
    return value


def json_ok(data: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status)
