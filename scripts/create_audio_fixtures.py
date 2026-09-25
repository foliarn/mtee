"""Generate short, tagged synthetic audio files using the pinned FFmpeg."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path
from typing import Any

from mtee.services.ffmpeg_runtime import FfmpegRuntime

__all__ = ["create_fixtures", "main"]

_FIXTURES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("mp3", "mp3", ("-c:a", "libmp3lame", "-q:a", "4")),
    ("flac", "flac", ("-c:a", "flac")),
    ("wav", "wav", ("-c:a", "pcm_s16le")),
    ("aiff", "aiff", ("-c:a", "pcm_s16be")),
    ("vorbis", "ogg", ("-c:a", "libvorbis", "-q:a", "3")),
    ("opus", "opus", ("-c:a", "libopus", "-b:a", "96k")),
    ("aac-adts", "adts", ("-c:a", "aac", "-b:a", "128k", "-f", "adts")),
    ("m4a-aac", "m4a", ("-c:a", "aac", "-b:a", "128k")),
    ("m4a-alac", "m4a", ("-c:a", "alac")),
)
_METADATA = (
    "-metadata",
    "title=Synthetic tone",
    "-metadata",
    "artist=MTEE test signal",
    "-metadata",
    "album=Fixture set",
    "-metadata",
    "genre=Test",
    "-metadata",
    "track=2/12",
    "-metadata",
    "comment=Generated locally for metadata round-trip validation",
    "-metadata",
    "mtee_fixture_marker=preserve-me",
)


def create_fixtures(output: Path, runtime: FfmpegRuntime) -> dict[str, Any]:
    """Create nine three-second fixtures in a new or empty output directory."""
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to write into a non-empty fixture folder: {output}")
    output.mkdir(parents=True, exist_ok=True)
    cover_path = output / "cover.png"
    _write_cover_png(cover_path)
    entries = []
    for name, container, encoding in _FIXTURES:
        target = output / f"{name}.{container}"
        arguments = [
            "-hide_banner",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=3",
            "-ac",
            "2",
            "-map_metadata",
            "-1",
            *_METADATA,
            *encoding,
            str(target),
        ]
        result = runtime.run("ffmpeg", arguments, timeout_seconds=60)
        if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError(
                f"Could not generate {name}: "
                f"{result.stderr[-2048:] or f'ffmpeg exited {result.returncode}'}"
            )
        probe = runtime.run(
            "ffprobe",
            [
                "-v",
                "error",
                "-show_entries",
                "format=format_name,duration:stream=codec_type,codec_name,sample_rate,channels,bits_per_sample,bits_per_raw_sample",
                "-of",
                "json",
                str(target),
            ],
            timeout_seconds=30,
        )
        if probe.returncode != 0:
            raise RuntimeError(f"Could not inspect {name}: {probe.stderr[-2048:]}")
        details = json.loads(probe.stdout)
        audio_streams = [
            stream for stream in details.get("streams", []) if stream.get("codec_type") == "audio"
        ]
        if len(audio_streams) != 1:
            raise RuntimeError(f"Expected exactly one audio stream in {target.name}.")
        entries.append(
            {
                "fixture_id": name,
                "file": target.name,
                "container": details.get("format", {}).get("format_name"),
                "duration_seconds": details.get("format", {}).get("duration"),
                "codec": audio_streams[0].get("codec_name"),
                "sample_rate": audio_streams[0].get("sample_rate"),
                "channels": audio_streams[0].get("channels"),
                "bits_per_sample": audio_streams[0].get("bits_per_sample"),
                "bits_per_raw_sample": audio_streams[0].get("bits_per_raw_sample"),
                "size_bytes": target.stat().st_size,
                "sha256": _sha256(target),
                "provenance": "Generated 440 Hz sine test signal using pinned FFmpeg.",
                "redistribution": "Project-generated signal; no third-party audio or sample.",
            }
        )
    manifest = {
        "schema_version": 1,
        "generator": runtime.version(),
        "fixture_policy": "Local-only synthetic fixtures; non-empty output is refused.",
        "cover_art": {
            "file": cover_path.name,
            "width": 16,
            "height": 16,
            "sha256": _sha256(cover_path),
            "provenance": "Generated solid-color PNG used by metadata round-trip fixtures.",
        },
        "fixtures": entries,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_cover_png(path: Path) -> None:
    """Write a tiny deterministic PNG without embedding third-party artwork."""
    width = height = 16
    row = b"\x00" + bytes((64, 160, 220)) * width
    pixels = row * height

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="new or empty local output directory"
    )
    parser.add_argument(
        "--ffmpeg-dir",
        type=Path,
        help="pinned FFmpeg bin directory; defaults to the project runtime",
    )
    arguments = parser.parse_args()
    try:
        manifest = create_fixtures(arguments.output, FfmpegRuntime(arguments.ffmpeg_dir))
    except (FileExistsError, OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(f"Created {len(manifest['fixtures'])} fixtures with {manifest['generator']}.")
    print(arguments.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
