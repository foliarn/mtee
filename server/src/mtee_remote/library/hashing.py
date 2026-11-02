"""Hashes and tags of one file, computed outside any database transaction."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
from pathlib import Path

from mtee_remote import tools

log = logging.getLogger(__name__)

_CHUNK = 1024 * 1024
_FFMPEG_TIMEOUT_S = 600
_STREAMHASH = re.compile(r"SHA256=([0-9A-Fa-f]{64})")


def file_sha256(path: Path) -> str:
    """Return the SHA-256 (lowercase hex) of the whole file, read in 1 MiB chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def audio_hash(path: Path) -> str | None:
    """Return the SHA-256 of the audio stream only (tags and cover art excluded), or None.

    Uses ffmpeg's `streamhash` on the copied stream (study 124.1). It stays the same when
    tags or cover art change. Any failure (no ffmpeg, unreadable or non-audio file, timeout)
    gives None; the file SHA-256 is then the only matching key.
    """
    try:
        command = [
            tools.ffmpeg_path(),
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a",
            "-c",
            "copy",
            "-f",
            "streamhash",
            "-hash",
            "sha256",
            "-",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_S,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, RuntimeError, subprocess.SubprocessError):
        log.warning("The audio hash could not be computed.", exc_info=True)
        return None
    if result.returncode != 0:
        return None
    lines = result.stdout.decode("ascii", errors="replace").splitlines()
    if not lines:
        return None
    found = _STREAMHASH.search(lines[0])
    return found.group(1).lower() if found else None


def read_metadata(path: Path) -> tuple[str | None, int | None]:
    """Return `(metadata_json, duration_us)` read with MTEE's metadata reader.

    The JSON is the snapshot's dictionary with sorted keys. A file Mutagen cannot read still
    gives a snapshot (with `"status": "unreadable"`). Any exception gives `(None, None)`.
    """
    try:
        from mtee.services.metadata_reader import MetadataReader

        snapshot = MetadataReader().read(path)
        text = json.dumps(snapshot.to_dict(), ensure_ascii=False, sort_keys=True)
        return text, snapshot.technical.duration_us
    except Exception:
        log.warning("The tags could not be read.", exc_info=True)
        return None, None
