"""Replace the content of a library track's file with a file from outside the library.

The track keeps its path and its identifier. The old file goes to the Windows Recycle Bin
through the core's trash path (the journal and the library update of a confirmed delete); the
new file takes its place and the library record is refreshed from it. Every step runs under
the write lease of the track, so a player, an analysis or a tag write waits for the end.

When the source is on another volume, it is copied to a hidden ``.<name>.part`` file of the
track's folder before anything is recycled, so a failed copy changes nothing. The source is
removed only after the new file is in place and recorded; it goes to the Recycle Bin, as
every removal of a file in MTEE does.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Protocol

from mtee.domain.source_tracks import NonFileTrackError
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository, normalize_path
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.metadata_reader import MetadataReader
from mtee.services.trash_service import TrashService, TrashServiceError

__all__ = ["ContentReplaceError", "ContentReplacement", "HeldRecycler"]

_LOGGER = logging.getLogger(__name__)
_COPY_CHUNK_BYTES = 1024 * 1024


class ContentReplaceError(Exception):
    """The file of a track could not be replaced; the message says where each file is."""

    readable = True


class HeldRecycler(Protocol):
    """The core's trash path, for a file whose write lease the caller holds."""

    def recycle_held(self, track_id: str) -> tuple[bool, str]: ...


class ContentReplacement:
    """Replace the file of a track in place, keeping its identifier (remote plan 126.4)."""

    def __init__(
        self,
        database: Database,
        library: LibraryRepository,
        file_access: FileAccessCoordinator,
        recycler: HeldRecycler,
        *,
        trash: TrashService | None = None,
        reader: MetadataReader | None = None,
    ) -> None:
        self._database = database
        self._library = library
        self._access = file_access
        self._recycler = recycler
        self._trash = trash or TrashService()
        self._reader = reader or MetadataReader()

    def replace(self, track_id: str, source: Path) -> Path:
        """Put ``source`` in place of the file of ``track_id`` and return the track's path.

        Raises ``NonFileTrackError`` for a track without a file, ``LookupError`` for an unknown
        track, ``FileNotFoundError`` when the track's file or ``source`` is missing, ``ValueError``
        when ``source`` is not a regular file or lies inside a library folder, and
        ``ContentReplaceError`` (readable) when the replacement cannot be completed; its message
        says where the old and the new file are. Waits up to the lease timeout for the readers of
        the track; ``TimeoutError`` past it. Call it from a job thread: the plugin context
        refuses the graphical thread before it gets here.
        """
        source = Path(source)
        record = self._library.source_record(track_id)
        if record is None:
            refusal = self._library.non_file_refusal(track_id, "replaced")
            if refusal:
                raise NonFileTrackError(refusal)
            raise LookupError(f"Track {track_id} is not in the library.")
        if not record.path.is_file():
            raise FileNotFoundError(f"The file of track {track_id} is missing.")
        if not source.exists():
            raise FileNotFoundError(f"The file to put in place does not exist: {source}")
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"The file to put in place is not a regular file: {source}")
        if self._inside_library(source):
            raise ValueError(
                f"The file to put in place is already in the library: {source}. "
                "Copy it out of the library folders first."
            )
        with self._write_lease(track_id):
            return self._replace_locked(track_id, source)

    @contextmanager
    def _write_lease(self, track_id: str) -> Iterator[None]:
        with self._access.acquire(TrackId.parse(track_id), "replace audio file"):
            yield

    def _replace_locked(self, track_id: str, source: Path) -> Path:
        record = self._library.source_record(track_id)
        if record is None:
            raise LookupError(f"Track {track_id} is no longer in the library.")
        target = record.path
        if not target.is_file():
            raise FileNotFoundError(f"The file of track {track_id} is missing.")
        name = target.name

        # Everything that can fail before the old file moves is done first: a copy to another
        # volume is complete and verified before the Recycle Bin is asked for anything.
        staged: Path | None = None
        if not _same_volume(source, target.parent):
            staged = _stage_copy(source, target)

        try:
            recycled, message = self._recycler.recycle_held(track_id)
        except BaseException:
            _discard_copy(staged)
            raise
        if not recycled:
            _discard_copy(staged)
            raise ContentReplaceError(
                f"The file of {name} was not replaced: {message} Its file is untouched, "
                f"and {source} was not moved."
            )

        # From here the old file is in the Recycle Bin. MTEE cannot take a file back out of it,
        # so every failure below says where the old file is.
        origin = staged if staged is not None else source
        try:
            _place(origin, target)
        except OSError as error:
            _discard_copy(staged)
            raise ContentReplaceError(
                f"The old file of {name} is in the Windows Recycle Bin, but the new file could "
                f"not be put in its place ({error}). Restore the old file from the Recycle Bin "
                f"by hand if you need it. The new file is untouched at {source}."
            ) from error

        try:
            snapshot = self._reader.read(target)
            new_revision = SourceRevision.observe(target, generation=record.revision.generation + 1)
            with self._database.transaction() as connection:
                LibraryRepository.move_location_in_transaction(
                    connection,
                    track_id=track_id,
                    expected_revision=record.revision,
                    destination=target,
                    new_revision=new_revision,
                    metadata=snapshot,
                )
        except Exception as error:
            where = self._take_back(staged, source, target)
            raise ContentReplaceError(
                f"The old file of {name} is in the Windows Recycle Bin, and the library could not "
                f"record the new file ({error}). {where}"
            ) from error

        if staged is not None:
            try:
                self._trash.recycle(source)
            except (OSError, TrashServiceError) as error:
                raise ContentReplaceError(
                    f"{name} now has the new file and the library is updated, but {source} could "
                    f"not be sent to the Recycle Bin ({error}). Remove it by hand."
                ) from error
        return target

    def _take_back(self, staged: Path | None, source: Path, target: Path) -> str:
        """Undo the placement after the library refused it; return the sentence for the user."""
        if staged is not None:
            # The placed file is our own copy; the source is still in place, untouched.
            _discard_copy(target)
            return f"The copy was removed again; {source} is untouched."
        try:
            _place(target, source)
        except OSError as error:
            return f"The new file could not be moved back to {source} ({error}); it is at {target}."
        return f"The new file was moved back to {source}."

    def _inside_library(self, path: Path) -> bool:
        wanted = Path(normalize_path(path))
        return any(
            wanted.is_relative_to(Path(normalize_path(str(root["path"]))))
            for root in self._library.roots()
        )


def _same_volume(source: Path, folder: Path) -> bool:
    return os.stat(source).st_dev == os.stat(folder).st_dev


def _place(origin: Path, destination: Path) -> None:
    """Rename a file on its own volume. The destination is free: its old file was recycled."""
    os.rename(origin, destination)


def _stage_copy(source: Path, target: Path) -> Path:
    """Copy ``source`` to the hidden ``.<name>.part`` of ``target``'s folder; return that copy.

    The copy is written with an exclusive create, so an existing file is never overwritten.
    """
    staged = target.with_name(f".{target.name}.part")
    try:
        with source.open("rb") as input_file, staged.open("xb") as output_file:
            shutil.copyfileobj(input_file, output_file, length=_COPY_CHUNK_BYTES)
            output_file.flush()
            os.fsync(output_file.fileno())
        copied = staged.stat().st_size
        expected = source.stat().st_size
        if copied != expected:
            raise OSError(f"the copy of {source.name} is {copied} bytes, not {expected}")
    except FileExistsError as error:
        raise ContentReplaceError(
            f"A partial copy named {staged.name} is already in the folder. "
            "Remove it, then try again."
        ) from error
    except BaseException:
        _discard_copy(staged)
        raise
    return staged


def _discard_copy(path: Path | None) -> None:
    """Remove a copy that this operation wrote itself; the file it copies is never touched."""
    if path is None:
        return
    with suppress(OSError):
        path.unlink()
