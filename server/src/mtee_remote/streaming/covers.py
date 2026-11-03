"""Album covers resized to 128, 512 or 1200 px and cached on disk (plan 127.2).

Source order: the embedded front cover of the audio file, then a picture file in the item's
folder named `cover`, `folder`, `front` or `album` (`.jpg`, `.jpeg` or `.png`, any case). Both
go through ffmpeg. Nothing is ever upscaled: the scale filter only shrinks.

The cache is `<cache_dir>/<key>-<px>.jpg`, where `key` is the item's SHA-256 (or
`<item_id>-<revision>` while the hash is unknown). A file is written under a unique `.part-`
name and renamed when complete, so a cached file is always whole.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import uuid
from pathlib import Path

from mtee_remote import tools

COVER_SIZES: dict[str, int] = {"s": 128, "m": 512, "l": 1200}
FFMPEG_TIMEOUT_S = 60
_FOLDER_NAMES = frozenset({"cover", "folder", "front", "album"})
_PICTURE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def cover_args(ffmpeg: str, source: Path, px: int, output: Path) -> list[str]:
    """The ffmpeg command that writes the first picture of `source`, at most `px` px, as JPEG."""
    scale = f"scale='min({px},iw)':'min({px},ih)':force_original_aspect_ratio=decrease"
    return [
        ffmpeg,
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
        "-vf",
        scale,
        "-q:v",
        "3",
        "-f",
        "image2",
        str(output),
    ]


def _run_ffmpeg(source: Path, px: int, output: Path) -> bool:
    """Run ffmpeg for one picture; True when `output` is a non-empty file. Blocks.

    A failed run leaves no `output` behind, so the next attempt can use the same name.
    """
    command = cover_args(tools.ffmpeg_path(), source, px, output)
    made = False
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=FFMPEG_TIMEOUT_S,
            check=False,
            creationflags=_CREATE_NO_WINDOW,
        )
        made = result.returncode == 0 and output.stat().st_size > 0
    except (OSError, subprocess.SubprocessError):
        made = False
    if not made:
        with contextlib.suppress(OSError):
            output.unlink(missing_ok=True)
    return made


def folder_picture(folder: Path) -> Path | None:
    """The picture file in `folder` named like a cover (case-insensitive), first by name."""
    try:
        entries = sorted(folder.iterdir(), key=lambda entry: entry.name)
    except OSError:
        return None
    for entry in entries:
        if (
            entry.is_file()
            and entry.stem.lower() in _FOLDER_NAMES
            and entry.suffix.lower() in _PICTURE_SUFFIXES
        ):
            return entry
    return None


def cover_file(cache_dir: Path, source: Path, key: str, px: int) -> Path | None:
    """Return the cached JPEG of `source` at `px`, making it first; None when there is no cover.

    Blocking: call it from a worker thread.
    """
    final = cache_dir / f"{key}-{px}.jpg"
    if final.is_file():
        return final
    cache_dir.mkdir(parents=True, exist_ok=True)
    part = final.with_name(f"{final.name}.part-{uuid.uuid4().hex}")
    try:
        made = _run_ffmpeg(source, px, part)
        if not made:
            picture = folder_picture(source.parent)
            made = picture is not None and _run_ffmpeg(picture, px, part)
        if not made:
            return None
        os.replace(part, final)
    finally:
        with contextlib.suppress(OSError):
            part.unlink(missing_ok=True)
    return final
