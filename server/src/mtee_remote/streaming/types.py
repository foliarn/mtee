"""Data types shared by the level rules, the transcoder and the stream routes.

`levels.plan()` turns a `SourceInfo` and a requested `Level` into a `DeliveryPlan`; the
transcoder only executes a plan, it never decides one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Level = Literal["original", "lossless", "320", "128"]
LEVELS: tuple[Level, ...] = ("original", "lossless", "320", "128")

# Codecs a client may accept. `alac` only matters for Apple clients at the lossless level.
ClientCodec = Literal["flac", "alac", "aac", "opus", "mp3"]
CLIENT_CODECS: frozenset[str] = frozenset({"flac", "alac", "aac", "opus", "mp3"})

# Output codecs the server produces. MP3 is never produced (architecture file, decision 11).
OutputCodec = Literal["flac", "aac", "opus"]


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """What the server knows about a stored audio file.

    `codec` uses ffmpeg's codec names (`flac`, `alac`, `mp3`, `aac`, `vorbis`, `opus`,
    `pcm_s16le`, `pcm_s24le`, `pcm_s16be`, ...). `lossless` is True for FLAC, ALAC, PCM and
    other lossless codecs. Unknown values are None.
    """

    codec: str
    lossless: bool
    sample_rate: int | None
    bit_depth: int | None
    bitrate: int | None  # bits per second
    channels: int | None


@dataclass(frozen=True, slots=True)
class DeliveryPlan:
    """What to send for one request.

    Either the original file (`send_original`), or a transcode described by the other fields.
    `key` names the transcode in the cache: two requests with the same source and the same
    key must produce the same bytes. `sample_rate` and `bit_depth` are the output values to
    force, or None to keep the source's.
    """

    send_original: bool
    codec: OutputCodec | None = None
    bitrate: int | None = None  # bits per second, lossy codecs only
    sample_rate: int | None = None
    bit_depth: int | None = None
    mime: str = "application/octet-stream"
    ext: str = ""
    key: str = "original"

    @classmethod
    def original(cls, mime: str, ext: str) -> DeliveryPlan:
        return cls(send_original=True, mime=mime, ext=ext, key="original")
