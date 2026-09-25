"""Locate the pinned FFmpeg tools without consulting PATH."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__ = ["FfmpegRuntime", "FfmpegRuntimeError"]


class FfmpegRuntimeError(RuntimeError):
    """An expected executable from the bundled FFmpeg runtime is unavailable."""


class FfmpegRuntime:
    """Resolve and invoke the packaged FFmpeg executables with argument vectors."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or self._default_root()

    @staticmethod
    def _default_root() -> Path:
        if getattr(sys, "frozen", False):
            return Path(vars(sys)["_MEIPASS"]) / "mtee" / "native" / "ffmpeg" / "bin"
        project_root = Path(__file__).resolve().parents[3]
        return project_root / "vendor" / "ffmpeg" / "bin"

    def executable(self, tool: str) -> Path:
        """Return one supported runtime executable, refusing arbitrary tool names."""
        if tool not in {"ffmpeg", "ffprobe"}:
            raise ValueError(f"Unsupported FFmpeg tool: {tool}")
        path = self._root / f"{tool}.exe"
        if not path.is_file():
            raise FfmpegRuntimeError(f"The bundled {tool} runtime is missing: {path}")
        return path

    def run(
        self,
        tool: str,
        arguments: list[str],
        *,
        timeout_seconds: float = 30,
    ) -> subprocess.CompletedProcess[str]:
        """Run a bundled tool without a shell and with a bounded execution time."""
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        command = [str(self.executable(tool)), *arguments]
        environment = os.environ.copy()
        environment["PATH"] = str(self._root)
        try:
            return subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                env=environment,
                shell=False,
                timeout=timeout_seconds,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            raise FfmpegRuntimeError(f"Could not start bundled {tool}: {error}") from error

    def start(self, tool: str, arguments: list[str]) -> subprocess.Popen[bytes]:
        """Start a streaming process without a shell for bounded PCM/progress I/O."""
        command = [str(self.executable(tool)), *arguments]
        environment = os.environ.copy()
        environment["PATH"] = str(self._root)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            return subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                shell=False,
                creationflags=flags,
            )
        except OSError as error:
            raise FfmpegRuntimeError(f"Could not start bundled {tool}: {error}") from error

    def version(self, tool: str = "ffmpeg") -> str:
        """Return the version banner from the selected executable."""
        result = self.run(tool, ["-version"])
        if result.returncode != 0:
            raise FfmpegRuntimeError(result.stderr[-2048:] or f"{tool} exited {result.returncode}.")
        return result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
