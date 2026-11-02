"""API errors and the exception handlers that turn them into JSON bodies."""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

DEFAULT_STATUS: dict[str, int] = {
    "unauthorized": 401,
    "forbidden": 403,
    "not_found": 404,
    "bad_request": 400,
    "conflict": 409,
    "path_taken": 409,
    "quota_exceeded": 413,
    "bad_hash": 422,
    "rate_limited": 429,
    "range_not_satisfiable": 416,
}

_CODE_FOR_STATUS: dict[int, str] = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "quota_exceeded",
    416: "range_not_satisfiable",
    422: "bad_hash",
    429: "rate_limited",
}


class ApiError(Exception):
    """An error reported to the client as `{"error": {"code", "message"}}`."""

    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status if status is not None else DEFAULT_STATUS.get(code, 400)


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return error_response(exc.code, exc.message, exc.status)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Give Starlette's own 404 and 405 (and other) errors the same body shape."""
    assert isinstance(exc, HTTPException)
    if exc.status_code == 404:
        return error_response("not_found", "Not found.", 404)
    code = _CODE_FOR_STATUS.get(exc.status_code, "bad_request")
    message = "Method not allowed." if exc.status_code == 405 else str(exc.detail)
    response = error_response(code, message, exc.status_code)
    if exc.headers:
        response.headers.update(exc.headers)
    return response
