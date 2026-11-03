"""Keep a track's identity when its file moves between this computer and a plugin's source.

A plugin that frees the disk space of a track, or downloads it again, needs the same ``track_id``
on both sides (remote plan 126.5). Two operations:

* ``adopt``: a library track whose file has left the library (it was recycled) becomes a source
  track of the plugin. Its ``track_id`` stays, so the playlists, the play log and the analysis
  still refer to it. The file locations of the track are forgotten; the ``tracks`` row stays.
* ``attach``: a source track of the plugin receives a local file (a download). The file goes into
  a folder of the library under the same ``track_id``, its metadata is read again, and the
  plugin's source row is removed.

Nothing is replaced: a taken name gets the next free ``name (2).ext`` (``file_import``). The
write lease of the track is held while ``attach`` switches the track to its file.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sqlite3
from pathlib import Path

from mtee.domain.source_tracks import SourceTrack
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_import import place_without_overwrite
from mtee.services.metadata_reader import MetadataReader

__all__ = ["TrackAttachError", "TrackIdentity"]

_COPY_CHUNK_BYTES = 1024 * 1024


class TrackAttachError(Exception):
    """The file moved by ``attach`` could not be put back; the message says where it is."""

    readable = True


class TrackIdentity:
    """Adopt a library track as a source track, or attach a file to a source track."""

    def __init__(
        self,
        database: Database,
        library: LibraryRepository,
        file_access: FileAccessCoordinator,
        *,
        reader: MetadataReader | None = None,
    ) -> None:
        self._database = database
        self._library = library
        self._access = file_access
        self._sources = SourceTrackRepository(database)
        self._reader = reader or MetadataReader()

    def adopt(self, plugin_id: str, track_id: str, entry: SourceTrack) -> str:
        """Make the library track ``track_id`` a source track of ``plugin_id``; return its id.

        A call for the track and key that it already has changes nothing. Raises ``ValueError``
        when the track does not exist, still has a file on this computer (or is still listed by a
        library folder), belongs to another plugin, or when ``entry.source_key`` is taken by
        another track of the plugin. Any thread.
        """
        if not plugin_id:
            raise ValueError("A plugin identifier is required.")
        with self._database.transaction() as connection:
            known = connection.execute(
                "SELECT 1 FROM tracks WHERE track_id=?", (track_id,)
            ).fetchone()
            if known is None:
                raise ValueError(f"The track {track_id} does not exist.")
            origin = self._sources.origin(track_id)
            if origin is not None:
                if origin == (plugin_id, entry.source_key):
                    return track_id
                if origin[0] != plugin_id:
                    raise ValueError(
                        f"The track {track_id} is a track of another plugin ({origin[0]})."
                    )
                raise ValueError(
                    f"The track {track_id} is already a track of this plugin under another key."
                )
            if _has_local_file(connection, track_id):
                raise ValueError(
                    f"The track {track_id} still has a file on this computer, or a library "
                    "folder still lists it. Rescan the folders first; it cannot be adopted."
                )
            taken = connection.execute(
                "SELECT track_id FROM plugin_source_tracks WHERE plugin_id=? AND source_key=?",
                (plugin_id, entry.source_key),
            ).fetchone()
            if taken is not None:
                raise ValueError(
                    f"The key {entry.source_key} of this plugin already belongs to another track."
                )
            LibraryRepository.release_location_in_transaction(connection, track_id=track_id)
            SourceTrackRepository.insert_in_transaction(connection, plugin_id, track_id, entry)
        return track_id

    def attach(self, plugin_id: str, track_id: str, source: Path, folder: Path) -> Path:
        """Move ``source`` into the library ``folder`` as the file of the source track ``track_id``.

        Returns the new path of the file. Raises ``ValueError`` when the track is not a source
        track of ``plugin_id``, when ``source`` is not a regular file or lies in the library, or
        when ``folder`` is outside the library; ``FileNotFoundError`` when ``source`` is missing.
        On any failure the file is back at ``source`` and the track stays a source track.
        Job thread only (the caller checks it). Holds the write lease of the track.
        """
        source = Path(source)
        folder = Path(folder)
        self._require_source_of(plugin_id, track_id)
        if not source.exists():
            raise FileNotFoundError(f"The file to attach does not exist: {source}")
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"The file to attach is not a regular file: {source}")
        if self._library.inside_a_root(source):
            raise ValueError(
                f"The file to attach is already in the library: {source}. "
                "Copy it out of the library folders first."
            )
        if not self._library.inside_a_root(folder):
            raise ValueError("The destination folder is not in the library.")

        with self._access.acquire(TrackId.parse(track_id), "attach audio file"):
            self._require_source_of(plugin_id, track_id)
            folder.mkdir(parents=True, exist_ok=True)
            target = place_without_overwrite(
                source, folder, lambda path: self._library.path_owner(path) is not None
            )
            try:
                metadata = self._reader.read(target)
                revision = SourceRevision.observe(target)
                with self._database.transaction() as connection:
                    SourceTrackRepository.release_in_transaction(connection, track_id)
                    LibraryRepository.attach_location_in_transaction(
                        connection,
                        track_id=track_id,
                        destination=target,
                        revision=revision,
                        metadata=metadata,
                    )
            except BaseException:
                _put_back(target, source)
                raise
        return target

    def _require_source_of(self, plugin_id: str, track_id: str) -> None:
        origin = self._sources.origin(track_id)
        if origin is None:
            raise ValueError(
                f"The track {track_id} is not a track of a plugin source, so it cannot take a file."
            )
        if origin[0] != plugin_id:
            raise ValueError(f"The track {track_id} is provided by another plugin ({origin[0]}).")


def _has_local_file(connection: sqlite3.Connection, track_id: str) -> bool:
    """Return whether the track still has a file, or a library folder still lists it."""
    row = connection.execute(
        "SELECT path FROM track_locations WHERE track_id=?", (track_id,)
    ).fetchone()
    if row is None:
        return False
    if Path(str(row[0])).is_file():
        return True
    listed = connection.execute(
        "SELECT 1 FROM root_tracks WHERE track_id=? AND present=1 LIMIT 1", (track_id,)
    ).fetchone()
    return listed is not None


def _put_back(target: Path, source: Path) -> None:
    """Move the file ``attach`` placed at ``target`` back to ``source``.

    A rename is used on the same volume; on another volume the file is copied back with an
    exclusive create and the copy in the library is removed. Raises ``TrackAttachError`` when the
    file cannot be put back, with the path where it is.
    """
    try:
        os.rename(target, source)
        return
    except OSError:
        pass
    created = False
    try:
        with target.open("rb") as reader, source.open("xb") as writer:
            created = True
            shutil.copyfileobj(reader, writer, _COPY_CHUNK_BYTES)
            writer.flush()
            os.fsync(writer.fileno())
        target.unlink()
    except OSError as error:
        if created:
            with contextlib.suppress(OSError):
                source.unlink()
        raise TrackAttachError(
            f"The file could not be put back at {source}; it is at {target} ({error})."
        ) from error
