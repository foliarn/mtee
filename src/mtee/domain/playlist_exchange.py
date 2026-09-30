"""Strict versioned portable playlist manifest; no audio or absolute paths."""

from __future__ import annotations

import base64
import json
import re
from pathlib import PurePosixPath
from typing import Any

from mtee.domain.playlists import playlist_name, portable_snapshot

MAX_MANIFEST_BYTES = 20 * 1024 * 1024
MAX_COVER_BYTES = 5 * 1024 * 1024
MAX_ENTRIES = 100_000
MAX_ARCHIVE_BYTES = 20 * 1024**3
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def safe_archive_path(value: str) -> str:
    parts = PurePosixPath(value).parts
    if (
        not parts
        or value.startswith(("/", "\\"))
        or "\\" in value
        or any(
            p in {".", ".."}
            or ":" in p
            or p.rstrip(" .") != p
            or _RESERVED.match(p)
            or any(ord(c) < 32 or c in '<>"|?*' for c in p)
            for p in parts
        )
    ):
        raise ValueError("The archive contains an unsafe Windows file name.")
    return "/".join(parts)


def decode_manifest(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_MANIFEST_BYTES:
        raise ValueError("This playlist manifest exceeds the 20 MB limit.")
    try:
        value = json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as error:
        raise ValueError("This file is not a valid MTEE playlist.") from error
    if not isinstance(value, dict) or value.get("format") != "mtee-playlist":
        raise ValueError("This file is not a MTEE playlist.")
    if value.get("version") != 1:
        raise ValueError("This playlist format version is unsupported. Update MTEE.")
    playlist_name(value.get("name", "") if isinstance(value.get("name"), str) else "")
    entries = value.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise ValueError("This playlist has an invalid entry list or exceeds 100,000 entries.")
    if (
        not isinstance(value.get("description", ""), str)
        or len(value.get("description", "")) > 10000
    ):
        raise ValueError("The playlist description is invalid.")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("snapshot"), dict):
            raise ValueError("A playlist entry is invalid.")
        snapshot = entry["snapshot"]
        for key, item in portable_snapshot(snapshot).items():
            if key in {"seconds", "durationUs"}:
                if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                    raise ValueError("A playlist duration is invalid.")
            elif key == "identityUncertain":
                if not isinstance(item, bool):
                    raise ValueError("A playlist identity flag is invalid.")
            elif key == "bpm":
                if not isinstance(item, (str, int, float)):
                    raise ValueError("A playlist tempo is invalid.")
            elif not isinstance(item, str) or len(item) > 10000:
                raise ValueError("A playlist tag is invalid.")
        entry["snapshot"] = portable_snapshot(snapshot)
        digest = entry.get("sha256", "")
        if not isinstance(digest, str) or (digest and not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("A playlist file fingerprint is invalid.")
        audio = entry.get("audio", "")
        if not isinstance(audio, str):
            raise ValueError("A playlist audio reference is invalid.")
        if audio:
            normalized = safe_archive_path(audio)
            if (
                normalized != audio
                or len(PurePosixPath(audio).parts) != 2
                or not audio.startswith("audio/")
                or not digest
            ):
                raise ValueError("Playlist audio must be a fingerprinted file in audio/.")
    cover = value.get("cover", "")
    if not isinstance(cover, str) or len(cover) > MAX_COVER_BYTES * 4 // 3 + 4:
        raise ValueError("This playlist cover exceeds the 5 MB limit.")
    if cover:
        try:
            base64.b64decode(cover, validate=True)
        except ValueError as error:
            raise ValueError("The playlist cover is invalid.") from error
    return value
