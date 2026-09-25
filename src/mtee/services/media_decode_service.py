"""Bounded, cancellable decoding to signed 16-bit little-endian PCM blocks."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, BinaryIO, Protocol, cast

from mtee.domain.conversion import ConversionSource
from mtee.domain.jobs import JobCancelledError
from mtee.domain.tracks import TrackId
from mtee.services.ffmpeg_runtime import FfmpegRuntime
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError

__all__ = ["MediaDecodeError", "MediaDecodeService", "PCMFormat", "PCMStream"]
_MAX_BLOCK_BYTES = 1024 * 1024
_MAX_DIAGNOSTIC_BYTES = 16 * 1024


class _Process(Protocol):
    stdout: IO[bytes] | None
    stderr: IO[bytes] | None

    def poll(self) -> int | None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...


class _StreamingRuntime(Protocol):
    def start(self, tool: str, arguments: list[str]) -> _Process: ...


class MediaDecodeError(RuntimeError):
    """An expected FFmpeg decode error or unavailable input."""


@dataclass(frozen=True, slots=True)
class PCMFormat:
    sample_rate: int
    channels: int
    sample_format: str = "s16le"

    @property
    def bytes_per_frame(self) -> int:
        return self.channels * 2


@dataclass(frozen=True, slots=True)
class PCMStream:
    format: PCMFormat
    duration_us: int | None
    blocks: Iterator[bytes]

    def __iter__(self) -> Iterator[bytes]:
        return self.blocks


class MediaDecodeService:
    """Decode audio to bounded chunks without using the player state."""

    def __init__(
        self,
        file_access: FileAccessCoordinator,
        *,
        runtime: _StreamingRuntime | None = None,
    ) -> None:
        self._file_access = file_access
        self._runtime = runtime or FfmpegRuntime()

    def stream_pcm(
        self,
        source: ConversionSource | Path | str,
        *,
        sample_rate: int = 44_100,
        channels: int = 2,
        duration_us: int | None = None,
        block_bytes: int = 64 * 1024,
        read_lease_held: bool = False,
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> PCMStream:
        if not 8_000 <= sample_rate <= 192_000:
            raise ValueError("sample_rate must be between 8000 and 192000 Hz")
        if channels not in {1, 2}:
            raise ValueError("channels must be mono or stereo")
        frame_bytes = channels * 2
        if not frame_bytes <= block_bytes <= _MAX_BLOCK_BYTES:
            raise ValueError("block_bytes must be between one frame and 1 MiB")
        block_bytes -= block_bytes % frame_bytes
        path = source.path if isinstance(source, ConversionSource) else Path(source)
        track_id = source.track_id if isinstance(source, ConversionSource) else None
        if not path.is_file():
            raise MediaDecodeError(f"The audio source is unavailable: {path}")
        pcm_format = PCMFormat(sample_rate, channels)
        return PCMStream(
            pcm_format,
            duration_us,
            self._decode(
                path, track_id, pcm_format, block_bytes, is_cancelled, read_lease_held
            ),
        )

    def _decode(
        self,
        path: Path,
        track_id: str | None,
        pcm_format: PCMFormat,
        block_bytes: int,
        is_cancelled: Callable[[], bool],
        read_lease_held: bool,
    ) -> Iterator[bytes]:
        lease = None
        process: _Process | None = None
        stderr_tail = bytearray()
        drain: threading.Thread | None = None
        try:
            if track_id is not None and not read_lease_held:
                lease = self._file_access.acquire_read(
                    TrackId.parse(track_id), "audio decode", timeout_seconds=0
                )
                lease.__enter__()
            args = [
                "-hide_banner",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-vn",
                "-sn",
                "-dn",
                "-f",
                pcm_format.sample_format,
                "-acodec",
                "pcm_s16le",
                "-ar",
                str(pcm_format.sample_rate),
                "-ac",
                str(pcm_format.channels),
                "pipe:1",
            ]
            process = cast(_Process, self._runtime.start("ffmpeg", args))
            stdout = process.stdout
            stderr = process.stderr
            if stdout is None or stderr is None:
                raise MediaDecodeError("The FFmpeg PCM pipes could not be opened.")
            drain = threading.Thread(target=_drain_tail, args=(stderr, stderr_tail), daemon=True)
            drain.start()
            while True:
                if is_cancelled():
                    _stop_process(process)
                    raise JobCancelledError("audio decode cancelled")
                block = stdout.read(block_bytes)
                if not block:
                    break
                if len(block) % pcm_format.bytes_per_frame:
                    raise MediaDecodeError("FFmpeg returned a partial PCM audio frame.")
                yield block
            return_code = process.wait(timeout=3)
            if drain is not None:
                drain.join(timeout=1)
            if return_code != 0:
                details = bytes(stderr_tail).decode("utf-8", errors="replace").strip()
                raise MediaDecodeError(details or f"FFmpeg exited with code {return_code}.")
        except FileAccessTimeoutError:
            raise MediaDecodeError(
                "Stop playback or wait for the audio file before decoding."
            ) from None
        finally:
            if process is not None and process.poll() is None:
                _stop_process(process)
            if drain is not None:
                drain.join(timeout=1)
            if lease is not None:
                lease.__exit__(None, None, None)


def _drain_tail(stream: BinaryIO, destination: bytearray) -> None:
    while block := stream.read(4096):
        destination.extend(block)
        if len(destination) > _MAX_DIAGNOSTIC_BYTES:
            del destination[:-_MAX_DIAGNOSTIC_BYTES]


def _stop_process(process: _Process) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=1)
    except (subprocess.TimeoutExpired, TimeoutError, OSError):
        process.kill()
        process.wait(timeout=2)
