"""Locations of external tools."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def ffmpeg_path() -> str:
    """Return the ffmpeg executable: `MTEE_REMOTE_FFMPEG`, else the one on PATH."""
    explicit = os.environ.get("MTEE_REMOTE_FFMPEG", "").strip()
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("ffmpeg was not found: set MTEE_REMOTE_FFMPEG or add ffmpeg to PATH.")


def ffprobe_path() -> str:
    """Return the ffprobe executable.

    Order: `MTEE_REMOTE_FFPROBE`; the ffprobe next to the ffmpeg found by `ffmpeg_path()`;
    ffprobe on PATH.
    """
    explicit = os.environ.get("MTEE_REMOTE_FFPROBE", "").strip()
    if explicit:
        return explicit
    try:
        ffmpeg = Path(ffmpeg_path())
    except RuntimeError:
        ffmpeg = None
    if ffmpeg is not None:
        sibling = ffmpeg.with_name("ffprobe" + ffmpeg.suffix)
        if sibling.is_file():
            return str(sibling)
    found = shutil.which("ffprobe")
    if found:
        return found
    raise RuntimeError("ffprobe was not found: set MTEE_REMOTE_FFPROBE or add ffprobe to PATH.")
