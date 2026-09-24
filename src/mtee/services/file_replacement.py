"""No-surprise replacement of a verified temporary beside its source."""

from __future__ import annotations

import ctypes
import os
import shutil
import stat
from pathlib import Path

__all__ = ["FileReplacement", "FileReplacementError"]

_REPLACEFILE_WRITE_THROUGH = 0x00000001


class FileReplacementError(OSError):
    """The source was not replaced and recovery paths are retained."""


class FileReplacement:
    """Publish a prepared copy without exposing a partially written source."""

    def publish(self, temporary_path: Path, destination: Path, backup_path: Path) -> None:
        for candidate, label in (
            (temporary_path, "Temporary"),
            (destination, "Source"),
        ):
            if candidate.is_symlink():
                raise FileReplacementError(f"{label} files cannot be symbolic links.")
        if backup_path.exists() or backup_path.is_symlink():
            raise FileReplacementError(f"Recovery path already exists: {backup_path.name}")
        temporary = temporary_path.resolve(strict=True)
        target = destination.resolve(strict=True)
        backup = backup_path.resolve(strict=False)
        if temporary.parent != target.parent or backup.parent != target.parent:
            raise FileReplacementError("Temporary, source, and backup must share one directory.")
        temporary_status = os.stat(temporary, follow_symlinks=False)
        target_status = os.stat(target, follow_symlinks=False)
        if not stat.S_ISREG(temporary_status.st_mode) or not stat.S_ISREG(target_status.st_mode):
            raise FileReplacementError("Source and temporary must be regular files.")
        if temporary_status.st_nlink != 1 or target_status.st_nlink != 1:
            raise FileReplacementError("Files with multiple hard links cannot be replaced safely.")
        if temporary_status.st_dev != target_status.st_dev:
            raise FileReplacementError("A metadata replacement must stay on the source volume.")
        if os.name == "nt":
            self._replace_windows(target, temporary, backup)
        else:
            try:
                shutil.copy2(target, backup)
                os.replace(temporary, target)
            except OSError as error:
                raise FileReplacementError(str(error)) from error

    @staticmethod
    def _replace_windows(target: Path, temporary: Path, backup: Path) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        replace_file = kernel32.ReplaceFileW
        replace_file.argtypes = (
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        replace_file.restype = ctypes.c_int
        succeeded = replace_file(
            str(target),
            str(temporary),
            str(backup),
            _REPLACEFILE_WRITE_THROUGH,
            None,
            None,
        )
        if not succeeded:
            error = ctypes.WinError(ctypes.get_last_error())
            raise FileReplacementError(
                f"Windows could not replace {target.name}: {error}"
            ) from error
