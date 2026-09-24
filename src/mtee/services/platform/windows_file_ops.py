"""Strict same-volume file moves without replacement or delete fallback."""

from __future__ import annotations

import ctypes
import os
import uuid
from pathlib import Path
from typing import Protocol

__all__ = [
    "FileOperationAdapter",
    "FileOperationNativeError",
    "FileOperationRecoveryError",
    "WindowsFileOps",
]


class FileOperationAdapter(Protocol):
    """Native adapter contract used by the file operation service."""

    def move_no_replace(self, source: Path, destination: Path) -> None:
        """Move a regular file atomically without replacing the destination."""


class FileOperationNativeError(OSError):
    """The native move did not complete as requested."""


class FileOperationRecoveryError(FileOperationNativeError):
    """A case-only rename left its uniquely named intermediate file in place."""

    def __init__(self, message: str, recovery_path: Path) -> None:
        super().__init__(message)
        self.recovery_path = recovery_path


class WindowsFileOps:
    """Move one regular file atomically while refusing an occupied destination."""

    def move_no_replace(self, source: Path, destination: Path) -> None:
        if source.is_symlink():
            raise FileOperationNativeError("Symbolic-link sources are not supported.")
        requested_source = Path(os.path.abspath(source))
        source_path = source.resolve(strict=True)
        if _normalized_path(source_path) != _normalized_path(requested_source):
            raise FileOperationNativeError("The source path resolves through a link.")
        requested_parent = Path(os.path.abspath(destination.parent))
        parent = destination.parent.resolve(strict=True)
        if _normalized_path(parent) != _normalized_path(requested_parent):
            raise FileOperationNativeError("The destination folder resolves through a link.")
        destination_path = parent / destination.name
        case_only = _case_only_rename(source_path, destination_path)
        if not case_only and (destination_path.exists() or destination_path.is_symlink()):
            raise FileOperationNativeError(
                f"The destination already exists: {destination_path.name}"
            )
        if not source_path.is_file():
            raise FileOperationNativeError("Only regular audio files can be moved.")
        if os.stat(source_path).st_dev != os.stat(parent).st_dev:
            raise FileOperationNativeError(
                "Moves between volumes are disabled until cross-volume recovery is verified."
            )
        if case_only:
            self._move_case_only(source_path, destination_path)
        else:
            self._move_once(source_path, destination_path)

    def _move_case_only(self, source: Path, destination: Path) -> None:
        temporary = source.with_name(f".mtee-rename-{uuid.uuid4()}{source.suffix}")
        if temporary.exists() or temporary.is_symlink():
            raise FileOperationNativeError("The temporary rename path is already occupied.")
        self._move_once(source, temporary)
        try:
            self._move_once(temporary, destination)
        except Exception as error:
            try:
                self._move_once(temporary, source)
            except Exception as restore_error:
                raise FileOperationRecoveryError(
                    f"Case-only rename needs recovery at {temporary.name}: {restore_error}",
                    temporary,
                ) from error
            raise

    @staticmethod
    def _move_once(source: Path, destination: Path) -> None:
        if destination.exists() or destination.is_symlink():
            raise FileOperationNativeError(f"The destination already exists: {destination.name}")
        if os.name == "nt":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            move_file = kernel32.MoveFileW
            move_file.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
            move_file.restype = ctypes.c_int
            if not move_file(_long_path(str(source)), _long_path(str(destination))):
                error = ctypes.WinError(ctypes.get_last_error())
                raise FileOperationNativeError(
                    f"Windows could not move {source.name}: {error}"
                ) from error
            return
        try:
            os.link(source, destination)
            os.unlink(source)
        except OSError as error:
            raise FileOperationNativeError(str(error)) from error


def _case_only_rename(source: Path, destination: Path) -> bool:
    return os.path.normcase(os.path.abspath(source)) == os.path.normcase(
        os.path.abspath(destination)
    ) and str(source) != str(destination)


def _long_path(value: str) -> str:
    if not value.startswith("\\\\?\\") and len(value) >= 248:
        return "\\\\?\\" + os.path.abspath(value)
    return value


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))
