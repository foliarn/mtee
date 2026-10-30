"""Wait for another MTEE process to exit before this one starts its application (plan 123.6).

A restarted MTEE is started with ``--wait-for-exit <pid>``. The old process saves its layout and
settings while it quits through the normal path, so the new one waits for that exit first. The
option is internal: ``mtee.__main__`` removes it before ``argparse`` reads the arguments, so it
never appears in ``--help``. This module imports no Qt module.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from collections.abc import Sequence

__all__ = ["WAIT_OPTION", "strip_wait_option", "wait_for_process_exit"]

WAIT_OPTION = "--wait-for-exit"

_DEFAULT_TIMEOUT_S = 15.0
_POLL_INTERVAL_S = 0.1
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0x00000000


def strip_wait_option(argv: Sequence[str]) -> tuple[list[str], int | None]:
    """Return ``argv`` without the ``--wait-for-exit <pid>`` pair, and the pid or None.

    The first item, the program name, is kept and never searched. A value that is not a positive
    whole number is ignored, and it is removed with the option. An option at the end without a
    value is removed too.
    """
    remaining = list(argv[:1])
    pid: int | None = None
    index = 1
    while index < len(argv):
        if argv[index] != WAIT_OPTION:
            remaining.append(argv[index])
            index += 1
            continue
        if index + 1 < len(argv):
            pid = _parse_pid(argv[index + 1]) or pid
            index += 2
        else:
            index += 1
    return remaining, pid


def wait_for_process_exit(pid: int, timeout_s: float = _DEFAULT_TIMEOUT_S) -> bool:
    """Return True once the process ``pid`` has exited, or False when ``timeout_s`` passes first.

    A process that is already gone gives True. This function never signals or ends the process.
    """
    if sys.platform == "win32":
        return _wait_on_windows(pid, timeout_s)
    return _wait_by_polling(pid, timeout_s)


def _parse_pid(text: str) -> int | None:
    if not text.isdecimal():
        return None
    pid = int(text)
    return pid if pid > 0 else None


def _wait_on_windows(pid: int, timeout_s: float) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    open_process.restype = ctypes.c_void_p
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    wait_for_single_object.restype = ctypes.c_uint32
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int

    handle = open_process(_SYNCHRONIZE, False, pid)
    if not handle:
        # No process has this identifier any more: it has exited.
        return True
    try:
        status = wait_for_single_object(handle, max(0, int(timeout_s * 1000)))
    finally:
        close_handle(handle)
    return status == _WAIT_OBJECT_0


def _wait_by_polling(pid: int, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            # The process exists but belongs to another user: it has not exited.
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_INTERVAL_S)
