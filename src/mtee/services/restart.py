"""Start a new MTEE process with the same arguments, so the application can restart itself.

The command is the executable of the running program: ``MTEE.exe`` when frozen, and
``python -m mtee`` when run from the sources. The new process is started detached, and the caller
then quits the current one through its normal quit path, so settings and layout are saved first.
The command names this process with ``--wait-for-exit <pid>``, so the new process waits for this
one to exit before it starts (plan 123.6).
The child of a one-file executable must not inherit the variables of the parent's bootloader
(PyInstaller 6.9 and later reset them when ``PYINSTALLER_RESET_ENVIRONMENT`` is set).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence

from mtee.services.wait_for_exit import WAIT_OPTION, strip_wait_option

__all__ = ["restart_command", "restart_environment", "start_detached"]

_RESET_VARIABLE = "PYINSTALLER_RESET_ENVIRONMENT"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def restart_command() -> list[str]:
    """Return the command line of a new MTEE process with the arguments of this one.

    The new process waits for this one: the option names this process id, and any option
    already present in the arguments is replaced, so it appears only once.
    """
    arguments, _ = strip_wait_option(sys.argv)
    waiting = [WAIT_OPTION, str(os.getpid())]
    if _is_frozen():
        return [sys.executable, *waiting, *arguments[1:]]
    return [sys.executable, "-m", "mtee", *waiting, *arguments[1:]]


def restart_environment() -> dict[str, str]:
    """Return the environment of the new process: a copy of this one, reset for a frozen child."""
    environment = dict(os.environ)
    if _is_frozen():
        environment[_RESET_VARIABLE] = "1"
    return environment


def start_detached(
    command: Sequence[str],
    environment: Mapping[str, str],
    *,
    runner: Callable[..., object] | None = None,
) -> None:
    """Start ``command`` in a detached process that outlives this one.

    The flags are those of ``services.platform.shell_reveal``. ``runner`` replaces
    ``subprocess.Popen`` in tests. Raise ``OSError`` when the process cannot start.
    """
    launch = runner or subprocess.Popen
    launch(
        list(command),
        env=dict(environment),
        close_fds=True,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )
