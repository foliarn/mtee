"""Immutable contracts for probing, converting, and relating derived audio."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mtee.domain.tracks import SourceRevision

__all__ = [
    "CodecCapabilities",
    "ConversionItemPreview",
    "ConversionPreview",
    "ConversionRequest",
    "ConversionResult",
    "ConversionSettings",
    "ConversionSource",
    "Derivation",
    "MediaProbe",
    "OutputCapability",
]


@dataclass(frozen=True, slots=True)
class MediaProbe:
    path: Path
    format_names: tuple[str, ...]
    container: str
    codec: str
    duration_us: int | None
    sample_rate: int | None
    channels: int | None
    channel_layout: str
    bits_per_sample: int | None
    bitrate: int | None
    size_bytes: int

    def __post_init__(self) -> None:
        if self.duration_us is not None and self.duration_us < 0:
            raise ValueError("duration_us must not be negative")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")


@dataclass(frozen=True, slots=True)
class OutputCapability:
    format_id: str
    label: str
    extension: str
    muxer: str
    encoder: str
    qualities: tuple[str, ...]
    sample_rates: tuple[int, ...]
    channels: tuple[int, ...]
    bit_depths: tuple[int, ...]
    lossless: bool


@dataclass(frozen=True, slots=True)
class CodecCapabilities:
    ffmpeg_version: str
    ffprobe_version: str
    outputs: tuple[OutputCapability, ...]

    def for_format(self, format_id: str) -> OutputCapability | None:
        return next((item for item in self.outputs if item.format_id == format_id), None)


@dataclass(frozen=True, slots=True)
class ConversionSource:
    track_id: str
    path: Path
    revision: SourceRevision


@dataclass(frozen=True, slots=True)
class ConversionSettings:
    format_id: str
    quality: str
    sample_rate: int | None = None
    channels: int | None = None
    bit_depth: int | None = None
    dither: bool = False
    copy_metadata: bool = True

    def __post_init__(self) -> None:
        if not self.format_id or not self.quality:
            raise ValueError("format_id and quality are required")
        if self.sample_rate is not None and self.sample_rate not in {
            8000,
            11025,
            16000,
            22050,
            32000,
            44100,
            48000,
            88200,
            96000,
            176400,
            192000,
        }:
            raise ValueError("sample_rate is outside the supported conversion rates")
        if self.channels is not None and self.channels not in {1, 2}:
            raise ValueError("channels must be mono or stereo")
        if self.bit_depth is not None and self.bit_depth not in {16, 24, 32}:
            raise ValueError("bit_depth must be 16, 24, or 32")


@dataclass(frozen=True, slots=True)
class ConversionRequest:
    sources: tuple[ConversionSource, ...]
    destination: Path
    settings: ConversionSettings

    def __post_init__(self) -> None:
        if not self.sources:
            raise ValueError("at least one source is required")
        if len({item.track_id for item in self.sources}) != len(self.sources):
            raise ValueError("a source may appear only once in a conversion request")
        if not self.destination:
            raise ValueError("a destination folder is required")


@dataclass(frozen=True, slots=True)
class ConversionItemPreview:
    source: ConversionSource
    probe: MediaProbe | None
    destination: Path
    status: str
    message: str = ""
    estimated_size_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ready", "unsupported", "conflict", "collision", "unreadable"}:
            raise ValueError(f"unknown conversion preview status: {self.status}")


@dataclass(frozen=True, slots=True)
class ConversionPreview:
    preview_id: str
    request: ConversionRequest
    items: tuple[ConversionItemPreview, ...]
    ffmpeg_version: str
    created_at_utc: str

    @property
    def executable(self) -> bool:
        return bool(self.items) and all(item.status == "ready" for item in self.items)


@dataclass(frozen=True, slots=True)
class Derivation:
    source_track_id: str
    source_revision: SourceRevision
    derived_track_id: str
    conversion_id: str
    parameters: tuple[tuple[str, Any], ...]
    time_mapping_status: str

    def __post_init__(self) -> None:
        if self.time_mapping_status not in {"identity", "converted", "unknown"}:
            raise ValueError("time_mapping_status must be identity, converted, or unknown")


@dataclass(frozen=True, slots=True)
class ConversionResult:
    conversion_id: str
    source_track_id: str
    source: Path
    destination: Path
    status: str
    message: str = ""
    source_sha256: str = ""
    output_sha256: str = ""
    output_probe: MediaProbe | None = None
    metadata_report: tuple[tuple[str, str], ...] = ()
    derivation: Derivation | None = None

    def __post_init__(self) -> None:
        if self.status not in {"completed", "failed", "cancelled", "conflict", "unsupported"}:
            raise ValueError(f"unknown conversion result status: {self.status}")


def new_preview_id() -> str:
    """Create an identifier for one immutable preview."""
    return str(uuid.uuid4())
