"""Path safety for every path that comes from a client."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from mtee_remote.errors import ApiError

MAX_PATH_LENGTH = 1024
MAX_SEGMENT_BYTES = 255

_DRIVE = re.compile(r"^[A-Za-z]:")
# C0 controls and DEL. C1 controls (U+0080-U+009F) are allowed: Linux and NTFS accept them,
# and real names contain them when an accented name was badly converted.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _bad(reason: str) -> ApiError:
    return ApiError("bad_request", f"Invalid path: {reason}.")


def normalize_relative_path(raw: str) -> str:
    """Return `raw` as a safe POSIX relative path in NFC, or raise `bad_request`."""
    if not isinstance(raw, str) or not raw:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise _bad("it is empty")
    if "\\" in raw:
        raise _bad("it contains a backslash")
    if raw.startswith("/"):
        raise _bad("it is absolute")
    if _DRIVE.match(raw):
        raise _bad("it looks like a drive path")
    if _CONTROL.search(raw):
        raise _bad("it contains a control character")
    path = unicodedata.normalize("NFC", raw)
    if len(path) > MAX_PATH_LENGTH:
        raise _bad(f"it is longer than {MAX_PATH_LENGTH} characters")
    for segment in path.split("/"):
        if segment in ("", ".", ".."):
            raise _bad("it has an empty, '.' or '..' segment")
        # NFKC folds fullwidth dots and solidi, which a client or a tool could turn into real
        # ones. Characters that only look like a slash (U+2215, U+2044) stay ordinary
        # characters on Linux, and real file names use them, so they are allowed.
        folded = unicodedata.normalize("NFKC", segment)
        if folded in (".", "..") or "/" in folded or "\\" in folded:
            raise _bad("it has a look-alike of a separator or dot segment")
        if _CONTROL.search(folded):
            raise _bad("it contains a control character")
        if len(segment.encode("utf-8")) > MAX_SEGMENT_BYTES:
            raise _bad(f"a segment is longer than {MAX_SEGMENT_BYTES} bytes")
    return path


def resolve_under(base: Path, relative: str) -> Path:
    """Join `relative` to `base`, following symlinks, and refuse a result outside `base`."""
    clean = normalize_relative_path(relative)
    base_real = base.resolve()
    target = (base / clean).resolve()
    if not target.is_relative_to(base_real):
        raise _bad("it leaves the folder")
    return base / clean


def disk_path(base: Path, relative: str) -> Path:
    """Return `base / relative` for a path *stored by the server*, kept in its disk spelling.

    Unlike `resolve_under` this does not normalise to NFC, because a scan keeps the spelling
    found on disk (NFD names stay NFD). It still refuses anything that leaves `base`.
    """
    parts = relative.split("/")
    if (
        not relative
        or relative.startswith("/")
        or "\\" in relative
        or _DRIVE.match(relative)
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise ApiError("not_found", "The file is not available.")
    target = base / relative
    if not target.resolve().is_relative_to(base.resolve()):
        raise ApiError("not_found", "The file is not available.")
    return target
