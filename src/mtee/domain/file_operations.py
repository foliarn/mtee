"""Immutable previews and results for reversible file mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mtee.domain.tracks import SourceRevision

__all__ = [
    "FileOperationPreview",
    "FileOperationResult",
    "FileOperationTarget",
]


@dataclass(frozen=True, slots=True)
class FileOperationTarget:
    """One UUID and the paths/revision captured for the requested operation."""

    track_id: str
    source: Path
    destination: Path
    revision: SourceRevision
    status: str = "ready"
    message: str = ""


@dataclass(frozen=True, slots=True)
class FileOperationPreview:
    """A user-visible plan that is revalidated before it can mutate a file."""

    preview_id: str
    kind: str
    destination_or_name: str
    targets: tuple[FileOperationTarget, ...]
    created_at_utc: str

    @property
    def executable(self) -> bool:
        return any(target.status == "ready" for target in self.targets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.preview_id,
            "kind": self.kind,
            "createdAtUtc": self.created_at_utc,
            "executable": self.executable,
            "targets": [
                {
                    "trackId": target.track_id,
                    "source": str(target.source),
                    "destination": str(target.destination),
                    "status": target.status,
                    "message": target.message,
                }
                for target in self.targets
            ],
        }


@dataclass(frozen=True, slots=True)
class FileOperationResult:
    """Result of one file, independent of other entries in the selection."""

    track_id: str
    operation_id: str
    status: str
    message: str = ""
    source: Path | None = None
    destination: Path | None = None
    revision: SourceRevision | None = None


def now_utc() -> str:
    """Return an ISO timestamp for durable operation records."""
    return datetime.now(UTC).isoformat(timespec="microseconds")
