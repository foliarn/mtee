"""Move library audio files into another library folder.

One file is moved at a time: the destination name is checked first, the track lock is
taken without waiting, the file is renamed without ever replacing another file, and one
SQLite transaction then points the same track UUID at its new location. When the
database update fails, the rename is undone, so the library and the disk never disagree
silently. Playlists, analyses and tag history keep following the UUID.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository, normalize_path
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError

__all__ = ["FileMoveError", "FileMoveResult", "FileMoveService"]


class FileMoveError(Exception):
    """The destination cannot receive files; the message is meant for the user."""


@dataclass(frozen=True, slots=True)
class FileMoveResult:
    """Outcome for one track: ``moved``, ``unchanged``, ``conflict``, ``busy`` or ``failed``."""

    track_id: str
    name: str
    status: str
    message: str = ""
    path: str = ""


class FileMoveService:
    def __init__(
        self, database: Database, library: LibraryRepository, file_access: FileAccessCoordinator
    ) -> None:
        self._database = database
        self._library = library
        self._access = file_access

    def resolve_folder(self, root_id: str, relative: str) -> Path:
        """Return the existing directory a library folder points to."""
        root = next((item for item in self._library.roots() if item["id"] == root_id), None)
        if root is None:
            raise FileMoveError("This library folder no longer exists.")
        root_path = Path(str(root["path"]))
        folder = root_path / relative if relative else root_path
        try:
            resolved = folder.resolve(strict=True)
            resolved.relative_to(root_path.resolve(strict=True))
        except (OSError, ValueError) as error:
            raise FileMoveError("The destination folder is not available.") from error
        if not resolved.is_dir():
            raise FileMoveError("The destination is not a folder.")
        return resolved

    def move(self, track_id: str, folder: Path) -> FileMoveResult:
        """Move one track's file into ``folder`` without replacing anything."""
        record = self._library.source_record(track_id)
        if record is None or record.status != "readable":
            return FileMoveResult(
                track_id, track_id, "conflict", "The file is no longer available."
            )
        current = record.path
        name = current.name
        if normalize_path(current.parent) == normalize_path(folder):
            return FileMoveResult(track_id, name, "unchanged", "Already in this folder.")
        target = folder / name
        if target.exists() or self._library.path_owner(target) is not None:
            return FileMoveResult(
                track_id, name, "conflict", "A file with this name already exists in the folder."
            )
        try:
            if os.stat(current).st_dev != os.stat(folder).st_dev:
                return FileMoveResult(
                    track_id, name, "failed", "Moving files between drives is not supported."
                )
        except OSError as error:
            return FileMoveResult(track_id, name, "failed", f"The file is not available: {error}")
        lease = self._access.acquire(TrackId.parse(track_id), "move audio file", timeout_seconds=0)
        try:
            with lease:
                try:
                    observed = SourceRevision.observe(current)
                except OSError as error:
                    return FileMoveResult(
                        track_id, name, "failed", f"The file is not available: {error}"
                    )
                if not record.revision.matches(observed):
                    return FileMoveResult(
                        track_id, name, "conflict", "The file changed since its last scan."
                    )
                try:
                    os.rename(current, target)
                except FileExistsError:
                    return FileMoveResult(
                        track_id,
                        name,
                        "conflict",
                        "A file with this name already exists in the folder.",
                    )
                except PermissionError:
                    return FileMoveResult(
                        track_id, name, "busy", "The file is in use by another program."
                    )
                except OSError as error:
                    return FileMoveResult(
                        track_id, name, "failed", f"The file could not be moved: {error}"
                    )
                try:
                    self._record(record, track_id, target)
                except Exception as error:
                    return self._rollback(track_id, name, current, target, error)
        except FileAccessTimeoutError:
            return FileMoveResult(
                track_id, name, "busy", "The file is playing or in use. Stop playback and retry."
            )
        return FileMoveResult(track_id, name, "moved", path=str(target))

    def _record(self, record, track_id: str, target: Path) -> None:
        with self._database.transaction() as connection:
            LibraryRepository.move_location_in_transaction(
                connection,
                track_id=track_id,
                expected_revision=record.revision,
                destination=target,
                new_revision=SourceRevision.observe(
                    target, generation=record.revision.generation + 1
                ),
                metadata=record.snapshot,
            )

    @staticmethod
    def _rollback(
        track_id: str, name: str, current: Path, target: Path, error: Exception
    ) -> FileMoveResult:
        try:
            os.rename(target, current)
        except OSError:
            return FileMoveResult(
                track_id,
                name,
                "failed",
                f"The file was moved but the library could not be updated ({error}). "
                "Rescan the folders to reconcile it.",
            )
        return FileMoveResult(
            track_id, name, "failed", f"The library could not record the move: {error}"
        )
