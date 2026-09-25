"""Inspect audio stream facts and enumerate the pinned FFmpeg output matrix."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mtee.domain.conversion import (
    CodecCapabilities,
    ConversionItemPreview,
    ConversionPreview,
    ConversionRequest,
    MediaProbe,
    OutputCapability,
    new_preview_id,
)
from mtee.domain.tracks import SourceRevision
from mtee.services.ffmpeg_runtime import FfmpegRuntime

__all__ = ["MediaProbeError", "MediaProbeService"]

_RATES = (22_050, 32_000, 44_100, 48_000, 88_200, 96_000)
_OUTPUTS = (
    OutputCapability(
        "mp3",
        "MP3",
        ".mp3",
        "mp3",
        "libmp3lame",
        ("128k", "192k", "256k", "320k"),
        (22_050, 32_000, 44_100, 48_000),
        (1, 2),
        (),
        False,
    ),
    OutputCapability(
        "flac", "FLAC", ".flac", "flac", "flac", ("0", "5", "8"), _RATES, (1, 2), (16, 24), True
    ),
    OutputCapability(
        "wav",
        "WAV",
        ".wav",
        "wav",
        "pcm",
        ("16-bit PCM", "24-bit PCM"),
        _RATES,
        (1, 2),
        (16, 24),
        True,
    ),
    OutputCapability(
        "aiff",
        "AIFF",
        ".aiff",
        "aiff",
        "pcm",
        ("16-bit PCM", "24-bit PCM"),
        _RATES,
        (1, 2),
        (16, 24),
        True,
    ),
    OutputCapability(
        "vorbis",
        "Ogg Vorbis",
        ".ogg",
        "ogg",
        "libvorbis",
        ("q3", "q5", "q7"),
        _RATES,
        (1, 2),
        (),
        False,
    ),
    OutputCapability(
        "opus",
        "Opus",
        ".opus",
        "opus",
        "libopus",
        ("96k", "128k", "160k"),
        (48_000,),
        (1, 2),
        (),
        False,
    ),
    OutputCapability(
        "m4a-aac",
        "M4A · AAC",
        ".m4a",
        "ipod",
        "aac",
        ("128k", "192k", "256k"),
        (44_100, 48_000),
        (1, 2),
        (),
        False,
    ),
    OutputCapability(
        "m4a-alac",
        "M4A · ALAC",
        ".m4a",
        "ipod",
        "alac",
        ("lossless",),
        _RATES,
        (1, 2),
        (16, 24),
        True,
    ),
)


class MediaProbeError(RuntimeError):
    """An audio file could not be identified as a usable audio stream."""


class MediaProbeService:
    """Inspect stream content instead of trusting a filename suffix."""

    def __init__(self, runtime: FfmpegRuntime | None = None) -> None:
        self._runtime = runtime or FfmpegRuntime()
        self._capabilities: CodecCapabilities | None = None

    def inspect(self, path: Path | str) -> MediaProbe:
        source = Path(path)
        if not source.is_file():
            raise MediaProbeError("The source file is unavailable.")
        result = self._runtime.run(
            "ffprobe",
            [
                "-v",
                "error",
                "-show_entries",
                "format=format_name,duration,size:stream=codec_type,codec_name,sample_rate,"
                "channels,channel_layout,bits_per_sample,bits_per_raw_sample,bit_rate",
                "-of",
                "json",
                str(source),
            ],
            timeout_seconds=30,
        )
        if result.returncode != 0:
            raise MediaProbeError(
                _diagnostic(result.stderr, "FFprobe could not inspect this file.")
            )
        try:
            document = json.loads(result.stdout)
            audio_streams = [
                item for item in document.get("streams", []) if item.get("codec_type") == "audio"
            ]
            if not audio_streams:
                raise ValueError("No audio stream was found.")
            stream = audio_streams[0]
            raw_format = document.get("format", {})
            names = tuple(
                name.strip().casefold()
                for name in str(raw_format.get("format_name", "")).split(",")
                if name.strip()
            )
            duration = _optional_float(raw_format.get("duration"))
            size = _optional_int(raw_format.get("size")) or source.stat().st_size
            bits = _optional_int(stream.get("bits_per_raw_sample")) or _optional_int(
                stream.get("bits_per_sample")
            )
            suffix = source.suffix.casefold()
            container = _container_from_probe(names, suffix)
            return MediaProbe(
                path=source.resolve(),
                format_names=names,
                container=container,
                codec=str(stream.get("codec_name", "")).casefold(),
                duration_us=round(duration * 1_000_000) if duration is not None else None,
                sample_rate=_optional_int(stream.get("sample_rate")),
                channels=_optional_int(stream.get("channels")),
                channel_layout=str(stream.get("channel_layout", "")),
                bits_per_sample=bits,
                bitrate=_optional_int(stream.get("bit_rate"))
                or _optional_int(raw_format.get("bit_rate")),
                size_bytes=size,
            )
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
            raise MediaProbeError(f"FFprobe returned invalid audio details: {error}") from error

    def capabilities(self) -> CodecCapabilities:
        if self._capabilities is not None:
            return self._capabilities
        encoders = self._listed_items("encoders")
        muxers = self._listed_items("muxers")
        outputs = tuple(
            item
            for item in _OUTPUTS
            if _required_encoders(item).issubset(encoders) and item.muxer in muxers
        )
        self._capabilities = CodecCapabilities(
            ffmpeg_version=self._runtime.version("ffmpeg"),
            ffprobe_version=self._runtime.version("ffprobe"),
            outputs=outputs,
        )
        return self._capabilities

    def preview(self, request: ConversionRequest) -> ConversionPreview:
        capabilities = self.capabilities()
        capability = capabilities.for_format(request.settings.format_id)
        items = []
        destinations: set[str] = set()
        for source in request.sources:
            destination = request.destination / f"{source.path.stem}{_extension(capability)}"
            collision_key = str(destination.resolve(strict=False)).casefold()
            if capability is None:
                items.append(
                    ConversionItemPreview(
                        source,
                        None,
                        destination,
                        "unsupported",
                        "This output format is not available in the bundled FFmpeg build.",
                    )
                )
                continue
            if not _settings_supported(request, capability):
                items.append(
                    ConversionItemPreview(
                        source,
                        None,
                        destination,
                        "unsupported",
                        "These output settings are not supported for this format.",
                    )
                )
                continue
            try:
                probe = self.inspect(source.path)
                effective_settings = _effective_settings(request.settings, capability, probe)
                if effective_settings is None:
                    items.append(
                        ConversionItemPreview(
                            source,
                            probe,
                            destination,
                            "unsupported",
                            "Source depth is unknown or unsupported. Choose an explicit output depth.",
                        )
                    )
                    continue
                observed = SourceRevision.observe(
                    source.path, generation=source.revision.generation
                )
                if not source.revision.matches(observed):
                    items.append(
                        ConversionItemPreview(
                            source,
                            probe,
                            destination,
                            "conflict",
                            "The source changed. Refresh the library before converting it.",
                        )
                    )
                elif not request.destination.is_dir():
                    items.append(
                        ConversionItemPreview(
                            source,
                            probe,
                            destination,
                            "unsupported",
                            "Choose an existing output folder.",
                        )
                    )
                elif destination.exists():
                    items.append(
                        ConversionItemPreview(
                            source,
                            probe,
                            destination,
                            "collision",
                            "This output already exists and will not be overwritten.",
                        )
                    )
                elif collision_key in destinations:
                    items.append(
                        ConversionItemPreview(
                            source,
                            probe,
                            destination,
                            "collision",
                            "Two selected files have the same output name.",
                        )
                    )
                else:
                    destinations.add(collision_key)
                    items.append(
                        ConversionItemPreview(
                            source,
                            probe,
                            destination,
                            "ready",
                            estimated_size_bytes=_estimate_size(probe, request.settings),
                            effective_settings=effective_settings,
                        )
                    )
            except MediaProbeError as error:
                items.append(
                    ConversionItemPreview(source, None, destination, "unreadable", str(error))
                )
            except OSError as error:
                items.append(
                    ConversionItemPreview(
                        source,
                        None,
                        destination,
                        "unreadable",
                        f"Could not inspect the source file: {error}",
                    )
                )
        return ConversionPreview(
            preview_id=new_preview_id(),
            request=request,
            items=tuple(items),
            ffmpeg_version=capabilities.ffmpeg_version,
            created_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        )

    def _listed_items(self, listing: str) -> set[str]:
        result = self._runtime.run("ffmpeg", ["-hide_banner", f"-{listing}"], timeout_seconds=30)
        if result.returncode != 0:
            raise MediaProbeError(_diagnostic(result.stderr, f"Could not list FFmpeg {listing}."))
        items = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            if (listing == "encoders" and len(parts[0]) == 6 and "A" in parts[0]) or (
                listing == "muxers" and len(parts[0]) == 1 and "E" in parts[0]
            ):
                items.add(parts[1])
        return items


def _container_from_probe(names: tuple[str, ...], suffix: str) -> str:
    if suffix == ".m4a" and any(name in names for name in ("mov", "mp4", "m4a")):
        return "m4a"
    for container, aliases in (
        ("wav", {"wav"}),
        ("aiff", {"aiff"}),
        ("flac", {"flac"}),
        ("mp3", {"mp3"}),
        ("opus", {"opus"}),
        ("ogg", {"ogg"}),
        ("aac", {"aac", "adts"}),
    ):
        if aliases.intersection(names):
            return container
    return names[0] if names else suffix.removeprefix(".")


def _required_encoders(capability: OutputCapability) -> set[str]:
    if capability.encoder == "pcm":
        return {
            f"pcm_s{depth}{'le' if capability.format_id == 'wav' else 'be'}"
            for depth in capability.bit_depths
        }
    return {capability.encoder}


def _settings_supported(request: ConversionRequest, capability: OutputCapability) -> bool:
    settings = request.settings
    if settings.quality not in capability.qualities:
        return False
    if settings.sample_rate is not None and settings.sample_rate not in capability.sample_rates:
        return False
    if settings.channels is not None and settings.channels not in capability.channels:
        return False
    return settings.bit_depth is None or settings.bit_depth in capability.bit_depths


def _effective_settings(settings, capability: OutputCapability, probe: MediaProbe):
    effective_depth = settings.bit_depth
    if capability.bit_depths and effective_depth is None:
        source_depth = probe.bits_per_sample
        if source_depth not in capability.bit_depths:
            return None
        effective_depth = source_depth
    if effective_depth is not None and effective_depth not in capability.bit_depths:
        return None
    dither_applies = (
        settings.dither
        and settings.format_id in {"wav", "aiff"}
        and probe.bits_per_sample is not None
        and effective_depth is not None
        and effective_depth < probe.bits_per_sample
    )
    return replace(settings, bit_depth=effective_depth, dither=dither_applies)


def _extension(capability: OutputCapability | None) -> str:
    return capability.extension if capability is not None else ".audio"


def _estimate_size(probe: MediaProbe, settings: Any) -> int | None:
    if probe.duration_us is None:
        return None
    seconds = probe.duration_us / 1_000_000
    if settings.format_id in {"flac", "wav", "aiff", "m4a-alac"}:
        if settings.format_id in {"wav", "aiff"} or settings.format_id == "flac":
            depth = settings.bit_depth or probe.bits_per_sample or 16
            channels = settings.channels or probe.channels or 2
            rate = settings.sample_rate or probe.sample_rate or 44_100
            return round(seconds * rate * channels * depth / 8 * 1.05)
        return max(probe.size_bytes, round(seconds * 1_000_000))
    quality = settings.quality.removesuffix("k")
    if quality.isdigit():
        return round(seconds * int(quality) * 1000 / 8 * 1.08)
    return round(probe.size_bytes * 0.65)


def _optional_float(value: object) -> float | None:
    if not isinstance(value, (int, float, str)) or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 else None


def _optional_int(value: object) -> int | None:
    if not isinstance(value, (int, float, str)) or isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result > 0 else None


def _diagnostic(output: str, fallback: str) -> str:
    return output.strip()[-4096:] or fallback
