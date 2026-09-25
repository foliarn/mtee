"""Verified FFmpeg conversion into new audio files."""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from mtee.domain.conversion import (
    ConversionItemPreview,
    ConversionPreview,
    ConversionResult,
    Derivation,
)
from mtee.domain.jobs import JobCancelledError
from mtee.domain.metadata_edit import MetadataPatch
from mtee.domain.tracks import SourceRevision, sha256_of_file
from mtee.services.ffmpeg_runtime import FfmpegRuntime
from mtee.services.media_probe import MediaProbeService
from mtee.services.metadata_adapters.base import MetadataAdapter
from mtee.services.metadata_adapters.id3 import Id3WaveAdapter
from mtee.services.metadata_adapters.mp4 import MP4MetadataAdapter
from mtee.services.metadata_adapters.vorbis import VorbisCommentAdapter
from mtee.services.metadata_reader import MetadataReader

__all__ = ["ConversionService"]

_FORMATS = {
    "mp3": ("libmp3lame", "mp3", "mp3"),
    "flac": ("flac", "flac", "flac"),
    "wav": ("pcm", "wav", "pcm_s16le"),
    "aiff": ("pcm", "aiff", "pcm_s16be"),
    "vorbis": ("libvorbis", "ogg", "vorbis"),
    "opus": ("libopus", "opus", "opus"),
    "m4a-aac": ("aac", "ipod", "aac"),
    "m4a-alac": ("alac", "ipod", "alac"),
}
_TOLERANCE_US = 150_000
_MAX_DIAGNOSTIC_BYTES = 16 * 1024


class ConversionService:
    """Convert with at most two FFmpeg processes and atomic create-if-absent publish."""

    def __init__(self, runtime: FfmpegRuntime | None = None) -> None:
        self._runtime = runtime or FfmpegRuntime()
        self._probe = MediaProbeService(self._runtime)
        self._metadata_reader = MetadataReader()
        self._metadata_adapters: tuple[MetadataAdapter, ...] = (
            Id3WaveAdapter(),
            VorbisCommentAdapter(),
            MP4MetadataAdapter(),
        )
        self._workers = threading.BoundedSemaphore(2)

    def inspect(self, source: Path | str):
        return self._probe.inspect(source)

    def capabilities(self):
        return self._probe.capabilities()

    def preview(self, request):
        return self._probe.preview(request)

    def _transfer_metadata(self, source: Path, destination: Path) -> dict[str, str]:
        source_snapshot = self._metadata_reader.read(source)
        adapter = next(
            (item for item in self._metadata_adapters if item.supports_path(destination)), None
        )
        if adapter is None:
            return {field: "No verified writer for output format" for field, _ in _FIELDS}
        capabilities = adapter.capabilities(destination)
        changes = {}
        report = {}
        for field, _label in _FIELDS:
            values = getattr(source_snapshot, field)
            editable, reason = capabilities.get(field, (False, "Field is not supported."))
            if len(values) == 1 and editable:
                changes[field] = values[0]
                report[field] = "Pending verification"
            elif len(values) > 1:
                report[field] = "Not transferred: multiple source values."
            elif values and not editable:
                report[field] = f"Not transferred: {reason}"
            else:
                report[field] = "No source value"
        if changes:
            patch = MetadataPatch.from_mapping(changes)
            audio, preserved = adapter.prepare(destination, patch)
            adapter.save(audio, destination)
            adapter.verify(destination, preserved, patch)
        return report

    def convert_item(
        self,
        preview: ConversionPreview,
        item: ConversionItemPreview,
        *,
        conversion_id: str | None = None,
        is_cancelled: Callable[[], bool] = lambda: False,
        report_progress: Callable[[float], None] = lambda _value: None,
    ) -> ConversionResult:
        conversion_id = conversion_id or str(uuid.uuid4())
        if item.status != "ready" or item.probe is None:
            return ConversionResult(
                conversion_id,
                item.source.track_id,
                item.source.path,
                item.destination,
                item.status,
                item.message,
            )
        with self._workers:
            if is_cancelled():
                raise JobCancelledError(conversion_id)
            current = SourceRevision.observe(
                item.source.path, generation=item.source.revision.generation
            )
            if not item.source.revision.matches(current):
                return ConversionResult(
                    conversion_id,
                    item.source.track_id,
                    item.source.path,
                    item.destination,
                    "conflict",
                    "The source changed after the preview.",
                )
            source_hash = sha256_of_file(item.source.path)
            temporary = item.destination.with_name(
                f".{item.destination.stem}.mtee-{conversion_id}.tmp{item.destination.suffix}"
            )
            process = None
            diagnostic = bytearray()
            stderr_thread = None
            try:
                process = self._runtime.start(
                    "ffmpeg",
                    _arguments(item.source.path, temporary, preview.request.settings),
                )
                if process.stdout is None or process.stderr is None:
                    raise RuntimeError("FFmpeg progress pipes could not be opened.")
                stderr_thread = threading.Thread(
                    target=_drain_tail, args=(process.stderr, diagnostic), daemon=True
                )
                stderr_thread.start()
                for raw_line in process.stdout:
                    if is_cancelled():
                        process.terminate()
                        with suppress(Exception):
                            process.wait(timeout=1)
                        if process.poll() is None:
                            process.kill()
                        raise JobCancelledError(conversion_id)
                    line = raw_line.decode("ascii", errors="replace").strip()
                    if line.startswith("out_time_ms=") and item.probe.duration_us:
                        try:
                            fraction = int(line.partition("=")[2]) / item.probe.duration_us
                        except ValueError:
                            continue
                        report_progress(min(0.98, max(0.0, fraction)))
                if process.wait(timeout=10) != 0:
                    return ConversionResult(
                        conversion_id,
                        item.source.track_id,
                        item.source.path,
                        item.destination,
                        "failed",
                        _diagnostic(diagnostic),
                        source_hash,
                    )
                if is_cancelled():
                    raise JobCancelledError(conversion_id)
                observed = SourceRevision.observe(
                    item.source.path, generation=item.source.revision.generation
                )
                if (
                    not item.source.revision.matches(observed)
                    or sha256_of_file(item.source.path) != source_hash
                ):
                    return ConversionResult(
                        conversion_id,
                        item.source.track_id,
                        item.source.path,
                        item.destination,
                        "conflict",
                        "The source changed during conversion.",
                        source_hash,
                    )
                transfer_report = (
                    self._transfer_metadata(item.source.path, temporary)
                    if preview.request.settings.copy_metadata
                    else {field: "Not copied by the selected option" for field, _ in _FIELDS}
                )
                output = self._probe.inspect(temporary)
                metadata_report = _metadata_report(
                    self._metadata_reader.read(item.source.path),
                    self._metadata_reader.read(temporary),
                    transfer_report,
                )
                settings = preview.request.settings
                expected = _expected_codec(settings)
                if output.codec != expected or output.duration_us is None:
                    raise ValueError(
                        f"Output verification failed: expected {expected}, got {output.codec}."
                    )
                if (
                    item.probe.duration_us is not None
                    and abs(output.duration_us - item.probe.duration_us) > _TOLERANCE_US
                ):
                    raise ValueError("Output duration is outside the measured tolerance.")
                if settings.sample_rate is not None and output.sample_rate != settings.sample_rate:
                    raise ValueError("Output sample rate does not match the selected setting.")
                if settings.channels is not None and output.channels != settings.channels:
                    raise ValueError("Output channel count does not match the selected setting.")
                if (
                    settings.bit_depth is not None
                    and output.bits_per_sample is not None
                    and output.bits_per_sample != settings.bit_depth
                ):
                    raise ValueError("Output sample depth does not match the selected setting.")
                # A hard link is an atomic create-if-absent operation on the destination volume.
                os.link(temporary, item.destination)
                temporary.unlink()
                output_hash = sha256_of_file(item.destination)
                report_progress(1.0)
                settings = preview.request.settings
                derivation = Derivation(
                    item.source.track_id,
                    item.source.revision,
                    str(uuid.uuid4()),
                    conversion_id,
                    tuple(
                        sorted(
                            (name, getattr(settings, name))
                            for name in settings.__dataclass_fields__
                        )
                    ),
                    "converted",
                )
                return ConversionResult(
                    conversion_id,
                    item.source.track_id,
                    item.source.path,
                    item.destination,
                    "completed",
                    "Output verified and published.",
                    source_hash,
                    output_hash,
                    output,
                    metadata_report,
                    derivation,
                )
            except FileExistsError:
                return ConversionResult(
                    conversion_id,
                    item.source.track_id,
                    item.source.path,
                    item.destination,
                    "conflict",
                    "The output appeared during publication and was not replaced.",
                    source_hash,
                )
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    with suppress(Exception):
                        process.wait(timeout=1)
                    if process.poll() is None:
                        process.kill()
                if stderr_thread is not None:
                    stderr_thread.join(timeout=1)
                with suppress(OSError):
                    temporary.unlink()


def _arguments(source: Path, destination: Path, settings) -> list[str]:
    encoder, muxer, _ = _FORMATS[settings.format_id]
    args = [
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-progress",
        "pipe:1",
        "-nostats",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        *(["-map_metadata", "0"] if settings.copy_metadata else []),
        "-vn",
        "-sn",
        "-dn",
        "-c:a",
        encoder,
    ]
    if settings.format_id == "mp3" or settings.format_id in {"opus", "m4a-aac"}:
        args.extend(["-b:a", settings.quality])
    elif settings.format_id == "flac":
        args.extend(["-compression_level", settings.quality])
    elif settings.format_id == "vorbis":
        args.extend(["-q:a", settings.quality.removeprefix("q")])
    if settings.format_id in {"wav", "aiff"}:
        depth = settings.bit_depth or (24 if "24" in settings.quality else 16)
        endian = "le" if settings.format_id == "wav" else "be"
        args[args.index("pcm")] = f"pcm_s{depth}{endian}"
    if settings.format_id == "m4a-alac":
        args.extend(["-sample_fmt", "s32p" if settings.bit_depth == 24 else "s16p"])
    if settings.sample_rate is not None:
        args.extend(["-ar", str(settings.sample_rate)])
    if settings.channels is not None:
        args.extend(["-ac", str(settings.channels)])
    if settings.dither and settings.format_id in {"wav", "aiff"}:
        args.extend(["-af", "aresample=dither_method=triangular"])
    args.extend(["-f", muxer, "-y", str(destination)])
    return args


def _drain_tail(stream, destination: bytearray) -> None:
    while block := stream.read(4096):
        destination.extend(block)
        if len(destination) > _MAX_DIAGNOSTIC_BYTES:
            del destination[:-_MAX_DIAGNOSTIC_BYTES]


def _diagnostic(destination: bytearray) -> str:
    return (
        bytes(destination).decode("utf-8", errors="replace").strip()[-4096:]
        or "FFmpeg conversion failed."
    )


def _expected_codec(settings) -> str:
    base = _FORMATS[settings.format_id][2]
    if settings.format_id in {"wav", "aiff"}:
        depth = settings.bit_depth or (24 if "24" in settings.quality else 16)
        endian = "le" if settings.format_id == "wav" else "be"
        return f"pcm_s{depth}{endian}"
    return base


_FIELDS = (
    ("title", "Title"),
    ("artist", "Artist"),
    ("album", "Album"),
    ("genre", "Genre"),
    ("date", "Date"),
    ("track_number", "Track number"),
    ("bpm", "BPM"),
    ("key", "Key"),
    ("comment", "Comment"),
)


def _metadata_report(source, output, transfer_report) -> tuple[tuple[str, str], ...]:
    report = []
    for field, label in _FIELDS:
        original = getattr(source, field)
        converted = getattr(output, field)
        if not original:
            status = "No source value"
        elif converted == original:
            status = "Copied and verified"
        elif not converted:
            status = transfer_report.get(field, "Not present in output")
        else:
            status = "Changed representation"
        report.append((label, status))
    report.append(("Cover art", "Not transferred or verified by this conversion build"))
    return tuple(report)
