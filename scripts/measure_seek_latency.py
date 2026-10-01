"""Measure how long libmpv takes to land on a position after ``seek`` (plan 100.3).

For each synthetic WAV, FLAC and MP3 file of two minutes, generated in a temporary
folder with the bundled FFmpeg, the script starts playback with the ``null`` audio
output (nothing is played), seeks to random positions with the backend's
``absolute+exact`` mode and polls the audio position (``audio-pts``, which only moves
once the audio chain has restarted at the target; ``time-pos`` jumps to the target at
once and says nothing about the sound) every millisecond until it reaches the target.
The delay is the time between the command and an audio position at or after the target,
so it covers the demuxer and the decoder but not the buffer of a real audio device,
which adds a fixed delay of its own.

    uv run python scripts/measure_seek_latency.py
"""

from __future__ import annotations

import argparse
import ctypes
import random
import statistics
import tempfile
import time
from pathlib import Path

from mtee.services.ffmpeg_runtime import FfmpegRuntime
from mtee.services.mpv_backend import MpvBackend

ROOT = Path(__file__).resolve().parents[1]
FORMATS = (
    ("wav", ("-c:a", "pcm_s16le")),
    ("flac", ("-c:a", "flac")),
    ("mp3", ("-c:a", "libmp3lame", "-q:a", "2")),
)
DURATION_SECONDS = 120


def create(folder: Path, extension: str, encoding: tuple[str, ...]) -> Path:
    target = folder / f"latency.{extension}"
    arguments = [
        "-hide_banner",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        f"anoisesrc=color=pink:duration={DURATION_SECONDS}:sample_rate=44100",
        "-ac",
        "2",
        *encoding,
        str(target),
    ]
    result = FfmpegRuntime().run("ffmpeg", arguments, timeout_seconds=120)
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(f"FFmpeg could not create {target.name}: {result.stderr[-300:]}")
    return target


def wait_for(condition, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.001)
    return False


def audio_position_us(backend: MpvBackend) -> int:
    """Return mpv's ``audio-pts`` in microseconds, or -1 while it is unavailable."""
    value = ctypes.c_double()
    # A format code of 5 is MPV_FORMAT_DOUBLE; the backend keeps its handle private.
    library, context = getattr(backend, "_lib"), getattr(backend, "_ctx")  # noqa: B009
    result = library.mpv_get_property(context, b"audio-pts", 5, ctypes.byref(value))
    return round(value.value * 1_000_000) if result >= 0 else -1


def measure(path: Path, seeks: int) -> list[float]:
    backend = MpvBackend(audio_output="null")
    delays: list[float] = []
    try:
        backend.load(path, 1)
        if not wait_for(lambda: (backend.position_us() or -1) >= 0):
            raise RuntimeError("playback did not start")
        generator = random.Random(7)
        for _ in range(seeks):
            target_us = generator.randrange(5_000_000, (DURATION_SECONDS - 10) * 1_000_000)
            started = time.perf_counter()
            backend.seek(target_us)
            low, high = target_us - 30_000, target_us + 400_000
            reached = wait_for(lambda lo=low, hi=high: lo <= audio_position_us(backend) <= hi)
            if reached:
                delays.append((time.perf_counter() - started) * 1000)
            time.sleep(0.05)
    finally:
        backend.close()
    return delays


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeks", type=int, default=30)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="mtee-seek-") as folder:
        for extension, encoding in FORMATS:
            path = create(Path(folder), extension, encoding)
            delays = measure(path, args.seeks)
            if not delays:
                print(f"{extension}: no seek reached its target")
                continue
            ordered = sorted(delays)
            print(
                f"{extension}: {len(delays)}/{args.seeks} seeks, median "
                f"{statistics.median(delays):.1f} ms, p95 "
                f"{ordered[int(0.95 * (len(ordered) - 1))]:.1f} ms, max {ordered[-1]:.1f} ms"
            )
            path.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
