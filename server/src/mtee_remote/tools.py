"""Locations of external tools."""

from __future__ import annotations

import os
import shutil


def ffmpeg_path() -> str:
    """Return the ffmpeg executable: `MTEE_REMOTE_FFMPEG`, else the one on PATH."""
    explicit = os.environ.get("MTEE_REMOTE_FFMPEG", "").strip()
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("ffmpeg was not found: set MTEE_REMOTE_FFMPEG or add ffmpeg to PATH.")
