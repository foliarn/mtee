"""Verified FFmpeg conversion into new audio files."""

from __future__ import annotations

import base64
import copy
import os
import queue
import subprocess
import threading
import uuid
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.aiff import AIFF
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

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

    def inspect(self, source: Path | str):
        return self._probe.inspect(source)

    def capabilities(self):
        return self._probe.capabilities()

    def preview(self, request):
        return self._probe.preview(request)

    def read_metadata(self, source: Path | str):
        """Read a finished output snapshot on the caller's worker thread."""
        return self._metadata_reader.read(source)

    def _transfer_metadata(self, source: Path, destination: Path) -> dict[str, str]:
        source_snapshot = self._metadata_reader.read(source)
        adapter = next(
            (item for item in self._metadata_adapters if item.supports_path(destination)), None
        )
        report: dict[str, str] = {}
        if adapter is None:
            report.update({field: "No verified writer for output format" for field, _ in _FIELDS})
        else:
            capabilities = adapter.capabilities(destination)
            changes = {}
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
        report["cover_art"] = self._transfer_cover_art(source, destination)
        return report

    def _transfer_cover_art(self, source: Path, destination: Path) -> str:
        try:
            source_audio = MutagenFile(source, easy=False)
            destination_audio = MutagenFile(destination, easy=False)
            source_covers = _cover_items(source_audio)
            if source_covers is None or not source_covers[1]:
                return "No source artwork"
            if destination_audio is None:
                return "Not transferred: output container has no verified artwork adapter."
            source_kind, covers = source_covers
            destination_kind = _cover_kind(destination_audio)
            if source_kind != destination_kind or destination_kind is None:
                return (
                    "Not transferred: the source artwork format is incompatible "
                    "with this output container."
                )
            if destination_kind == "id3":
                if destination_audio.tags is None:
                    destination_audio.add_tags()
                tags = destination_audio.tags
                assert isinstance(tags, ID3)
                tags.delall("APIC")
                for cover in covers:
                    tags.add(copy.deepcopy(cover))
            elif destination_kind == "mp4":
                destination_audio.tags["covr"] = [copy.deepcopy(cover) for cover in covers]
            elif destination_kind == "flac":
                assert isinstance(destination_audio, FLAC)
                destination_audio.clear_pictures()
                for cover in covers:
                    destination_audio.add_picture(copy.deepcopy(cover))
            elif destination_kind == "vorbis":
                destination_audio.tags["metadata_block_picture"] = [
                    base64.b64encode(cover.write()).decode("ascii") for cover in covers
                ]
            destination_audio.save()
            verified_audio = MutagenFile(destination, easy=False)
            verified = _cover_items(verified_audio)
            if verified is None or verified[0] != source_kind:
                return "Not transferred: the output artwork could not be verified."
            if tuple(_cover_signature(item) for item in verified[1]) != tuple(
                _cover_signature(item) for item in covers
            ):
                return "Not transferred: the output artwork differs from the source."
            return "Copied and verified"
        except Exception as error:
            return f"Not transferred: {type(error).__name__} while copying or verifying artwork."

    def convert_item(
        self,
        preview: ConversionPreview,
        item: ConversionItemPreview,
        *,
        conversion_id: str | None = None,
        is_cancelled: Callable[[], bool] = lambda: False,
        report_progress: Callable[[float], None] = lambda _value: None,
        before_publish: Callable[[str, str, str, object, tuple[tuple[str, str], ...]], None]
        | None = None,
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
        stdout_thread = None
        stop_readers = threading.Event()
        progress_lines: queue.Queue[bytes | None] = queue.Queue(maxsize=32)
        temporary_owned = False
        source_hash = ""
        settings = item.effective_settings or preview.request.settings
        try:
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
            try:
                descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                return ConversionResult(
                    conversion_id,
                    item.source.track_id,
                    item.source.path,
                    item.destination,
                    "conflict",
                    "The operation's temporary path is already occupied.",
                    source_hash,
                )
            os.close(descriptor)
            temporary_owned = True
            process = self._runtime.start(
                "ffmpeg",
                _arguments(item.source.path, temporary, settings),
            )
            if process.stdout is None or process.stderr is None:
                raise RuntimeError("FFmpeg progress pipes could not be opened.")
            stderr_thread = threading.Thread(
                target=_drain_tail, args=(process.stderr, diagnostic), daemon=True
            )
            stdout_thread = threading.Thread(
                target=_drain_progress,
                args=(process.stdout, progress_lines, stop_readers),
                daemon=True,
            )
            stderr_thread.start()
            stdout_thread.start()
            output_closed = False
            while process.poll() is None or not output_closed:
                if is_cancelled():
                    stop_readers.set()
                    _stop_process(process)
                    raise JobCancelledError(conversion_id)
                try:
                    raw_line = progress_lines.get(timeout=0.05)
                except queue.Empty:
                    continue
                if raw_line is None:
                    output_closed = True
                    continue
                line = raw_line.decode("ascii", errors="replace").strip()
                if line.startswith("out_time_ms=") and item.probe.duration_us:
                    try:
                        fraction = int(line.partition("=")[2]) / item.probe.duration_us
                    except ValueError:
                        continue
                    report_progress(min(0.98, max(0.0, fraction)))
            return_code = process.wait()
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
            if return_code != 0:
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
                if settings.copy_metadata
                else {
                    **{field: "Not copied by the selected option" for field, _ in _FIELDS},
                    "cover_art": "Not copied by the selected option",
                }
            )
            output = self._probe.inspect(temporary)
            metadata_report = _metadata_report(
                self._metadata_reader.read(item.source.path),
                self._metadata_reader.read(temporary),
                transfer_report,
            )
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
            output_hash = sha256_of_file(temporary)
            final_observation = SourceRevision.observe(
                item.source.path, generation=item.source.revision.generation
            )
            if (
                not item.source.revision.matches(final_observation)
                or sha256_of_file(item.source.path) != source_hash
            ):
                return ConversionResult(
                    conversion_id,
                    item.source.track_id,
                    item.source.path,
                    item.destination,
                    "conflict",
                    "The source changed before publication.",
                    source_hash,
                )
            derivation = Derivation(
                item.source.track_id,
                item.source.revision,
                item.derived_track_id or str(uuid.uuid4()),
                conversion_id,
                tuple(
                    sorted(
                        (name, getattr(settings, name)) for name in settings.__dataclass_fields__
                    )
                ),
                "converted",
            )
            if before_publish is not None:
                before_publish(
                    source_hash,
                    output_hash,
                    str(temporary),
                    output,
                    metadata_report,
                )
            # A hard link atomically creates the final path without replacement.
            os.link(temporary, item.destination)
            try:
                temporary.unlink()
                temporary_owned = False
            except OSError:
                pass
            report_progress(1.0)
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
            stop_readers.set()
            if process is not None and process.poll() is None:
                _stop_process(process)
            if stdout_thread is not None:
                stdout_thread.join(timeout=1)
            if stderr_thread is not None:
                stderr_thread.join(timeout=1)
            if process is not None:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        with suppress(OSError):
                            stream.close()
            if temporary_owned:
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
        "-map_metadata",
        "0" if settings.copy_metadata else "-1",
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


def _drain_progress(stream, destination: queue.Queue[bytes | None], stop: threading.Event) -> None:
    try:
        while line := stream.readline():
            while not stop.is_set():
                try:
                    destination.put(line, timeout=0.05)
                    break
                except queue.Full:
                    continue
            if stop.is_set():
                return
    finally:
        while not stop.is_set():
            try:
                destination.put(None, timeout=0.05)
                break
            except queue.Full:
                continue


def _stop_process(process) -> None:
    if process.poll() is not None:
        return
    with suppress(OSError):
        process.terminate()
    try:
        process.wait(timeout=1)
        return
    except subprocess.TimeoutExpired:
        pass
    with suppress(OSError):
        process.kill()
    with suppress(Exception):
        process.wait()


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
    report.append(("Cover art", transfer_report.get("cover_art", "Not transferred or verified")))
    return tuple(report)


def _cover_kind(audio) -> str | None:
    if audio is None:
        return None
    tags = getattr(audio, "tags", None)
    if isinstance(audio, (AIFF, MP3, WAVE)) or isinstance(tags, ID3):
        return "id3"
    if isinstance(audio, MP4):
        return "mp4"
    if isinstance(audio, FLAC):
        return "flac"
    if isinstance(audio, (OggVorbis, OggOpus)):
        return "vorbis"
    return None


def _cover_items(audio):
    kind = _cover_kind(audio)
    if kind is None:
        return None
    tags = getattr(audio, "tags", None)
    if kind == "id3":
        values = tags.getall("APIC") if tags is not None else ()
    elif kind == "mp4":
        values = tags.get("covr", ()) if tags is not None else ()
    elif kind == "flac":
        values = audio.pictures
    else:
        encoded = tags.get("metadata_block_picture", ()) if tags is not None else ()
        values = [Picture(base64.b64decode(str(item), validate=True)) for item in encoded]
    return kind, tuple(values)


def _cover_signature(item):
    if isinstance(item, MP4Cover):
        return (bytes(item), int(item.imageformat))
    if isinstance(item, Picture):
        return (
            int(item.type),
            str(item.mime),
            str(item.desc),
            int(item.width),
            int(item.height),
            int(item.depth),
            int(item.colors),
            bytes(item.data),
        )
    if getattr(item, "FrameID", "") == "APIC":
        return (str(item.mime), int(item.type), str(item.desc), bytes(item.data))
    return repr(item)
