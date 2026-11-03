"""Transcoding one file with ffmpeg for a delivery plan (plan 127.1).

Decision (plan 127): a transcode is served only once it is **complete**. The first request
waits for ffmpeg to finish (FLAC, AAC and Opus encode tens of times faster than real time on
the server), then every request gets a normal file with `Content-Length` and HTTP Range. This
keeps MP4 `faststart` and exact gapless metadata, and fixes seeking everywhere. Streaming a
growing file is out of scope.

ffmpeg runs without a shell and with stdin closed. Its stderr goes to a temporary file, so a
noisy ffmpeg cannot block on a full pipe. On Windows no console window opens. The output is
always a fresh path chosen by the caller (`cache.py` writes `<final>.part-<uuid>`): ffmpeg is
never asked to overwrite a user file.
"""

from __future__ import annotations

import contextlib
import functools
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import IO

from mtee_remote.streaming.types import DeliveryPlan

RUN_TIMEOUT_S = 1800
_POLL_S = 0.2
_TAIL_LINES = 6
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class TranscodeError(RuntimeError):
    """A transcode failed, was cancelled or timed out. The output file is removed."""


def ffmpeg_args(ffmpeg: str, source: Path, plan: DeliveryPlan, output: Path) -> list[str]:
    """Return the ffmpeg command line that turns the first audio stream of `source` into `output`.

    Cover art, subtitles, data streams and tags are dropped. The output format is given with
    `-f`, because the output name is a `.part-<uuid>` file that ffmpeg cannot guess from.
    """
    if plan.send_original or plan.codec is None:
        raise ValueError("Only a transcode plan has ffmpeg arguments.")
    args = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-v",
        "error",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-map_metadata",
        "-1",
    ]
    if plan.codec == "flac":
        args += ["-c:a", "flac", "-compression_level", "5"]
        if plan.bit_depth == 16:
            args += ["-sample_fmt", "s16"]
        elif plan.bit_depth == 24:
            args += ["-sample_fmt", "s32", "-bits_per_raw_sample", "24"]
        elif plan.bit_depth is not None:
            raise ValueError(f"Unsupported FLAC bit depth: {plan.bit_depth}")
    elif plan.codec == "aac":
        args += ["-c:a", "aac", "-b:a", str(_required_bitrate(plan))]
    else:
        args += ["-c:a", "libopus", "-b:a", str(_required_bitrate(plan)), "-vbr", "on"]

    if plan.sample_rate is not None:
        if _has_soxr(ffmpeg):
            args += ["-af", f"aresample=resampler=soxr:osr={plan.sample_rate}"]
        else:
            args += ["-ar", str(plan.sample_rate)]

    if plan.codec == "flac":
        args += ["-f", "flac"]
    elif plan.codec == "aac":
        args += ["-f", "mp4", "-movflags", "+faststart"]
    else:
        args += ["-f", "ogg"]
    args.append(str(output))
    return args


def run_transcode(
    ffmpeg: str,
    source: Path,
    plan: DeliveryPlan,
    output: Path,
    *,
    timeout: float = RUN_TIMEOUT_S,
    cancel: threading.Event | None = None,
) -> None:
    """Run ffmpeg for `plan` and return once `output` is complete.

    `cancel` is polled every 0.2 s. On cancel or timeout the process is killed and waited for,
    and `output` is deleted before `TranscodeError` is raised. A non-zero exit, or an empty
    output, also deletes it and raises. This function blocks: call it from a worker thread.
    """
    if cancel is not None and cancel.is_set():
        raise TranscodeError(f"The transcode of {source.name} was cancelled.")
    args = ffmpeg_args(ffmpeg, source, plan, output)
    with tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=stderr,
                creationflags=_CREATE_NO_WINDOW,
            )
        except OSError as exc:
            _discard(output)
            raise TranscodeError(f"ffmpeg could not start: {exc}") from exc

        deadline = time.monotonic() + timeout
        stop_reason: str | None = None
        code: int | None = None
        while code is None and stop_reason is None:
            try:
                code = process.wait(timeout=_POLL_S)
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel.is_set():
                    stop_reason = "was cancelled"
                elif time.monotonic() >= deadline:
                    stop_reason = "timed out"
        if stop_reason is not None:
            process.kill()
            process.wait()
            _discard(output)
            raise TranscodeError(f"The transcode of {source.name} {stop_reason}.")
        tail = _stderr_tail(stderr)

    if code != 0:
        _discard(output)
        raise TranscodeError(f"ffmpeg failed ({code}) on {source.name}: {tail}")
    try:
        empty = output.stat().st_size == 0
    except OSError:
        empty = True
    if empty:
        _discard(output)
        raise TranscodeError(f"ffmpeg produced no audio for {source.name}: {tail}")


@functools.cache
def _has_soxr(ffmpeg: str) -> bool:
    """Tell whether this ffmpeg has the soxr resampler, by running a tiny resample once."""
    command = [
        ffmpeg,
        "-hide_banner",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=mono",
        "-t",
        "0.05",
        "-af",
        "aresample=resampler=soxr:osr=48000",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=60,
            check=False,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _required_bitrate(plan: DeliveryPlan) -> int:
    if plan.bitrate is None:
        raise ValueError(f"The {plan.codec} transcode needs a bitrate.")
    return plan.bitrate


def _discard(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


def _stderr_tail(stderr: IO[bytes]) -> str:
    stderr.seek(0)
    lines = stderr.read().decode("utf-8", errors="replace").strip().splitlines()
    return " | ".join(line.strip() for line in lines[-_TAIL_LINES:]) or "no message"
