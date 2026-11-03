"""API errors and the exception handlers that turn them into JSON bodies."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger(__name__)

BUSY_MESSAGE = "The file is in use on the server; try again in a moment."
FILE_ERROR_MESSAGE = "The server could not complete the file operation."
# Windows error codes of a file that another process holds open (sharing or lock violation).
_BUSY_WINERRORS = frozenset({32, 33})

DEFAULT_STATUS: dict[str, int] = {
    "unauthorized": 401,
    "forbidden": 403,
    "not_found": 404,
    "bad_request": 400,
    "conflict": 409,
    "path_taken": 409,
    "busy": 409,
    "quota_exceeded": 413,
    "bad_hash": 422,
    "rate_limited": 429,
    "range_not_satisfiable": 416,
    "file_error": 500,
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


def is_busy_error(exc: BaseException) -> bool:
    """True when an `OSError` says that another process holds the file (retrying may help)."""
    if isinstance(exc, PermissionError):
        return True
    return isinstance(exc, OSError) and getattr(exc, "winerror", None) in _BUSY_WINERRORS


def file_error(exc: OSError) -> ApiError:
    """The `ApiError` for an `OSError` raised by a file operation.

    A missing file is `not_found`, a busy file is `busy` (409). Anything else is unexpected:
    it is logged with its stack and answered with a readable 500 `file_error`.
    """
    if isinstance(exc, FileNotFoundError):
        return ApiError("not_found", "The file is not available.")
    if is_busy_error(exc):
        return ApiError("busy", BUSY_MESSAGE)
    log.error("A file operation failed unexpectedly.", exc_info=exc)
    return ApiError("file_error", FILE_ERROR_MESSAGE, 500)


def file_operation[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Decorate a function that touches files so that no `OSError` leaves it (see `file_error`)."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except OSError as exc:
            raise file_error(exc) from exc

    return wrapper


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
