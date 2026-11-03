"""The hashes of the local tracks: the SHA-256 of the file and the audio hash (plan 126.2).

The audio hash is the one the server computes (``server/src/mtee_remote/library/hashing.py``):
the SHA-256 of the copied audio stream, tags and cover art left out, so a tag edit keeps it. The
command below is that command, argument for argument, run without a shell.

Hashing runs on a job thread, under the read lease of each track (``context.files.read_lease``),
so a tag write never races it. The results are cached per path, size and modification time in
``remote_hash_cache``, with the time at which they were computed (``hashed_at_ns``): a file that
did not change is never hashed twice, unless it is "racy" (see ``_trusted_cache``).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mtee.plugins.api import JobContext, PluginContext

from .store import CachedHashes, RemoteStore

log = logging.getLogger(__name__)

CHUNK_BYTES = 1024 * 1024
AUDIO_HASH_TIMEOUT_S = 600
# Coarse file system timestamps (FAT: 2 s) can hide an edit that keeps the size: see _trusted_cache.
RACY_MARGIN_NS = 2_000_000_000
_STREAMHASH = re.compile(r"SHA256=([0-9A-Fa-f]{64})")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Why a track has no hash: the reasons shown in the summary and in the log.
SKIP_MISSING = "missing"
SKIP_NOT_A_FILE = "not_a_file"
SKIP_UNREADABLE = "unreadable"
SKIP_BUSY = "busy"
SKIP_UNKNOWN = "unknown"


@dataclass(frozen=True)
class FileHashes:
    sha256: str
    audio_hash: str | None


@dataclass
class HashReport:
    """The hashes of the tracks that could be read, and why the others were skipped."""

    hashes: dict[str, FileHashes] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    cached: int = 0
    hashed: int = 0


def file_sha256(path: Path) -> str:
    """Return the SHA-256 (lowercase hex) of the whole file, read in 1 MiB chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def audio_hash(ffmpeg: Path, path: Path) -> str | None:
    """Return the audio hash of ``path``, or None when it cannot be computed.

    None covers a missing or non-audio file, a failed run and a timeout; the SHA-256 is then the
    only key the match can use for that file.
    """
    command = [
        str(ffmpeg),
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
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=AUDIO_HASH_TIMEOUT_S,
            check=False,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        log.warning("The audio hash of a file could not be computed.", exc_info=True)
        return None
    if result.returncode != 0:
        return None
    lines = result.stdout.decode("ascii", errors="replace").splitlines()
    if not lines:
        return None
    found = _STREAMHASH.search(lines[0])
    return found.group(1).lower() if found else None


def hash_tracks(context: PluginContext, track_ids: Sequence[str], job: JobContext) -> HashReport:
    """Hash each track of ``track_ids`` on a job thread; skip and count those that cannot be read.

    Reports progress per track and stops at the next track when the job is cancelled
    (``JobCancelledError``). A track without a local file, a missing file and a file that cannot
    be read are skipped with their reason; the report keeps them.
    """
    store = RemoteStore(context)
    ffmpeg = context.ffmpeg_path()
    report = HashReport()
    total = len(track_ids)
    for index, track_id in enumerate(track_ids):
        job.raise_if_cancelled()
        try:
            with context.files.read_lease(track_id) as path:
                hashes, was_cached = _hashes_of(store, ffmpeg, Path(path))
        except FileNotFoundError:
            report.skipped[track_id] = SKIP_MISSING
        except TimeoutError:
            report.skipped[track_id] = SKIP_BUSY
        except LookupError:
            report.skipped[track_id] = SKIP_UNKNOWN
        except ValueError:
            # A track without a local file: the lease refuses it with a ValueError.
            report.skipped[track_id] = SKIP_NOT_A_FILE
        except OSError:
            report.skipped[track_id] = SKIP_UNREADABLE
        else:
            report.hashes[track_id] = hashes
            if was_cached:
                report.cached += 1
            else:
                report.hashed += 1
        if total:
            job.report_progress((index + 1) / total)
    return report


def _hashes_of(store: RemoteStore, ffmpeg: Path, path: Path) -> tuple[FileHashes, bool]:
    """Return the hashes of ``path`` and whether they came from the cache.

    The time of the hashing is taken before the file is read, and stored with the hashes.
    """
    hashed_at_ns = time.time_ns()
    info = os.stat(path)
    key = os.path.normcase(os.path.abspath(path))
    cached = _trusted_cache(store, key, info.st_size, info.st_mtime_ns)
    if cached is not None:
        return FileHashes(cached.sha256, cached.audio_hash), True
    hashes = FileHashes(file_sha256(path), audio_hash(ffmpeg, path))
    _remember(store, key, info.st_size, info.st_mtime_ns, hashed_at_ns, hashes)
    return hashes, False


def _trusted_cache(
    store: RemoteStore, key: str, size_bytes: int, mtime_ns: int
) -> CachedHashes | None:
    """Return the cached hashes of a file, when they can be trusted; None means hash it again.

    The rule is the one of Git's "racy" entries. Two saves can keep the size and fall in the same
    clock tick (or, on a coarse file system, in the same two seconds): the cache key then does not
    change, and the second content would get the first content's hash. So an entry is trusted only
    when the file's modification time is older than the time at which the hash was computed, minus
    2 seconds (``RACY_MARGIN_NS``). A file touched in that window is hashed again, and the new
    hashes are stored with the new time, so a file older than the margin is served from the cache.
    An entry without that time (stored before migration 004, or by another writer) is not trusted.
    """
    row = (
        store.connection()
        .execute(
            "SELECT sha256, audio_hash, hashed_at_ns FROM remote_hash_cache"
            " WHERE path = ? AND size_bytes = ? AND mtime_ns = ?",
            (key, size_bytes, mtime_ns),
        )
        .fetchone()
    )
    if row is None or row["hashed_at_ns"] is None:
        return None
    if mtime_ns >= int(row["hashed_at_ns"]) - RACY_MARGIN_NS:
        return None
    return CachedHashes(str(row["sha256"]), row["audio_hash"])


def _remember(
    store: RemoteStore,
    key: str,
    size_bytes: int,
    mtime_ns: int,
    hashed_at_ns: int,
    hashes: FileHashes,
) -> None:
    """Store the hashes of a file with the time at which they were computed."""
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO remote_hash_cache"
            " (path, size_bytes, mtime_ns, sha256, audio_hash, hashed_at_ns)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (path) DO UPDATE SET size_bytes = excluded.size_bytes,"
            " mtime_ns = excluded.mtime_ns, sha256 = excluded.sha256,"
            " audio_hash = excluded.audio_hash, hashed_at_ns = excluded.hashed_at_ns",
            (key, size_bytes, mtime_ns, hashes.sha256, hashes.audio_hash, hashed_at_ns),
        )
