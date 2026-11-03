"""What the server knows about a stored audio file (plan 127.0).

The codec, sample rate and bit depth come from MTEE's metadata snapshot when it can name them
(no I/O). When it cannot, `probe()` asks ffprobe. The result is a `SourceInfo` from `types.py`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from mtee_remote import tools
from mtee_remote.streaming.types import SourceInfo

_PROBE_TIMEOUT_S = 60
_PROBE_ENTRIES = (
    "stream=codec_name,sample_rate,bits_per_raw_sample,bits_per_sample,bit_rate,channels"
    ":format=bit_rate"
)
_LOSSLESS_CODECS = frozenset({"flac", "alac", "wavpack", "ape", "tta", "mlp", "truehd"})

# MTEE stores the Mutagen class name as `codec`; `read_metadata` reads with easy=True, so the
# name may carry an "Easy" prefix (EasyMP3). MP4 is left out on purpose: TechnicalInfo reports
# "MP4" for both AAC and ALAC, so the metadata cannot tell them apart and the probe decides.
_MUTAGEN_CODECS: dict[str, str] = {
    "FLAC": "flac",
    "OggFLAC": "flac",
    "MP3": "mp3",
    "AAC": "aac",
    "OggVorbis": "vorbis",
    "OggOpus": "opus",
    "WavPack": "wavpack",
    "TrueAudio": "tta",
    "MonkeysAudio": "ape",
}

# Opus is always decoded at 48 kHz; the metadata does not carry a rate for it.
_OPUS_RATE = 48000


def is_lossless(codec: str) -> bool:
    """True for FLAC, ALAC, PCM and the other lossless codecs of this module."""
    return codec in _LOSSLESS_CODECS or codec.startswith("pcm_")


def _positive(value: object) -> int | None:
    """Return `value` as a positive int, or None (missing, zero, negative or not a number)."""
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _codec_from_mutagen(name: str, bits: int | None) -> str | None:
    if name.startswith("Easy"):
        name = name[len("Easy") :]
    if name in _MUTAGEN_CODECS:
        return _MUTAGEN_CODECS[name]
    if name == "WAVE" and bits is not None:
        if bits == 8:
            return "pcm_u8"
        if bits in (16, 24):
            return f"pcm_s{bits}le"
        # 32 bits is integer or float in a WAVE file; only the probe can tell.
        return None
    if name == "AIFF" and bits is not None:
        if bits == 8:
            return "pcm_s8"
        if bits in (16, 24, 32):
            return f"pcm_s{bits}be"
    return None


def from_metadata(metadata_json: str | None) -> SourceInfo | None:
    """Build the `SourceInfo` from MTEE's metadata JSON, or None when it cannot say.

    The JSON is `MetadataSnapshot.to_dict()` (see `library/hashing.read_metadata`). Its
    `technical` part gives the codec (`codec`, a Mutagen class name), `sample_rate`,
    `bits_per_sample` and `bitrate`. The snapshot has no channel count, so `channels` is None.
    """
    if not metadata_json:
        return None
    try:
        data: Any = json.loads(metadata_json)
    except ValueError:
        return None
    technical = data.get("technical") if isinstance(data, dict) else None
    if not isinstance(technical, dict):
        return None
    bits = _positive(technical.get("bits_per_sample"))
    codec = _codec_from_mutagen(str(technical.get("codec") or ""), bits)
    if codec is None:
        return None
    sample_rate = _positive(technical.get("sample_rate"))
    if codec == "opus" and sample_rate is None:
        sample_rate = _OPUS_RATE
    return SourceInfo(
        codec=codec,
        lossless=is_lossless(codec),
        sample_rate=sample_rate,
        bit_depth=bits,
        bitrate=_positive(technical.get("bitrate")),
        channels=None,
    )


def probe(path: Path) -> SourceInfo:
    """Ask ffprobe about the first audio stream of `path`.

    Raises RuntimeError when ffprobe fails, times out, or finds no audio stream.
    """
    command = [
        tools.ffprobe_path(),
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        _PROBE_ENTRIES,
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=_PROBE_TIMEOUT_S,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"ffprobe timed out on {path.name}.") from error
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe could not read {path.name}.")
    try:
        data: Any = json.loads(result.stdout)
    except ValueError as error:
        raise RuntimeError(f"ffprobe printed no JSON for {path.name}.") from error
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError(f"{path.name} has no audio stream.")
    stream = streams[0]
    codec = str(stream.get("codec_name") or "")
    if not codec:
        raise RuntimeError(f"ffprobe did not name the codec of {path.name}.")
    sample_rate = _positive(stream.get("sample_rate"))
    if sample_rate is None:
        # ffprobe still names a stream for a non-audio file that carries the extension.
        raise RuntimeError(f"{path.name} has no readable audio stream.")
    fmt = data.get("format") or {}
    return SourceInfo(
        codec=codec,
        lossless=is_lossless(codec),
        sample_rate=sample_rate,
        bit_depth=_positive(stream.get("bits_per_raw_sample"))
        or _positive(stream.get("bits_per_sample")),
        bitrate=_positive(stream.get("bit_rate")) or _positive(fmt.get("bit_rate")),
        channels=_positive(stream.get("channels")),
    )


def source_info(path: Path, metadata_json: str | None) -> SourceInfo:
    """The metadata's answer when it has one, else the probe's."""
    found = from_metadata(metadata_json)
    if found is not None:
        return found
    return probe(path)
