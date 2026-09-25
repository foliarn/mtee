"""Cancellable, bounded FFmpeg filter execution for analysis."""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable

from mtee.domain.jobs import JobCancelledError
from mtee.services.ffmpeg_runtime import FfmpegRuntime

_MAX_LOG_BYTES = 128 * 1024


def run_filter(
    runtime: FfmpegRuntime,
    arguments: list[str],
    is_cancelled: Callable[[], bool],
    timeout_seconds: float = 7200,
) -> str:
    process = runtime.start("ffmpeg", arguments)
    output = bytearray()

    def drain(stream: object, capture: bool) -> None:
        while chunk := stream.read(8192):  # type: ignore[attr-defined]
            if not capture:
                continue
            output.extend(chunk)
            if len(output) > _MAX_LOG_BYTES:
                del output[:-_MAX_LOG_BYTES]

    assert process.stdout is not None and process.stderr is not None
    readers = (
        threading.Thread(target=drain, args=(process.stdout, False), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, True), daemon=True),
    )
    for thread in readers:
        thread.start()
    started = time.monotonic()
    try:
        while process.poll() is None:
            if is_cancelled():
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise JobCancelledError("analysis cancelled")
            if time.monotonic() - started > timeout_seconds:
                process.kill()
                raise TimeoutError("FFmpeg analysis exceeded its time limit.")
            time.sleep(0.05)
        for thread in readers:
            thread.join(timeout=1)
        if process.returncode != 0:
            diagnostic = bytes(output).decode("utf-8", errors="replace").strip()
            raise RuntimeError(diagnostic or f"FFmpeg exited with code {process.returncode}.")
        return bytes(output).decode("utf-8", errors="replace")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        for thread in readers:
            thread.join(timeout=1)
