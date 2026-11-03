"""The device token of MTEE Remote, encrypted with Windows DPAPI for the current user.

The token is written to ``<data-dir>/token.bin`` and never to the settings or to a log. DPAPI
uses the user scope (no machine scope), so only the same Windows account on the same computer
can open the file, and no window is shown (``CRYPTPROTECT_UI_FORBIDDEN``). The plain token
exists only in the memory of the caller.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

TOKEN_FILE = "token.bin"
_UI_FORBIDDEN = 0x1
_UNSUPPORTED = "Saving the MTEE Remote connection needs Windows. MTEE runs on Windows only."
_UNREADABLE = "The saved MTEE Remote connection cannot be opened on this computer. Connect again."


class TokenError(RuntimeError):
    """The token store cannot save, read or open the token. The message is a sentence."""

    readable = True


class _DataBlob(ctypes.Structure):
    _fields_ = (
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    )


def save_token(data_dir: Path, token: str) -> None:
    """Encrypt ``token`` and store it in ``data_dir``, replacing any earlier token."""
    _require_windows()
    if not token:
        raise ValueError("An empty token cannot be saved.")
    blob = _protect(token.encode("utf-8"))
    data_dir.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=data_dir, prefix="token-", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, data_dir / TOKEN_FILE)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def load_token(data_dir: Path) -> str | None:
    """Return the stored token, or ``None`` when there is none."""
    _require_windows()
    try:
        blob = (data_dir / TOKEN_FILE).read_bytes()
    except FileNotFoundError:
        return None
    try:
        return _unprotect(blob).decode("utf-8")
    except (TokenError, UnicodeDecodeError):
        raise TokenError(_UNREADABLE) from None


def token_exists(data_dir: Path) -> bool:
    """Return whether a token file is stored, without opening it."""
    return (data_dir / TOKEN_FILE).is_file()


def delete_token(data_dir: Path) -> None:
    """Remove the stored token; a missing file is not an error."""
    _require_windows()
    (data_dir / TOKEN_FILE).unlink(missing_ok=True)


def _require_windows() -> None:
    if sys.platform != "win32":
        raise TokenError(_UNSUPPORTED)


def _protect(data: bytes) -> bytes:
    crypt32 = _crypt32()
    source = _blob_of(data)
    output = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(source), None, None, None, None, _UI_FORBIDDEN, ctypes.byref(output)
    )
    if not ok:
        raise TokenError("Windows could not protect the MTEE Remote connection. Try again.")
    return _take(output)


def _unprotect(blob: bytes) -> bytes:
    crypt32 = _crypt32()
    source = _blob_of(blob)
    output = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, _UI_FORBIDDEN, ctypes.byref(output)
    )
    if not ok:
        raise TokenError(_UNREADABLE)
    return _take(output)


def _crypt32() -> ctypes.WinDLL:
    library = ctypes.WinDLL("crypt32", use_last_error=True)
    for name in ("CryptProtectData", "CryptUnprotectData"):
        function = getattr(library, name)
        function.argtypes = (
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        )
        function.restype = wintypes.BOOL
    return library


def _blob_of(data: bytes) -> _DataBlob:
    """Wrap ``data`` for a call; the buffer is kept alive by the blob."""
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob._buffer = buffer  # type: ignore[attr-defined]  # keeps the memory alive
    return blob


def _take(blob: _DataBlob) -> bytes:
    """Copy the bytes Windows allocated, then free them."""
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = (wintypes.HLOCAL,)
        kernel32.LocalFree.restype = wintypes.HLOCAL
        kernel32.LocalFree(ctypes.cast(blob.pbData, wintypes.HLOCAL))
