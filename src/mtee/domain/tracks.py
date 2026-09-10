"""Track identity and source revision.

``TrackId`` is an internal UUID: the path of a file may change without changing
the track it designates, and two physical copies own two distinct identifiers.
A content hash is never used as an identity.

``SourceRevision`` is an observation of the file on disk. It detects ordinary
modifications; it is not a cryptographic proof of content. A critical operation
completes the check with a streamed SHA-256 digest.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

__all__ = ["SourceRevision", "TrackId", "sha256_of_file"]

_SHA256_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True, order=True)
class TrackId:
    """Stable internal identifier of a track."""

    value: uuid.UUID

    @staticmethod
    def new() -> TrackId:
        """Return a freshly generated identifier."""
        return TrackId(uuid.uuid4())

    @staticmethod
    def parse(text: str) -> TrackId:
        """Return the identifier written as ``text``.

        Raises ``ValueError`` when the text is not a UUID.
        """
        return TrackId(uuid.UUID(str(text)))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class SourceRevision:
    """Observation of a source file used to detect ordinary modifications.

    ``file_id`` is the optional identifier provided by the file system, and
    ``generation`` is incremented by MTEE after each mutation it performs.
    """

    size_bytes: int
    mtime_ns: int
    file_id: str | None = None
    generation: int = 0

    def __post_init__(self) -> None:
        if self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")
        if self.mtime_ns < 0:
            raise ValueError("mtime_ns must not be negative")
        if self.generation < 0:
            raise ValueError("generation must not be negative")
        if self.file_id is not None and not self.file_id:
            raise ValueError("file_id must be None or a non-empty string")

    @staticmethod
    def observe(path: Path | str, *, generation: int = 0) -> SourceRevision:
        """Observe ``path`` and return its current revision."""
        status = os.stat(path)
        return SourceRevision(
            size_bytes=status.st_size,
            mtime_ns=status.st_mtime_ns,
            file_id=_file_id_of(status),
            generation=generation,
        )

    def matches(self, observed: SourceRevision) -> bool:
        """Return whether ``observed`` describes the same unmodified file.

        The generation is ignored: it records mutations performed by MTEE, not
        the state of the bytes on disk. A ``file_id`` is compared only when both
        revisions carry one, because the value is optional.
        """
        if self.size_bytes != observed.size_bytes or self.mtime_ns != observed.mtime_ns:
            return False
        if self.file_id is not None and observed.file_id is not None:
            return self.file_id == observed.file_id
        return True

    def looks_modified(self, observed: SourceRevision) -> bool:
        """Return whether ``observed`` suggests the file changed since ``self``."""
        return not self.matches(observed)

    def bumped(self) -> SourceRevision:
        """Return the same observation with the next generation number."""
        return replace(self, generation=self.generation + 1)


def _file_id_of(status: os.stat_result) -> str | None:
    """Return the file system identifier of ``status`` when it is available."""
    file_index = getattr(status, "st_ino", 0)
    volume = getattr(status, "st_dev", 0)
    if not file_index:
        return None
    return f"{volume}:{file_index}"


def sha256_of_file(path: Path | str, *, chunk_bytes: int = _SHA256_CHUNK_BYTES) -> str:
    """Return the streamed SHA-256 digest of ``path``, for critical checks only."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()
