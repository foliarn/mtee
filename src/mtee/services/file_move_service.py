"""Move library audio files into another library folder.

One file is moved at a time: the destination name is checked first, the track lock is
taken without waiting, the file is renamed without ever replacing another file, and one
SQLite transaction then points the same track UUID at its new location. When the
database update fails, the rename is undone, so the library and the disk never disagree
silently. Playlists, analyses and tag history keep following the UUID.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from collections.abc import Callable
from contextlib import ExitStack, suppress
from dataclasses import dataclass
from pathlib import Path

from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository, normalize_path
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError
from mtee.services.file_import import place_without_overwrite

__all__ = [
    "FileMoveError",
    "FileMoveResult",
    "FileMoveService",
    "FolderActionResult",
    "invalid_base_name",
]

_REFUSED_CHARACTERS = frozenset('<>:"/\\|?*')
_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


def invalid_base_name(value: str) -> str:
    """Return why ``value`` cannot be the base name of a file, or an empty string when it can."""
    name = value.strip()
    if not name:
        return "The name cannot be empty."
    if any(character in _REFUSED_CHARACTERS or ord(character) < 32 for character in name):
        return 'The name cannot contain any of these characters: \\ / : * ? " < > |'
    if name.endswith("."):
        return "The name cannot end with a dot."
    if name.split(".", 1)[0].strip().upper() in _RESERVED_NAMES:
        return "This name is reserved by Windows."
    return ""


class FileMoveError(Exception):
    """The destination cannot receive files; the message is meant for the user."""


@dataclass(frozen=True, slots=True)
class FileMoveResult:
    """Outcome for one track: ``moved``, ``copied``, ``unchanged``, ``conflict``, ``busy`` or
    ``failed``."""

    track_id: str
    name: str
    status: str
    message: str = ""
    path: str = ""


@dataclass(frozen=True, slots=True)
class FolderActionResult:
    """Outcome of a folder action: ``created``, ``renamed``, ``unchanged``, ``conflict``, ``busy``
    or ``failed``. ``relative`` is the folder after the action, ``previous`` the one before it."""

    status: str
    message: str = ""
    name: str = ""
    relative: str = ""
    previous: str = ""


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

    def import_file(self, source: Path, folder: Path) -> Path:
        """Move a file that is not in the library into a library folder; return its new path.

        The file never replaces another one (``place_without_overwrite``). ``folder`` must lie
        inside a library folder and is created when missing. The scanner records the file at
        the next scan. Raises ``FileMoveError`` for a destination outside the library or a
        source the library already owns, and ``OSError`` when the file cannot be moved.
        """
        source = Path(source)
        folder = Path(folder)
        if not source.is_file():
            raise FileNotFoundError(f"The file to import does not exist: {source}")
        if self._library.path_owner(source) is not None:
            raise FileMoveError("This file is already in the library.")
        wanted = Path(normalize_path(folder))
        if not any(
            wanted.is_relative_to(Path(normalize_path(str(root["path"]))))
            for root in self._library.roots()
        ):
            raise FileMoveError("The destination folder is not in the library.")
        folder.mkdir(parents=True, exist_ok=True)
        if normalize_path(source.parent) == normalize_path(folder):
            return source
        return place_without_overwrite(
            source, folder, lambda target: self._library.path_owner(target) is not None
        )

    def move(
        self,
        track_id: str,
        folder: Path,
        *,
        on_disk_moved: Callable[[], None] | None = None,
    ) -> FileMoveResult:
        """Move one track's file into ``folder`` without replacing anything."""
        record = self._library.source_record(track_id)
        if record is None or record.status != "readable":
            refusal = self._library.non_file_refusal(track_id, "moved") if record is None else ""
            return FileMoveResult(
                track_id, track_id, "conflict", refusal or "The file is no longer available."
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
        return self._relocate(
            record, track_id, name, target, "move audio file", on_disk_moved=on_disk_moved
        )

    def copy(self, track_id: str, folder: Path) -> FileMoveResult:
        """Copy one track's file into ``folder``; a name already there is a conflict.

        The bytes go to a hidden ``.part`` file opened with mode ``xb`` and are put in place by
        ``os.rename``, which refuses an existing target on Windows, so nothing is ever replaced
        and a scan never sees a half-written file. The copy is a new file for the library: the
        scanner records it, the original track keeps its own record. Playing files can be copied.
        """
        record = self._library.source_record(track_id)
        if record is None or record.status != "readable":
            refusal = self._library.non_file_refusal(track_id, "copied") if record is None else ""
            return FileMoveResult(
                track_id, track_id, "conflict", refusal or "The file is no longer available."
            )
        current = record.path
        name = current.name
        target = folder / name
        if target.exists() or self._library.path_owner(target) is not None:
            return FileMoveResult(
                track_id, name, "conflict", "A file with this name already exists in the folder."
            )
        part = folder / f".{name}.part"
        created = False
        try:
            if not record.revision.matches(SourceRevision.observe(current)):
                return FileMoveResult(
                    track_id, name, "conflict", "The file changed since its last scan."
                )
            with open(current, "rb") as reader, open(part, "xb") as writer:
                created = True
                shutil.copyfileobj(reader, writer, 1024 * 1024)
            shutil.copystat(current, part)
            os.rename(part, target)
        except FileExistsError:
            return FileMoveResult(
                track_id, name, "conflict", "A file with this name already exists in the folder."
            )
        except PermissionError:
            return FileMoveResult(track_id, name, "busy", "The file is in use by another program.")
        except OSError as error:
            return FileMoveResult(
                track_id, name, "failed", f"The file could not be copied: {error}"
            )
        finally:
            if created:  # only the part file this call made, if it was not put in place
                with contextlib.suppress(OSError):
                    part.unlink(missing_ok=True)
        return FileMoveResult(track_id, name, "copied", path=str(target))

    def rename(self, track_id: str, new_base_name: str) -> FileMoveResult:
        """Rename one track's file inside its folder; the extension stays and nothing is replaced.

        A name that is empty, holds a path separator or another character Windows refuses, ends
        with a dot or a space, or is a reserved device name is refused. So is a name another
        file of the folder already has: the user chose the name, so it is not changed silently.
        The record keeps the same track UUID, so playlists, analyses and tag history follow.
        """
        record = self._library.source_record(track_id)
        if record is None or record.status != "readable":
            refusal = self._library.non_file_refusal(track_id, "renamed") if record is None else ""
            return FileMoveResult(
                track_id, track_id, "conflict", refusal or "The file is no longer available."
            )
        current = record.path
        name = current.name
        problem = invalid_base_name(new_base_name)
        if problem:
            return FileMoveResult(track_id, name, "failed", problem)
        target = current.with_name(new_base_name.strip() + current.suffix)
        if target.name == name:
            return FileMoveResult(track_id, name, "unchanged", "The name did not change.")
        only_case = normalize_path(target) == normalize_path(current)
        if not only_case and (target.exists() or self._library.path_owner(target) is not None):
            return FileMoveResult(
                track_id, name, "conflict", "A file with this name already exists in this folder."
            )
        return self._relocate(record, track_id, name, target, "rename audio file")

    def _relocate(
        self,
        record,
        track_id: str,
        name: str,
        target: Path,
        purpose: str,
        *,
        on_disk_moved: Callable[[], None] | None = None,
    ) -> FileMoveResult:
        """Rename the file on disk to ``target`` and point the track at it, or undo it all."""
        current = record.path
        verb = "moved" if purpose.startswith("move") else "renamed"
        lease = self._access.acquire(TrackId.parse(track_id), purpose, timeout_seconds=0)
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
                        track_id, name, "failed", f"The file could not be {verb}: {error}"
                    )
                if on_disk_moved is not None:
                    try:
                        on_disk_moved()
                    except Exception as error:
                        return self._rollback(track_id, name, current, target, error)
                try:
                    self._record(record, track_id, target)
                except Exception as error:
                    return self._rollback(track_id, name, current, target, error)
        except FileAccessTimeoutError:
            return FileMoveResult(
                track_id, name, "busy", "The file is playing or in use. Stop playback and retry."
            )
        return FileMoveResult(track_id, name, "moved", path=str(target))

    def create_folder(self, root_id: str, parent_relative: str, name: str) -> FolderActionResult:
        """Create a folder inside a library folder. An existing name is refused, never reused."""
        clean = name.strip()
        problem = invalid_base_name(name)
        if problem:
            return FolderActionResult("failed", problem, name=clean)
        try:
            parent = self.resolve_folder(root_id, parent_relative)
        except FileMoveError as error:
            return FolderActionResult("failed", str(error), name=clean)
        target = parent / clean
        if os.path.lexists(target):
            return FolderActionResult(
                "conflict", "A file or folder with this name already exists here.", name=clean
            )
        relative = f"{parent_relative}/{clean}" if parent_relative else clean
        try:
            os.mkdir(target)
        except FileExistsError:
            return FolderActionResult(
                "conflict", "A file or folder with this name already exists here.", name=clean
            )
        except OSError as error:
            return FolderActionResult(
                "failed", f"The folder could not be created: {error}", name=clean
            )
        try:
            self._library.add_folder_record(root_id, relative)
        except Exception as error:
            with suppress(OSError):
                os.rmdir(target)
            return FolderActionResult(
                "failed", f"The library could not record the folder: {error}", name=clean
            )
        return FolderActionResult(
            "created", f"Created the folder “{clean}”.", name=clean, relative=relative
        )

    def next_folder_name(
        self, root_id: str, parent_relative: str, base: str = "Unnamed folder"
    ) -> str:
        """The first free "<base> 01", "<base> 02"... inside a folder; never an existing name."""
        parent = self.resolve_folder(root_id, parent_relative)
        for number in range(1, 1000):
            candidate = f"{base} {number:02d}"
            if not os.path.lexists(parent / candidate):
                return candidate
        raise FileMoveError("No free folder name is left here.")

    def rename_folder(self, root_id: str, relative: str, new_name: str) -> FolderActionResult:
        """Rename a folder of a source on disk and point the records under it at the new place.

        The tracks under the folder keep their UUIDs, analysis, edits and playlist entries. The
        folder is renamed only when every track under it is free (write leases taken without
        waiting), and the rename is undone when the library cannot record it. A source itself is
        never renamed here: it is removed from the library and added again.
        """
        clean = new_name.strip()
        if not relative:
            return FolderActionResult("failed", "A source cannot be renamed here.", name=clean)
        problem = invalid_base_name(new_name)
        if problem:
            return FolderActionResult("failed", problem, name=clean)
        try:
            old = self.resolve_folder(root_id, relative)
        except FileMoveError as error:
            return FolderActionResult("failed", str(error), name=clean, previous=relative)
        if clean == old.name:
            return FolderActionResult(
                "unchanged", "The name did not change.", name=clean, previous=relative
            )
        target = old.with_name(clean)
        only_case = normalize_path(target) == normalize_path(old)
        if not only_case and os.path.lexists(target):
            return FolderActionResult(
                "conflict",
                "A file or folder with this name already exists here.",
                name=clean,
                previous=relative,
            )
        parent_relative = relative.rpartition("/")[0]
        new_relative = f"{parent_relative}/{clean}" if parent_relative else clean
        track_ids = self._library.track_ids_in_tree(root_id, relative)
        try:
            with ExitStack() as leases:
                for track_id in track_ids:
                    leases.enter_context(
                        self._access.acquire(
                            TrackId.parse(track_id), "rename folder", timeout_seconds=0
                        )
                    )
                try:
                    os.rename(old, target)
                except PermissionError:
                    return FolderActionResult(
                        "busy",
                        "A file in the folder is in use by another program.",
                        name=clean,
                        previous=relative,
                    )
                except OSError as error:
                    return FolderActionResult(
                        "failed",
                        f"The folder could not be renamed: {error}",
                        name=clean,
                        previous=relative,
                    )
                try:
                    self._library.rename_folder_records(root_id, relative, new_relative, target)
                except Exception as error:
                    message = f"The library could not record the rename: {error}"
                    try:
                        os.rename(target, old)
                    except OSError:
                        message += " The folder stays renamed on disk; rescan the source."
                    return FolderActionResult("failed", message, name=clean, previous=relative)
        except FileAccessTimeoutError:
            return FolderActionResult(
                "busy",
                "A file of the folder is playing or in use. Stop playback and retry.",
                name=clean,
                previous=relative,
            )
        return FolderActionResult(
            "renamed",
            f"Renamed the folder to “{clean}”.",
            name=clean,
            relative=new_relative,
            previous=relative,
        )

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
