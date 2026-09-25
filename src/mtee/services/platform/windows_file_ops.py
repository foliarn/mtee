"""No-overwrite Windows file operations with verified cross-volume moves."""

from __future__ import annotations

import ctypes
import hashlib
import os
import stat
import uuid
from collections.abc import Callable
from contextlib import suppress
from ctypes import wintypes
from pathlib import Path
from typing import Protocol

from mtee.domain.tracks import SourceRevision

__all__ = [
    "FileOperationAdapter",
    "FileOperationCancelledError",
    "FileOperationNativeError",
    "FileOperationRecoveryError",
    "WindowsFileOps",
]


class FileOperationAdapter(Protocol):
    """Native adapter contract used by the file operation service."""

    def move_no_replace(self, source: Path, destination: Path) -> None:
        """Move a regular file atomically without replacing the destination."""

    def move_cross_volume(
        self,
        source: Path,
        temporary: Path,
        destination: Path,
        *,
        expected_revision: SourceRevision,
        expected_sha256: str,
        is_cancelled: Callable[[], bool],
        report_progress: Callable[[int, int], None],
        phase_changed: Callable[[str, Path | None], None],
    ) -> None:
        """Copy, publish and remove only the verified source object."""


class FileOperationNativeError(OSError):
    """The native move did not complete as requested."""


class FileOperationCancelledError(Exception):
    """A verified copy was cancelled before its destination was published."""


class FileOperationRecoveryError(FileOperationNativeError):
    """A file operation left source, destination or temporary data for inspection."""

    def __init__(
        self,
        message: str,
        recovery_path: Path | None,
        *,
        phase: str = "copying",
    ) -> None:
        super().__init__(message)
        self.recovery_path = recovery_path
        self.phase = phase


class WindowsFileOps:
    """Move regular files without replacing destinations or deleting by path."""

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
                "MoveFileW only handles same-volume moves; use the verified copy protocol."
            )
        if case_only:
            self._move_case_only(source_path, destination_path)
        else:
            self._move_once(source_path, destination_path)

    def move_cross_volume(
        self,
        source: Path,
        temporary: Path,
        destination: Path,
        *,
        expected_revision: SourceRevision,
        expected_sha256: str,
        is_cancelled: Callable[[], bool],
        report_progress: Callable[[int, int], None],
        phase_changed: Callable[[str, Path | None], None],
    ) -> None:
        """Copy to an exclusive destination temp, publish, then delete by handle."""
        if os.name != "nt":
            raise FileOperationNativeError("Cross-volume moves are supported on Windows only.")
        if expected_revision.file_id is None:
            raise FileOperationNativeError(
                "This volume does not provide a stable file identifier for a safe move."
            )
        if temporary.parent != destination.parent:
            raise FileOperationNativeError(
                "The recovery copy must be created in the destination folder."
            )
        if temporary.exists() or temporary.is_symlink():
            raise FileOperationNativeError("The operation's temporary path is already occupied.")
        if destination.exists() or destination.is_symlink():
            raise FileOperationNativeError("The destination already exists.")

        source_fd = _open_existing_handle(source, access=0x80000000 | 0x00010000)
        temporary_fd = -1
        destination_fd = -1
        try:
            _validate_regular_handle(source_fd, source)
            initial_status = os.fstat(source_fd)
            initial_revision = _revision_from_stat(initial_status, expected_revision.generation)
            if not expected_revision.matches(initial_revision):
                raise FileOperationNativeError("The source changed before its copy began.")
            if int(getattr(initial_status, "st_file_attributes", 0)) & 0x00004000:
                raise FileOperationNativeError(
                    "Encrypted files cannot be moved across volumes by this copy adapter."
                )
            source_basic_info = _get_file_basic_info(source_fd)

            temporary_fd = _create_new_handle(temporary, access=0x40000000 | 0x00010000)
            phase_changed("copying", temporary)
            digest = hashlib.sha256()
            copied = 0
            total = expected_revision.size_bytes
            source_copy_fd = os.dup(source_fd)
            cancelled = False
            with (
                os.fdopen(source_copy_fd, "rb") as source_stream,
                os.fdopen(temporary_fd, "wb", closefd=False) as target_stream,
            ):
                while True:
                    if is_cancelled():
                        cancelled = True
                        break
                    chunk = source_stream.read(1024 * 1024)
                    if not chunk:
                        break
                    target_stream.write(chunk)
                    digest.update(chunk)
                    copied += len(chunk)
                    report_progress(copied, total)
                cancelled = cancelled or is_cancelled()
                target_stream.flush()
                if not cancelled:
                    os.fsync(temporary_fd)
                    _set_file_basic_info(temporary_fd, source_basic_info)
            if cancelled:
                _mark_for_deletion(temporary_fd)
                os.close(temporary_fd)
                temporary_fd = -1
                raise FileOperationCancelledError(
                    "The copy was cancelled. The source and library location are unchanged."
                )

            final_source_revision = _revision_from_stat(
                os.fstat(source_fd), expected_revision.generation
            )
            copied_hash = digest.hexdigest()
            if (
                copied_hash != expected_sha256
                or not expected_revision.matches(final_source_revision)
                or copied != total
            ):
                raise FileOperationRecoveryError(
                    "The copied bytes or source revision differ from the preview.",
                    temporary,
                )
            os.close(temporary_fd)
            temporary_fd = -1

            self.move_no_replace(temporary, destination)
            phase_changed("destination_published", None)

            destination_fd = _open_existing_handle(destination, access=0x80000000)
            _validate_regular_handle(destination_fd, destination)
            if (
                os.fstat(destination_fd).st_size != total
                or _sha256_fd(destination_fd) != expected_sha256
            ):
                raise FileOperationRecoveryError(
                    "The published destination failed its size or SHA-256 check.",
                    None,
                    phase="destination_published",
                )

            _mark_for_deletion(source_fd)
            os.close(source_fd)
            source_fd = -1
            try:
                remaining = SourceRevision.observe(source, generation=expected_revision.generation)
            except FileNotFoundError:
                remaining = None
            if remaining is not None and expected_revision.matches(remaining):
                raise FileOperationRecoveryError(
                    "Windows did not remove the verified source file.",
                    None,
                    phase="destination_published",
                )
            phase_changed("source_removed", None)
        except FileOperationCancelledError:
            raise
        except FileOperationRecoveryError:
            raise
        except OSError as error:
            recovery = temporary if temporary.exists() else None
            if recovery is None and not destination.exists():
                raise FileOperationNativeError(str(error)) from error
            raise FileOperationRecoveryError(
                f"Cross-volume move stopped with its source retained: {error}",
                recovery,
                phase="destination_published" if destination.exists() else "copying",
            ) from error
        finally:
            if destination_fd >= 0:
                os.close(destination_fd)
            if temporary_fd >= 0:
                os.close(temporary_fd)
            if source_fd >= 0:
                os.close(source_fd)

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

    def copy_no_replace(
        self,
        source: Path,
        temporary: Path,
        destination: Path,
        *,
        expected_revision: SourceRevision,
        expected_sha256: str,
        is_cancelled: Callable[[], bool],
        report_progress: Callable[[int, int], None],
    ) -> None:
        """Copy to an exclusive neighbor, verify it, and publish by no-overwrite link."""
        if source.is_symlink() or not source.is_file():
            raise FileOperationNativeError("Only regular files can be copied.")
        if temporary.parent != destination.parent:
            raise FileOperationNativeError("The temporary copy must be beside its destination.")
        if temporary.exists() or destination.exists() or destination.is_symlink():
            raise FileOperationNativeError("The temporary path or destination is already occupied.")
        before = SourceRevision.observe(source, generation=expected_revision.generation)
        if not expected_revision.matches(before):
            raise FileOperationNativeError("The source changed before the copy began.")
        digest = hashlib.sha256()
        copied = 0
        try:
            with source.open("rb") as source_stream, temporary.open("xb") as target_stream:
                while chunk := source_stream.read(1024 * 1024):
                    if is_cancelled():
                        raise FileOperationCancelledError("The copy was cancelled.")
                    target_stream.write(chunk)
                    digest.update(chunk)
                    copied += len(chunk)
                    report_progress(copied, expected_revision.size_bytes)
                target_stream.flush()
                os.fsync(target_stream.fileno())
            after = SourceRevision.observe(source, generation=expected_revision.generation)
            if (
                copied != expected_revision.size_bytes
                or digest.hexdigest() != expected_sha256
                or not expected_revision.matches(after)
            ):
                raise FileOperationRecoveryError(
                    "The source changed or the temporary copy failed verification.", temporary
                )
            self.move_no_replace(temporary, destination)
        except FileOperationCancelledError:
            with suppress(OSError):
                temporary.unlink()
            raise
        except FileOperationRecoveryError:
            raise
        except OSError as error:
            recovery_path = temporary if temporary.exists() else None
            raise FileOperationRecoveryError(
                f"The verified copy could not be published without replacement: {error}",
                recovery_path,
            ) from error
        if _sha256_path(destination) != expected_sha256:
            raise FileOperationRecoveryError(
                "The published copy failed SHA-256 verification.", None, phase="published"
            )


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


def _open_existing_handle(path: Path, *, access: int) -> int:
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        _long_path(str(path)),
        access,
        0x00000001,
        None,
        3,
        0x00200000,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        handle_value = handle if isinstance(handle, int) else handle.value
        return msvcrt.open_osfhandle(int(handle_value), os.O_RDONLY | os.O_BINARY)
    except Exception:
        kernel32.CloseHandle(handle)
        raise


def _create_new_handle(path: Path, *, access: int) -> int:
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        _long_path(str(path)),
        access,
        0,
        None,
        1,
        0x00000080,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        handle_value = handle if isinstance(handle, int) else handle.value
        return msvcrt.open_osfhandle(int(handle_value), os.O_RDWR | os.O_BINARY)
    except Exception:
        kernel32.CloseHandle(handle)
        raise


def _validate_regular_handle(file_descriptor: int, path: Path) -> None:
    file_status = os.fstat(file_descriptor)
    if not stat.S_ISREG(file_status.st_mode):
        raise FileOperationNativeError(f"Only regular files can be moved: {path}")
    attributes = getattr(file_status, "st_file_attributes", 0)
    if attributes & 0x00000400:
        raise FileOperationNativeError(f"Reparse-point files are not supported: {path}")


def _revision_from_stat(status: os.stat_result, generation: int) -> SourceRevision:
    file_index = getattr(status, "st_ino", 0)
    volume = getattr(status, "st_dev", 0)
    file_id = f"{volume}:{file_index}" if file_index else None
    return SourceRevision(status.st_size, status.st_mtime_ns, file_id, generation)


def _sha256_fd(file_descriptor: int) -> str:
    digest = hashlib.sha256()
    with os.fdopen(os.dup(file_descriptor), "rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _mark_for_deletion(file_descriptor: int) -> None:
    import msvcrt

    class FileDispositionInfo(ctypes.Structure):
        _fields_ = [("DeleteFile", wintypes.BOOL)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_information = kernel32.SetFileInformationByHandle
    set_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    set_information.restype = wintypes.BOOL
    disposition = FileDispositionInfo(True)
    handle = msvcrt.get_osfhandle(file_descriptor)
    if not set_information(
        handle,
        4,
        ctypes.byref(disposition),
        ctypes.sizeof(disposition),
    ):
        raise ctypes.WinError(ctypes.get_last_error())


class _FileBasicInfo(ctypes.Structure):
    _fields_ = [
        ("CreationTime", ctypes.c_longlong),
        ("LastAccessTime", ctypes.c_longlong),
        ("LastWriteTime", ctypes.c_longlong),
        ("ChangeTime", ctypes.c_longlong),
        ("FileAttributes", wintypes.DWORD),
    ]


def _get_file_basic_info(file_descriptor: int) -> _FileBasicInfo:
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandleEx
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    get_information.restype = wintypes.BOOL
    information = _FileBasicInfo()
    if not get_information(
        msvcrt.get_osfhandle(file_descriptor),
        0,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return information


def _set_file_basic_info(file_descriptor: int, source: _FileBasicInfo) -> None:
    import msvcrt

    preserved_attributes = int(source.FileAttributes) & (
        0x00000001 | 0x00000002 | 0x00000004 | 0x00000020 | 0x00002000
    )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_information = kernel32.SetFileInformationByHandle
    set_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    set_information.restype = wintypes.BOOL
    information = _FileBasicInfo(
        source.CreationTime,
        source.LastAccessTime,
        source.LastWriteTime,
        0,
        preserved_attributes if preserved_attributes else 0x00000080,
    )
    if not set_information(
        msvcrt.get_osfhandle(file_descriptor),
        0,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
