"""Put a file that is not in the library into a folder, without ever replacing a file.

This is the placement rule of ``FileOperations.import_file`` (AGENTS.md, Data safety: pick a new
name rather than replacing an existing file):

* the name is tried first as it is, then ``name (2).ext``, ``name (3).ext``...;
* the file is put in place by an operation that refuses an existing target: on Windows
  ``os.rename`` (it raises ``FileExistsError`` instead of replacing), elsewhere ``os.link``
  followed by removing the source. A name that appears between the check and the move is
  tried again with the next number;
* on another volume the file is first copied to ``.<name>.part`` in the destination folder
  (opened with mode ``xb``, so it cannot replace anything), then put in place the same way, so
  the scanner never sees a half-written audio file under its final name.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

__all__ = ["numbered_name", "place_without_overwrite"]

_MAX_ATTEMPTS = 1000
_COPY_CHUNK = 1024 * 1024


def numbered_name(name: str, number: int) -> str:
    """Return ``name`` for number 1 and ``stem (number).ext`` after."""
    if number <= 1:
        return name
    path = Path(name)
    return f"{path.stem} ({number}){path.suffix}"


def place_without_overwrite(
    source: Path, folder: Path, is_reserved: Callable[[Path], bool] | None = None
) -> Path:
    """Move ``source`` into the existing ``folder`` and return the path it now has.

    ``is_reserved(target)`` may name paths that are not free although no file is there (a path
    the library still owns). Raises ``OSError`` when the file cannot be moved; ``source`` is
    then untouched and nothing is left in ``folder``. When the file was copied across volumes
    and the source cannot be removed afterwards, the source stays in place.
    """
    wanted = source.name
    part: Path | None = None
    current = source
    if not _same_volume(source, folder):
        part = _copy_to_part(source, folder, wanted)
        current = part
    try:
        for number in range(1, _MAX_ATTEMPTS + 1):
            target = folder / numbered_name(wanted, number)
            if target.exists() or (is_reserved is not None and is_reserved(target)):
                continue
            try:
                _place(current, target)
            except FileExistsError:
                continue
            except OSError:
                if part is None and not _same_volume(source, folder):
                    # The volumes differ after all: go through the copy.
                    part = _copy_to_part(source, folder, wanted)
                    current = part
                    continue
                raise
            if part is not None:
                with contextlib.suppress(OSError):
                    source.unlink()
                part = None
            return target
        raise FileExistsError(f"No free name for {wanted} in {folder}")
    finally:
        if part is not None:
            with contextlib.suppress(OSError):
                part.unlink()


def _place(source: Path, target: Path) -> None:
    """Make ``target`` the file ``source`` was; raise ``FileExistsError`` if it exists."""
    if sys.platform == "win32":
        os.rename(source, target)  # Windows refuses an existing target
        return
    os.link(source, target)  # POSIX: refuses an existing target
    os.unlink(source)


def _same_volume(source: Path, folder: Path) -> bool:
    try:
        return os.stat(source).st_dev == os.stat(folder).st_dev
    except OSError:
        return False


def _copy_to_part(source: Path, folder: Path, wanted: str) -> Path:
    """Copy ``source`` to a new ``.<name>.part`` of ``folder``; never replaces a file."""
    for number in range(1, _MAX_ATTEMPTS + 1):
        part = folder / f".{numbered_name(wanted, number)}.part"
        created = False
        try:
            with source.open("rb") as reader, part.open("xb") as writer:
                created = True
                shutil.copyfileobj(reader, writer, _COPY_CHUNK)
                writer.flush()
                os.fsync(writer.fileno())
        except OSError as error:
            if created:  # never remove a file this call did not create
                with contextlib.suppress(OSError):
                    part.unlink()
            elif isinstance(error, FileExistsError):
                continue
            raise
        return part
    raise FileExistsError(f"No free temporary name for {wanted} in {folder}")
