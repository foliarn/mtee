"""Test helpers shared by the server tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mtee_remote import tools

# format -> (encoder arguments, ffmpeg muxer)
_FORMATS: dict[str, tuple[list[str], str]] = {
    "flac": (["-c:a", "flac"], "flac"),
    "mp3": (["-c:a", "libmp3lame", "-b:a", "128k"], "mp3"),
    "wav": (["-c:a", "pcm_s16le"], "wav"),
    "m4a": (["-c:a", "aac", "-b:a", "128k"], "ipod"),
    "ogg": (["-c:a", "libvorbis"], "ogg"),
    "opus": (["-c:a", "libopus"], "ogg"),
    "aiff": (["-c:a", "pcm_s16be", "-write_id3v2", "1"], "aiff"),
}


def make_audio(path: Path, fmt: str, *, seconds: float = 1.0, title: str | None = None) -> Path:
    """Write a short sine-wave file in `fmt` at `path` with ffmpeg and return `path`."""
    if fmt not in _FORMATS:
        raise ValueError(f"Unsupported test format: {fmt}")
    codec_args, muxer = _FORMATS[fmt]
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        tools.ffmpeg_path(),
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
        *codec_args,
    ]
    if title is not None:
        command += ["-metadata", f"title={title}"]
    command += ["-f", muxer, str(path)]
    subprocess.run(command, check=True, capture_output=True)
    return path
