"""Locations of the data, cache and log directories.

Nothing is written inside the repository or next to the executable. The
recipe of a step isolates its files with ``--data-dir``; ``--demo`` selects a
separate storage so the real settings are never read nor altered.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QStandardPaths

__all__ = ["DEMO_DIRECTORY_NAME", "AppPaths", "resolve_app_paths"]

DEMO_DIRECTORY_NAME = "demo"
_DATABASE_FILE_NAME = "mtee.sqlite3"


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Directories owned by one MTEE installation and mode."""

    data_dir: Path
    cache_dir: Path
    logs_dir: Path

    @property
    def database_path(self) -> Path:
        """Return the SQLite file of this installation."""
        return self.data_dir / _DATABASE_FILE_NAME

    def ensure(self) -> AppPaths:
        """Create the three directories when they are missing and return ``self``."""
        for directory in (self.data_dir, self.cache_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def resolve_app_paths(data_dir: Path | str | None = None, *, demo: bool = False) -> AppPaths:
    """Return the directories to use for this run.

    With ``data_dir``, every directory lives under that root, which keeps a
    recipe self-contained. Without it, the standard locations of the platform
    are used. ``demo`` appends an isolated sub-directory in both cases.
    """
    if data_dir is not None:
        root = Path(data_dir).expanduser().resolve()
        if demo:
            root = root / DEMO_DIRECTORY_NAME
        return AppPaths(data_dir=root, cache_dir=root / "cache", logs_dir=root / "logs")

    data_root = _standard_location(QStandardPaths.StandardLocation.AppDataLocation)
    cache_root = _standard_location(QStandardPaths.StandardLocation.CacheLocation)
    logs_root = data_root / "logs"
    if demo:
        data_root = data_root / DEMO_DIRECTORY_NAME
        cache_root = cache_root / DEMO_DIRECTORY_NAME
        logs_root = data_root / "logs"
    return AppPaths(data_dir=data_root, cache_dir=cache_root, logs_dir=logs_root)


def _standard_location(location: QStandardPaths.StandardLocation) -> Path:
    """Return the writable standard directory of ``location``.

    Qt returns an empty string when no location is available; the failure is
    reported instead of silently writing next to the executable.
    """
    raw = QStandardPaths.writableLocation(location)
    if not raw:
        raise RuntimeError(f"No writable location provided by the system for {location!r}")
    return Path(raw)
