"""Ask Windows Explorer to select a file without invoking a shell."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

__all__ = ["WindowsShellReveal"]


class WindowsShellReveal:
    """Launch Explorer with a structured argument vector for one existing file."""

    def __init__(self, runner: Callable[..., object] | None = None) -> None:
        self._runner = runner or subprocess.Popen
        self._is_windows = os.name == "nt" or runner is not None

    def reveal(self, path: Path | str) -> None:
        target = Path(path).expanduser().resolve(strict=True)
        if not target.is_file():
            raise FileNotFoundError(target)
        if not self._is_windows:
            raise OSError("Windows Explorer is available only on Windows.")
        self._runner(
            ["explorer.exe", f"/select,{target}"],
            close_fds=True,
            creationflags=subprocess.DETACHED_PROCESS,
        )
