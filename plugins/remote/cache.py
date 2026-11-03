"""The desktop stream cache of MTEE Remote (plan 127.6): the originals of server-only tracks.

A server-only track played at the *Original* level is downloaded in the background into this
folder (``<data-dir>/cache``). The copy is kept under ``<item_id>-<sha256><ext>``: it is used only
while its SHA-256 is the one the server reports, so a copy that was damaged, or of an older
revision, is discarded and never played. Download reuses the copy (``offload``), so a track the
person keeps on this computer is not downloaded twice.

Only files that this module wrote are touched: ``add`` takes a file only from the ``incoming``
folder under the cache folder, and eviction and clearing only look at the files of the folder.
Eviction removes the least recently used copies (by modification time, which ``lookup`` refreshes)
until the folder is under the size limit.
"""

from __future__ import annotations

import contextlib
import os
import re
from pathlib import Path, PurePosixPath

from mtee.plugins.api import PluginContext

from .hashing import file_sha256

CACHE_DIR = "cache"
INCOMING_DIR = "incoming"
LIMIT_SETTING = "cache_size_gb"
DEFAULT_LIMIT_GB = 10
MIN_LIMIT_GB = 1
MAX_LIMIT_GB = 200
_GIB = 1024**3
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ITEM_ID = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
_EXT = re.compile(r"^\.[a-z0-9]{1,8}$")


def ext_of(name: str) -> str:
    """The lower-case extension of a file name (``.flac``), or ``""`` when it is not a plain one."""
    suffix = PurePosixPath(name).suffix.lower()
    return suffix if _EXT.match(suffix) else ""


def cache_limit_gb(context: PluginContext) -> int:
    """The size limit of the cache in GB, from its setting (default 10, kept within 1 to 200)."""
    raw = context.settings.get(LIMIT_SETTING, str(DEFAULT_LIMIT_GB)) or ""
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_LIMIT_GB
    return min(MAX_LIMIT_GB, max(MIN_LIMIT_GB, value))


def set_cache_limit_gb(context: PluginContext, value: int) -> None:
    """Store the size limit in GB; a value out of 1 to 200 raises ``ValueError``."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("The cache size must be a whole number of GB.")
    if not MIN_LIMIT_GB <= value <= MAX_LIMIT_GB:
        raise ValueError(f"The cache size must be from {MIN_LIMIT_GB} to {MAX_LIMIT_GB} GB.")
    context.settings.set(LIMIT_SETTING, str(value))


def open_cache(context: PluginContext) -> StreamCache:
    """The cache of this plugin, with the size limit of its setting."""
    return StreamCache(context.data_dir / CACHE_DIR, cache_limit_gb(context) * _GIB)


class StreamCache:
    """The copies of server originals in one folder, with a size limit and least-recent eviction."""

    def __init__(self, folder: Path, limit_bytes: int) -> None:
        if limit_bytes < 0:
            raise ValueError("The cache limit must not be negative.")
        self._folder = Path(folder)
        self._limit = limit_bytes

    @property
    def folder(self) -> Path:
        return self._folder

    @property
    def limit_bytes(self) -> int:
        return self._limit

    def set_limit(self, limit_bytes: int) -> None:
        if limit_bytes < 0:
            raise ValueError("The cache limit must not be negative.")
        self._limit = limit_bytes

    def incoming_dir(self) -> Path:
        """The folder where a download is written before ``add`` takes it (created when asked)."""
        path = self._folder / INCOMING_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    def path_for(self, item_id: str, sha256: str, ext: str) -> Path:
        """Where the copy of an item at a SHA-256 is kept. Bad values raise ``ValueError``."""
        if not _ITEM_ID.match(item_id):
            raise ValueError("The item identifier is not valid.")
        if not _SHA256.match(sha256):
            raise ValueError("The SHA-256 is not valid.")
        if ext and not _EXT.match(ext):
            raise ValueError("The extension is not valid.")
        return self._folder / f"{item_id}-{sha256}{ext}"

    def lookup(self, item_id: str, sha256: str, ext: str) -> Path | None:
        """The copy at ``sha256`` when it is there and its bytes match; otherwise None.

        A copy whose bytes do not match is deleted. A copy that is returned gets a new modification
        time, so eviction keeps it longer.
        """
        path = self.path_for(item_id, sha256, ext)
        try:
            if not path.is_file():
                return None
            if file_sha256(path) != sha256:
                with contextlib.suppress(OSError):
                    path.unlink()
                return None
            os.utime(path)
        except OSError:
            return None
        return path

    def add(self, item_id: str, sha256: str, src_path: Path) -> Path | None:
        """Keep the download ``src_path`` as the copy of an item; return its path, or None.

        ``src_path`` must be a file of the ``incoming`` folder. Its SHA-256 is checked first: a file
        that does not match is deleted and None is returned. A matching file is moved into the
        cache. Raises ``ValueError`` for a ``src_path`` outside the ``incoming`` folder.
        """
        src = Path(src_path)
        if not _within(src, self._folder / INCOMING_DIR):
            raise ValueError("Only a download of the incoming folder can be added to the cache.")
        target = self.path_for(item_id, sha256, ext_of(src.name))
        if not src.is_file():
            return None
        if file_sha256(src) != sha256:
            with contextlib.suppress(OSError):
                src.unlink()
            return None
        self._folder.mkdir(parents=True, exist_ok=True)
        os.replace(src, target)
        return target

    def evict(self, keep: Path | None = None) -> int:
        """Remove the least recently used copies until the folder is under the limit.

        ``keep`` (the copy just added) is never removed. A copy that is in use cannot be removed on
        Windows; it is skipped. Return how many copies were removed.
        """
        entries = self._entries()
        total = sum(size for _path, size, _mtime in entries)
        removed = 0
        for path, size, _mtime in sorted(entries, key=lambda entry: entry[2]):
            if total <= self._limit:
                break
            if keep is not None and _same(path, keep):
                continue
            try:
                path.unlink()
            except OSError:
                continue
            total -= size
            removed += 1
        return removed

    def clear(self) -> int:
        """Remove every copy and every partial download of the folder; return how many went."""
        removed = 0
        for path, _size, _mtime in self._entries(include_incoming=True):
            try:
                path.unlink()
            except OSError:
                continue
            removed += 1
        return removed

    def size(self) -> int:
        """The bytes of the copies (the partial downloads are not counted)."""
        return sum(size for _path, size, _mtime in self._entries())

    def _entries(self, *, include_incoming: bool = False) -> list[tuple[Path, int, float]]:
        """The regular files of the folder (and of its incoming folder), with size and mtime."""
        folders = [self._folder]
        if include_incoming:
            folders.append(self._folder / INCOMING_DIR)
        found: list[tuple[Path, int, float]] = []
        for folder in folders:
            try:
                scanned = list(os.scandir(folder))
            except FileNotFoundError:
                continue
            for entry in scanned:
                if not entry.is_file(follow_symlinks=False):
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                found.append((Path(entry.path), info.st_size, info.st_mtime))
        return found


def _within(path: Path, folder: Path) -> bool:
    """True when ``path`` lies inside ``folder``."""
    base = os.path.normcase(os.path.abspath(folder))
    target = os.path.normcase(os.path.abspath(path))
    return target.startswith(base + os.sep)


def _same(first: Path, second: Path) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))
