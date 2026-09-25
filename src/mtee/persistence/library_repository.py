"""Durable catalog of selected roots, stable tracks and source snapshots."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mtee.domain.file_dates import FileDates, format_file_timestamp
from mtee.domain.metadata import MetadataSnapshot, format_bitrate
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.database import Database

__all__ = ["LibraryRepository"]


@dataclass(frozen=True, slots=True)
class TrackSource:
    """Current library snapshot required before a safe file mutation."""

    track_id: str
    path: Path
    revision: SourceRevision
    snapshot: MetadataSnapshot
    status: str


class LibraryRepository:
    """Store file references and read-only metadata without touching audio bytes."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def add_root(self, path: Path | str) -> dict[str, Any]:
        source = Path(path).expanduser().resolve(strict=False)
        key = normalize_path(source)
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM library_roots WHERE path_key = ?", (key,)
            ).fetchone()
            if row is None:
                root_id = str(uuid.uuid4())
                connection.execute(
                    "INSERT INTO library_roots(root_id,path,path_key,name) VALUES(?,?,?,?)",
                    (root_id, str(source), key, source.name or str(source)),
                )
                row = connection.execute(
                    "SELECT * FROM library_roots WHERE root_id = ?", (root_id,)
                ).fetchone()
            return _root_dict(row)

    def begin_scan(self, root_id: str, *, show_scanning: bool = True) -> int:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT scan_generation FROM library_roots WHERE root_id = ?", (root_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown library root: {root_id}")
            generation = int(row[0]) + 1
            update = "UPDATE library_roots SET scan_generation=?"
            if show_scanning:
                update += ",availability='scanning'"
            connection.execute(f"{update} WHERE root_id=?", (generation, root_id))
        return generation

    def upsert_location(
        self,
        root_id: str,
        relative_path: str,
        path: Path | str,
        revision: SourceRevision,
        metadata: MetadataSnapshot,
        scan_generation: int,
    ) -> str:
        return self.upsert_locations(
            root_id,
            [(relative_path, path, revision, metadata)],
            scan_generation,
        )[0]

    def upsert_locations(
        self,
        root_id: str,
        entries: Sequence[tuple[str, Path | str, SourceRevision, MetadataSnapshot | None]],
        scan_generation: int,
    ) -> list[str]:
        """Upsert one bounded scan batch in a single SQLite transaction."""
        with self._database.transaction() as connection:
            root = connection.execute(
                "SELECT scan_generation FROM library_roots WHERE root_id = ?", (root_id,)
            ).fetchone()
            if root is None:
                raise KeyError(f"Unknown library root: {root_id}")
            if int(root["scan_generation"]) != scan_generation:
                return [""] * len(entries)
            reserved_destinations = {
                normalize_path(Path(str(row[0])))
                for row in connection.execute(
                    "SELECT destination_path FROM file_operations "
                    "WHERE status IN ('prepared','needs_recovery')"
                )
            }
            identities: list[str] = []
            for relative_path, path, revision, metadata in entries:
                source = Path(path).resolve(strict=False)
                try:
                    observed = SourceRevision.observe(source, generation=revision.generation)
                except OSError:
                    identities.append("")
                    continue
                if source.is_symlink() or not source.is_file() or not revision.matches(observed):
                    identities.append("")
                    continue
                key = normalize_path(source)
                file_dates = FileDates.observe(source)
                if key in reserved_destinations:
                    identities.append("")
                    continue
                existing = connection.execute(
                    "SELECT * FROM track_locations WHERE path_key = ?", (key,)
                ).fetchone()
                if existing is None:
                    if metadata is None:
                        identities.append("")
                        continue
                    track_id = str(TrackId.new())
                    generation = 0
                    connection.execute("INSERT INTO tracks(track_id) VALUES(?)", (track_id,))
                    encoded = json.dumps(metadata.to_dict(), ensure_ascii=False, sort_keys=True)
                else:
                    track_id = str(existing["track_id"])
                    previous = SourceRevision(
                        size_bytes=int(existing["size_bytes"]),
                        mtime_ns=int(existing["mtime_ns"]),
                        file_id=existing["file_id"],
                        generation=int(existing["generation"]),
                    )
                    unchanged = previous.matches(revision)
                    generation = previous.generation + (0 if unchanged else 1)
                    if metadata is None and not unchanged:
                        identities.append("")
                        continue
                    if unchanged:
                        encoded = str(existing["metadata_json"])
                        metadata = MetadataSnapshot.from_dict(json.loads(encoded))
                    elif metadata is None:
                        identities.append("")
                        continue
                    else:
                        encoded = json.dumps(metadata.to_dict(), ensure_ascii=False, sort_keys=True)
                connection.execute(
                    "INSERT INTO track_locations(path_key,track_id,path,size_bytes,mtime_ns,"
                    "file_id,generation,duration_us,status,metadata_json,file_created_at_ns,"
                    "file_modified_at_ns) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(path_key) DO UPDATE SET "
                    "path=excluded.path,size_bytes=excluded.size_bytes,mtime_ns=excluded.mtime_ns,"
                    "file_id=excluded.file_id,generation=excluded.generation,duration_us=excluded.duration_us,"
                    "status=excluded.status,metadata_json=excluded.metadata_json,"
                    "file_created_at_ns=COALESCE(track_locations.file_created_at_ns,"
                    "excluded.file_created_at_ns),file_modified_at_ns=excluded.file_modified_at_ns",
                    (
                        key,
                        track_id,
                        str(source),
                        revision.size_bytes,
                        revision.mtime_ns,
                        revision.file_id,
                        generation,
                        metadata.technical.duration_us,
                        metadata.status,
                        encoded,
                        file_dates.created_at_ns,
                        file_dates.modified_at_ns,
                    ),
                )
                connection.execute(
                    "INSERT INTO root_tracks(root_id,track_id,relative_path,seen_generation,"
                    "present) "
                    "VALUES(?,?,?,?,1) "
                    "ON CONFLICT(root_id,track_id) DO UPDATE SET "
                    "relative_path=excluded.relative_path, "
                    "seen_generation=excluded.seen_generation,present=1",
                    (root_id, track_id, relative_path, scan_generation),
                )
                identities.append(track_id)
        return identities

    def unchanged_paths(
        self,
        root_id: str,
        entries: Sequence[tuple[str, SourceRevision]],
    ) -> set[str]:
        """Return paths whose recorded source revision still matches this scan batch."""
        if not entries:
            return set()
        unchanged: set[str] = set()
        connection = self._database.connection()
        for offset in range(0, len(entries), 900):
            batch = entries[offset : offset + 900]
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                "SELECT rt.relative_path,loc.size_bytes,loc.mtime_ns,loc.file_id "
                "FROM root_tracks AS rt JOIN track_locations AS loc "
                "ON loc.track_id=rt.track_id "
                f"WHERE rt.root_id=? AND rt.relative_path IN ({placeholders})",
                (root_id, *(relative for relative, _revision in batch)),
            ).fetchall()
            recorded = {
                str(row["relative_path"]): SourceRevision(
                    size_bytes=int(row["size_bytes"]),
                    mtime_ns=int(row["mtime_ns"]),
                    file_id=row["file_id"],
                )
                for row in rows
            }
            unchanged.update(
                relative
                for relative, revision in batch
                if (previous := recorded.get(relative)) is not None and previous.matches(revision)
            )
        return unchanged

    def upsert_folders(self, root_id: str, folders: Sequence[str], scan_generation: int) -> None:
        """Remember discovered folders, including empty ones, in one transaction."""
        if not folders:
            return
        with self._database.transaction() as connection:
            root = connection.execute(
                "SELECT scan_generation FROM library_roots WHERE root_id=?", (root_id,)
            ).fetchone()
            if root is None:
                raise KeyError(f"Unknown library root: {root_id}")
            if int(root[0]) != scan_generation:
                return
            connection.executemany(
                "INSERT INTO library_folders(root_id,relative_path,seen_generation,present) "
                "VALUES(?,?,?,1) "
                "ON CONFLICT(root_id,relative_path) DO UPDATE SET "
                "seen_generation=excluded.seen_generation,present=1",
                [(root_id, folder, scan_generation) for folder in folders],
            )

    def finish_scan(
        self, root_id: str, generation: int, *, complete: bool, available: bool = True
    ) -> None:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        status = (
            "available" if complete and available else "partial" if available else "unavailable"
        )
        with self._database.transaction() as connection:
            current = connection.execute(
                "SELECT scan_generation FROM library_roots WHERE root_id=?", (root_id,)
            ).fetchone()
            if current is None or int(current[0]) != generation:
                return
            if complete:
                connection.execute(
                    "UPDATE root_tracks SET present=0 WHERE root_id=? AND seen_generation<>?",
                    (root_id, generation),
                )
                connection.execute(
                    "UPDATE library_folders SET present=0 WHERE root_id=? AND seen_generation<>?",
                    (root_id, generation),
                )
            connection.execute(
                "UPDATE library_roots SET availability=?,last_scan_utc=? WHERE root_id=?",
                (status, now, root_id),
            )

    def mark_root_unavailable(self, root_id: str) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE library_roots SET availability='unavailable' WHERE root_id=?", (root_id,)
            )

    def roots(self) -> list[dict[str, Any]]:
        rows = (
            self._database.connection()
            .execute("SELECT * FROM library_roots ORDER BY name COLLATE NOCASE,path_key")
            .fetchall()
        )
        return [_root_dict(row) for row in rows]

    def folders(self, root_id: str) -> list[str]:
        folders: set[str] = {""}
        connection = self._database.connection()
        saved_folders = connection.execute(
            "SELECT relative_path FROM library_folders WHERE root_id=? AND present=1",
            (root_id,),
        ).fetchall()
        tracks = connection.execute(
            "SELECT relative_path FROM root_tracks WHERE root_id=? AND present=1",
            (root_id,),
        ).fetchall()
        for row in saved_folders:
            relative = str(row[0])
            parts = relative.split("/")
            folders.add(relative)
            for index in range(1, len(parts) + 1):
                folders.add("/".join(parts[:index]))
        for row in tracks:
            parent = str(Path(str(row[0])).parent.as_posix())
            if parent == ".":
                continue
            parts = parent.split("/")
            for index in range(1, len(parts) + 1):
                folders.add("/".join(parts[:index]))
        return sorted(folders, key=lambda item: (item.casefold(), item))

    def tracks_in_folder(self, root_id: str, relative_folder: str) -> list[dict[str, Any]]:
        where, parameters = _folder_filter(root_id, relative_folder)
        rows = (
            self._database.connection()
            .execute(
                "SELECT t.track_id,l.path,l.size_bytes,l.mtime_ns,l.file_id,l.generation,"
                "l.file_created_at_ns,l.file_modified_at_ns,"
                "l.status,l.metadata_json,rt.relative_path "
                "FROM root_tracks rt JOIN tracks t ON t.track_id=rt.track_id "
                "JOIN track_locations l ON l.track_id=t.track_id "
                f"WHERE rt.root_id=? AND rt.present=1 AND {where} "
                "ORDER BY rt.relative_path COLLATE NOCASE,rt.relative_path",
                parameters,
            )
            .fetchall()
        )
        return [_track_dict(row, root_id) for row in rows]

    def folder_stats(self, root_id: str, relative_folder: str) -> tuple[int, int, int]:
        """Return direct child track count, bytes and duration in one indexed query."""
        where, parameters = _folder_filter(root_id, relative_folder)
        row = (
            self._database.connection()
            .execute(
                "SELECT COUNT(*),COALESCE(SUM(l.size_bytes),0),COALESCE(SUM(l.duration_us),0) "
                "FROM root_tracks rt JOIN track_locations l ON l.track_id=rt.track_id "
                f"WHERE rt.root_id=? AND rt.present=1 AND {where}",
                parameters,
            )
            .fetchone()
        )
        return int(row[0]), int(row[1]), int(row[2])

    def track(self, track_id: str) -> dict[str, Any]:
        row = (
            self._database.connection()
            .execute(
                "SELECT l.path,l.size_bytes,l.mtime_ns,l.file_id,l.generation,l.status,"
                "l.file_created_at_ns,l.file_modified_at_ns,"
                "l.metadata_json,"
                "rt.root_id,COALESCE(rt.relative_path,'') AS relative_path "
                "FROM track_locations l LEFT JOIN root_tracks rt ON rt.track_id=l.track_id "
                "AND rt.present=1 "
                "WHERE l.track_id=? ORDER BY rt.root_id LIMIT 1",
                (track_id,),
            )
            .fetchone()
        )
        if row is None:
            return {}
        return _track_dict(row, str(row["root_id"] or ""), track_id=track_id)

    def source_record(self, track_id: str) -> TrackSource | None:
        """Return the path, cached metadata, and exact stored source revision."""
        row = (
            self._database.connection()
            .execute(
                "SELECT path,size_bytes,mtime_ns,file_id,generation,status,metadata_json "
                "FROM track_locations WHERE track_id=?",
                (track_id,),
            )
            .fetchone()
        )
        if row is None:
            return None
        return TrackSource(
            track_id=track_id,
            path=Path(str(row["path"])),
            revision=SourceRevision(
                size_bytes=int(row["size_bytes"]),
                mtime_ns=int(row["mtime_ns"]),
                file_id=row["file_id"],
                generation=int(row["generation"]),
            ),
            snapshot=MetadataSnapshot.from_dict(json.loads(str(row["metadata_json"]))),
            status=str(row["status"]),
        )

    def path_owner(self, path: Path | str) -> str | None:
        row = (
            self._database.connection()
            .execute(
                "SELECT track_id FROM track_locations WHERE path_key=?",
                (normalize_path(path),),
            )
            .fetchone()
        )
        return str(row[0]) if row is not None else None

    @staticmethod
    def copy_location_in_transaction(
        connection: sqlite3.Connection,
        *,
        destination: Path,
        revision: SourceRevision,
        metadata: MetadataSnapshot,
    ) -> str:
        """Register verified copied bytes as a new UUID in all containing roots."""
        final_path = destination.resolve(strict=True)
        key = normalize_path(final_path)
        if connection.execute("SELECT 1 FROM track_locations WHERE path_key=?", (key,)).fetchone():
            raise ValueError("A library track already owns the copied destination path.")
        memberships: list[tuple[str, str, int]] = []
        for root in connection.execute("SELECT root_id,path,scan_generation FROM library_roots"):
            root_path = Path(str(root["path"])).expanduser().resolve(strict=False)
            try:
                relative = final_path.relative_to(root_path).as_posix()
            except ValueError:
                continue
            if relative and relative != ".":
                memberships.append((str(root["root_id"]), relative, int(root["scan_generation"])))
        if not memberships:
            raise ValueError("The copy destination is outside every registered library root.")
        track_id = str(TrackId.new())
        dates = FileDates.observe(final_path)
        connection.execute("INSERT INTO tracks(track_id) VALUES(?)", (track_id,))
        connection.execute(
            "INSERT INTO track_locations(path_key,track_id,path,size_bytes,mtime_ns,file_id,"
            "generation,duration_us,status,metadata_json,file_created_at_ns,file_modified_at_ns) "
            "VALUES(?,?,?,?,?,?,0,?,?,?,?,?)",
            (
                key,
                track_id,
                str(final_path),
                revision.size_bytes,
                revision.mtime_ns,
                revision.file_id,
                metadata.technical.duration_us,
                metadata.status,
                json.dumps(metadata.to_dict(), ensure_ascii=False, sort_keys=True),
                dates.created_at_ns,
                dates.modified_at_ns,
            ),
        )
        connection.executemany(
            "INSERT INTO root_tracks(root_id,track_id,relative_path,seen_generation,present) "
            "VALUES(?,?,?,?,1)",
            [
                (root_id, track_id, relative, generation)
                for root_id, relative, generation in memberships
            ],
        )
        return track_id

    def registered_roots_for(self, path: Path | str) -> list[tuple[str, str, int]]:
        """Return registered roots containing a destination and its relative path."""
        candidate = Path(path).expanduser().absolute()
        candidate_parent = candidate.parent.resolve(strict=True)
        candidate = candidate_parent / candidate.name
        matches: list[tuple[str, str, int]] = []
        rows = self._database.connection().execute(
            "SELECT root_id,path,scan_generation FROM library_roots"
        )
        for row in rows:
            root_path = Path(str(row["path"])).expanduser().resolve(strict=False)
            try:
                relative = candidate.relative_to(root_path).as_posix()
            except ValueError:
                continue
            if relative and relative != ".":
                matches.append((str(row["root_id"]), relative, int(row["scan_generation"])))
        return matches

    @staticmethod
    def move_location_in_transaction(
        connection: sqlite3.Connection,
        *,
        track_id: str,
        expected_revision: SourceRevision,
        destination: Path,
        new_revision: SourceRevision,
        metadata: MetadataSnapshot,
    ) -> None:
        """Move one UUID and all of its registered-root memberships atomically."""
        final_path = destination.resolve(strict=True)
        file_dates = FileDates.observe(final_path)
        destination_key = normalize_path(final_path)
        conflict = connection.execute(
            "SELECT track_id FROM track_locations WHERE path_key=? AND track_id<>?",
            (destination_key, track_id),
        ).fetchone()
        if conflict is not None:
            raise ValueError("A different library track already owns the destination path.")
        memberships: list[tuple[str, str, int]] = []
        for root in connection.execute("SELECT root_id,path,scan_generation FROM library_roots"):
            root_path = Path(str(root["path"])).expanduser().resolve(strict=False)
            try:
                relative = final_path.relative_to(root_path).as_posix()
            except ValueError:
                continue
            if relative and relative != ".":
                memberships.append((str(root["root_id"]), relative, int(root["scan_generation"])))
        if not memberships:
            raise ValueError("The destination is outside every registered library root.")
        updated = connection.execute(
            "UPDATE track_locations SET path_key=?,path=?,size_bytes=?,mtime_ns=?,file_id=?,"
            "file_created_at_ns=?,file_modified_at_ns=?,"
            "generation=?,duration_us=?,status=?,metadata_json=? WHERE track_id=? "
            "AND size_bytes=? AND mtime_ns=? AND file_id IS ? AND generation=?",
            (
                destination_key,
                str(final_path),
                new_revision.size_bytes,
                new_revision.mtime_ns,
                new_revision.file_id,
                file_dates.created_at_ns,
                file_dates.modified_at_ns,
                new_revision.generation,
                metadata.technical.duration_us,
                metadata.status,
                json.dumps(metadata.to_dict(), ensure_ascii=False, sort_keys=True),
                track_id,
                expected_revision.size_bytes,
                expected_revision.mtime_ns,
                expected_revision.file_id,
                expected_revision.generation,
            ),
        ).rowcount
        if updated != 1:
            raise ValueError("The track location changed before the move could be recorded.")
        connection.execute("DELETE FROM root_tracks WHERE track_id=?", (track_id,))
        connection.executemany(
            "INSERT INTO root_tracks(root_id,track_id,relative_path,seen_generation,present) "
            "VALUES(?,?,?,?,1)",
            [
                (root_id, track_id, relative, generation)
                for root_id, relative, generation in memberships
            ],
        )

    def artwork_source(self, track_id: str) -> tuple[Path, SourceRevision] | None:
        row = (
            self._database.connection()
            .execute(
                "SELECT path,size_bytes,mtime_ns,file_id,generation FROM track_locations "
                "WHERE track_id=?",
                (track_id,),
            )
            .fetchone()
        )
        if row is None:
            return None
        revision = SourceRevision(
            size_bytes=int(row["size_bytes"]),
            mtime_ns=int(row["mtime_ns"]),
            file_id=row["file_id"],
            generation=int(row["generation"]),
        )
        return Path(str(row["path"])), revision


def normalize_path(path: Path | str) -> str:
    """Canonical comparison key; keep the user's spelling in the stored path."""
    return os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))


def _folder_filter(root_id: str, relative_folder: str) -> tuple[str, tuple[Any, ...]]:
    if not relative_folder:
        return "instr(rt.relative_path,'/')=0", (root_id,)
    prefix = relative_folder.rstrip("/") + "/"
    return (
        "substr(rt.relative_path,1,?)=? AND instr(substr(rt.relative_path,?+1),'/')=0",
        (root_id, len(prefix), prefix, len(prefix)),
    )


def _root_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["root_id"]),
        "path": str(row["path"]),
        "pathKey": str(row["path_key"]),
        "name": str(row["name"]),
        "availability": str(row["availability"]),
        "scanGeneration": int(row["scan_generation"]),
    }


def _track_dict(row: sqlite3.Row, root_id: str, *, track_id: str | None = None) -> dict[str, Any]:
    identity = track_id or str(row["track_id"])
    path = Path(str(row["path"]))
    relative = str(row["relative_path"])
    values = MetadataSnapshot.from_dict(json.loads(str(row["metadata_json"])))
    technical = values.technical
    title = _first(values.title) or path.stem
    artist = _joined(values.artist)
    album = _first(values.album)
    genre = _joined(values.genre)
    duration = technical.duration_us or 0
    seconds = round(duration / 1_000_000)
    parent = _folder_of(relative)
    folder_id = f"folder:{root_id}/{parent}"
    return {
        "id": identity,
        "folder": folder_id,
        "rootId": root_id,
        "relativePath": relative,
        "title": title,
        "artist": artist,
        "album": album,
        "genre": genre,
        "bpm": _number(_first(values.bpm)),
        "key": _first(values.key),
        "seconds": seconds,
        "durationUs": duration,
        "duration": _duration(seconds),
        "format": technical.container,
        "codec": technical.codec,
        "bitrate": technical.bitrate or 0,
        "bitrateText": format_bitrate(technical.bitrate),
        "sampleRate": technical.sample_rate or 0,
        "bitsPerSample": technical.bits_per_sample or 0,
        "sizeBytes": int(row["size_bytes"]),
        "sizeMb": int(row["size_bytes"]) / (1024 * 1024),
        "size": _size(int(row["size_bytes"])),
        "filename": path.name,
        "path": str(path),
        "fileCreatedAtNs": row["file_created_at_ns"],
        "fileModifiedAtNs": row["file_modified_at_ns"],
        "fileCreatedAtText": format_file_timestamp(row["file_created_at_ns"]),
        "fileModifiedAtText": format_file_timestamp(row["file_modified_at_ns"]),
        "dateAdded": "",
        "cover": -1,
        "coverUrl": f"image://artwork/{identity}/{int(row['generation'])}",
        "year": _first(values.date),
        "trackNumber": _first(values.track_number),
        "comment": _joined(values.comment),
        "status": str(row["status"]),
        "error": values.error,
        "revision": int(row["generation"]),
    }


def _folder_of(relative: str) -> str:
    parent = str(Path(relative).parent.as_posix())
    return "" if parent == "." else parent


def _first(values: tuple[str, ...]) -> str:
    return values[0] if values else ""


def _joined(values: tuple[str, ...]) -> str:
    return ", ".join(values)


def _number(value: str) -> int | str:
    try:
        number = float(value)
        return round(number) if math.isfinite(number) else value
    except (TypeError, ValueError, OverflowError):
        return value


def _duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _size(size_bytes: int) -> str:
    return (
        f"{size_bytes / (1024**3):.1f} GB"
        if size_bytes >= 1024**3
        else f"{size_bytes / (1024**2):.1f} MB"
    )
