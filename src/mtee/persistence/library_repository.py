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

from mtee.domain.analysis import LOUDNESS_ALGORITHM_VERSION, durations_agree, format_bpm
from mtee.domain.file_dates import FileDates, format_file_timestamp
from mtee.domain.metadata import MetadataSnapshot, format_bitrate
from mtee.domain.musical_key import MusicalKey, format_key, parse_key
from mtee.domain.tracks import SourceRevision, TrackId, sha256_of_file
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


@dataclass(frozen=True, slots=True)
class AnalysisDisplay:
    """How calculated tempo and key are written in the rows handed to the interface."""

    notation: str = "camelot"
    decimals: int = 2


_ANALYSIS_COLUMNS = (
    "a.bpm AS analysis_bpm,a.key_tonic AS analysis_key_tonic,a.key_minor AS analysis_key_minor,"
    "a.bpm_user_edited AS bpm_user_edited,a.key_user_edited AS key_user_edited,"
    "a.integrated_lufs AS analysis_lufs,a.sample_peak_dbfs AS analysis_peak_dbfs,"
    "a.loudness_version AS analysis_loudness_version,"
    "a.source_duration_us AS analysis_source_duration_us,"
)


class LibraryRepository:
    """Store file references and read-only metadata without touching audio bytes."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._display = AnalysisDisplay()

    def set_analysis_display(self, notation: str, decimals: int) -> None:
        """Choose the key notation and BPM decimals of the rows built from now on."""
        self._display = AnalysisDisplay(notation, decimals)

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
        observed_entries: list[
            tuple[str, Path, SourceRevision, MetadataSnapshot | None, FileDates] | None
        ] = []
        for relative_path, path, revision, metadata in entries:
            source = Path(path).resolve(strict=False)
            try:
                observed = SourceRevision.observe(source, generation=revision.generation)
                if source.is_symlink() or not source.is_file() or not revision.matches(observed):
                    observed_entries.append(None)
                    continue
                file_dates = FileDates.observe(source)
            except OSError:
                observed_entries.append(None)
                continue
            observed_entries.append((relative_path, source, observed, metadata, file_dates))

        source_by_key = {
            normalize_path(entry[1]): entry[1] for entry in observed_entries if entry is not None
        }
        derived_ids: dict[str, str] = {}
        if source_by_key:
            connection = self._database.connection()
            keys = list(source_by_key)
            for offset in range(0, len(keys), 900):
                batch = keys[offset : offset + 900]
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    "SELECT destination_path_key,derived_track_id,output_sha256 "
                    "FROM conversion_attempts WHERE status='completed' "
                    "AND destination_path_key IN (" + placeholders + ") "
                    "AND derived_track_id<>'' AND output_sha256<>''",
                    batch,
                ).fetchall()
                for row in rows:
                    key = str(row["destination_path_key"])
                    source = source_by_key.get(key)
                    if source is None:
                        continue
                    try:
                        if sha256_of_file(source) == str(row["output_sha256"]):
                            derived_ids[key] = str(row["derived_track_id"])
                    except OSError:
                        continue

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
            reserved_destinations.update(
                normalize_path(Path(str(row[0])))
                for row in connection.execute(
                    "SELECT destination_path FROM conversion_attempts "
                    "WHERE status IN ('prepared','running')"
                )
            )
            identities: list[str] = []
            for observed_entry in observed_entries:
                if observed_entry is None:
                    identities.append("")
                    continue
                relative_path, source, revision, metadata, file_dates = observed_entry
                key = normalize_path(source)
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
                    track_id = derived_ids.get(key) or str(TrackId.new())
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
                    "INSERT INTO root_tracks(root_id,track_id,relative_path,parent_relative_path,"
                    "seen_generation,present) "
                    "VALUES(?,?,?,?,?,1) "
                    "ON CONFLICT(root_id,track_id) DO UPDATE SET "
                    "relative_path=excluded.relative_path, "
                    "parent_relative_path=excluded.parent_relative_path, "
                    "seen_generation=excluded.seen_generation,present=1",
                    (
                        root_id,
                        track_id,
                        relative_path,
                        relative_path.rpartition("/")[0],
                        scan_generation,
                    ),
                )
                identities.append(track_id)
        return identities

    def register_derived_output(
        self, path: Path | str, metadata: MetadataSnapshot
    ) -> tuple[str, str] | None:
        """Catalog a verified conversion only when it is inside a selected root."""
        source = Path(path).resolve(strict=True)
        revision = SourceRevision.observe(source)
        for root in self.roots():
            root_path = Path(str(root["path"])).resolve(strict=False)
            try:
                relative = source.relative_to(root_path).as_posix()
            except ValueError:
                continue
            scan = (
                self._database.connection()
                .execute(
                    "SELECT scan_generation FROM library_roots WHERE root_id=?",
                    (str(root["id"]),),
                )
                .fetchone()
            )
            if scan is None:
                continue
            identities = self.upsert_locations(
                str(root["id"]),
                [(relative, source, revision, metadata)],
                int(scan["scan_generation"]),
            )
            if identities and identities[0]:
                return str(root["id"]), relative.rpartition("/")[0]
            return None
        return None

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

    def upsert_folders(
        self, root_id: str, folders: Sequence[str], scan_generation: int
    ) -> list[str]:
        """Remember folders and return paths that became newly present."""
        if not folders:
            return []
        connection = self._database.connection()
        newly_present: set[str] = set(folders)
        for offset in range(0, len(folders), 900):
            batch = folders[offset : offset + 900]
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                "SELECT relative_path FROM library_folders WHERE root_id=? AND present=1 "
                f"AND relative_path IN ({placeholders})",
                (root_id, *batch),
            ).fetchall()
            newly_present.difference_update(str(row[0]) for row in rows)
        with self._database.transaction() as connection:
            root = connection.execute(
                "SELECT scan_generation FROM library_roots WHERE root_id=?", (root_id,)
            ).fetchone()
            if root is None:
                raise KeyError(f"Unknown library root: {root_id}")
            if int(root[0]) != scan_generation:
                return []
            connection.executemany(
                "INSERT INTO library_folders(root_id,relative_path,parent_relative_path,"
                "seen_generation,present) "
                "VALUES(?,?,?,?,1) "
                "ON CONFLICT(root_id,relative_path) DO UPDATE SET "
                "parent_relative_path=excluded.parent_relative_path,"
                "seen_generation=excluded.seen_generation,present=1",
                [
                    (root_id, folder, folder.rpartition("/")[0], scan_generation)
                    for folder in folders
                ],
            )
        return sorted(newly_present)

    def finish_scan(
        self, root_id: str, generation: int, *, complete: bool, available: bool = True
    ) -> list[str]:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        status = (
            "available" if complete and available else "partial" if available else "unavailable"
        )
        with self._database.transaction() as connection:
            current = connection.execute(
                "SELECT scan_generation FROM library_roots WHERE root_id=?", (root_id,)
            ).fetchone()
            if current is None or int(current[0]) != generation:
                return []
            changed_parents: set[str] = set()
            if complete:
                removed = connection.execute(
                    "SELECT parent_relative_path FROM root_tracks WHERE root_id=? "
                    "AND seen_generation<>? AND present=1 UNION "
                    "SELECT parent_relative_path FROM library_folders WHERE root_id=? "
                    "AND seen_generation<>? AND present=1",
                    (root_id, generation, root_id, generation),
                ).fetchall()
                changed_parents.update(str(row[0]) for row in removed)
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
        return sorted(changed_parents)

    def current_generation(self, root_id: str) -> int:
        row = (
            self._database.connection()
            .execute("SELECT scan_generation FROM library_roots WHERE root_id=?", (root_id,))
            .fetchone()
        )
        if row is None:
            raise KeyError(f"Unknown library root: {root_id}")
        return int(row[0])

    def reconcile_folder(
        self,
        root_id: str,
        relative: str,
        *,
        present_files: Sequence[str],
        present_folders: Sequence[str],
        generation: int,
    ) -> list[str]:
        """Mark absent the direct children of one folder that a listing no longer shows.

        Nothing happens when the root was rescanned since ``generation`` was read: that
        scan owns the presence flags. Sub-folders that vanished take their whole subtree
        with them, as a complete scan would. Returns the parents whose content changed.
        """
        changed: set[str] = set()
        with self._database.transaction() as connection:
            current = connection.execute(
                "SELECT scan_generation FROM library_roots WHERE root_id=?", (root_id,)
            ).fetchone()
            if current is None or int(current[0]) != generation:
                return []
            files = set(present_files)
            folders = set(present_folders)
            for row in connection.execute(
                "SELECT track_id,relative_path FROM root_tracks WHERE root_id=? "
                "AND parent_relative_path=? AND present=1",
                (root_id, relative),
            ).fetchall():
                if str(row["relative_path"]) not in files:
                    connection.execute(
                        "UPDATE root_tracks SET present=0 WHERE root_id=? AND track_id=?",
                        (root_id, str(row["track_id"])),
                    )
                    changed.add(relative)
            for row in connection.execute(
                "SELECT relative_path FROM library_folders WHERE root_id=? "
                "AND parent_relative_path=? AND present=1",
                (root_id, relative),
            ).fetchall():
                gone = str(row["relative_path"])
                if gone in folders:
                    continue
                prefix = gone + "/"
                for table in ("root_tracks", "library_folders"):
                    connection.execute(
                        f"UPDATE {table} SET present=0 WHERE root_id=? AND present=1 "
                        "AND (relative_path=? OR substr(relative_path,1,?)=?)",
                        (root_id, gone, len(prefix), prefix),
                    )
                changed.add(relative)
        return sorted(changed)

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

    def folder_children(self, root_id: str, relative_parent: str) -> list[dict[str, Any]]:
        """Return indexed direct children with only the fields needed by Explorer."""
        connection = self._database.connection()
        root = connection.execute(
            "SELECT path,availability FROM library_roots WHERE root_id=?", (root_id,)
        ).fetchone()
        if root is None:
            return []
        parent = relative_parent.strip("/")
        child_folders = connection.execute(
            "SELECT f.relative_path,"
            "EXISTS(SELECT 1 FROM library_folders child "
            "WHERE child.root_id=f.root_id AND child.parent_relative_path=f.relative_path "
            "AND child.present=1) OR EXISTS(SELECT 1 FROM root_tracks child "
            "WHERE child.root_id=f.root_id AND child.parent_relative_path=f.relative_path "
            "AND child.present=1) AS has_children "
            "FROM library_folders f WHERE f.root_id=? AND f.parent_relative_path=? "
            "AND f.present=1 ORDER BY f.relative_path COLLATE NOCASE,f.relative_path",
            (root_id, parent),
        ).fetchall()
        child_tracks = connection.execute(
            "SELECT rt.track_id,rt.relative_path,rt.parent_relative_path,l.status,"
            "COALESCE(NULLIF(json_extract(l.metadata_json,'$.title[0]'),''),'') AS title "
            "FROM root_tracks rt JOIN track_locations l ON l.track_id=rt.track_id "
            "WHERE rt.root_id=? AND rt.parent_relative_path=? AND rt.present=1 "
            "ORDER BY rt.relative_path COLLATE NOCASE,rt.relative_path",
            (root_id, parent),
        ).fetchall()
        parent_id = f"folder:{root_id}/{parent}"
        rows = [
            {
                "kind": "folder",
                "id": f"folder:{root_id}/{row['relative_path']}",
                "name": str(row["relative_path"]).rsplit("/", 1)[-1],
                "path": str(root["path"]),
                "hasChildren": bool(row["has_children"]),
                "availability": str(root["availability"]),
            }
            for row in child_folders
        ]
        rows.extend(
            {
                "kind": "track",
                "id": str(row["track_id"]),
                "name": str(
                    row["title"] or row["relative_path"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
                ),
                "depth": 0,
                "expanded": False,
                "hasChildren": False,
                "folder": parent_id,
                "status": str(row["status"]),
            }
            for row in child_tracks
        )
        return rows

    def tracks_in_folder(self, root_id: str, relative_folder: str) -> list[dict[str, Any]]:
        where, parameters = _folder_filter(root_id, relative_folder)
        rows = (
            self._database.connection()
            .execute(
                "SELECT t.track_id,l.path,l.size_bytes,l.mtime_ns,l.file_id,l.generation,"
                f"l.file_created_at_ns,l.file_modified_at_ns,{_ANALYSIS_COLUMNS}"
                "l.status,l.metadata_json,rt.relative_path "
                "FROM root_tracks rt JOIN tracks t ON t.track_id=rt.track_id "
                "JOIN track_locations l ON l.track_id=t.track_id "
                "LEFT JOIN track_analysis a ON a.track_id=t.track_id "
                f"WHERE rt.root_id=? AND rt.present=1 AND {where} "
                "ORDER BY rt.relative_path COLLATE NOCASE,rt.relative_path",
                parameters,
            )
            .fetchall()
        )
        return [_track_dict(row, root_id, display=self._display) for row in rows]

    def tracks_by_ids(self, track_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Return the rows of these tracks, in the order given, one row per track.

        A track that is no longer listed by any root (recycled or its folder missing)
        keeps its row with an empty root, so a caller does not lose it silently.
        """
        wanted = list(dict.fromkeys(str(value) for value in track_ids))
        found: dict[str, dict[str, Any]] = {}
        connection = self._database.connection()
        for start in range(0, len(wanted), 500):
            chunk = wanted[start : start + 500]
            marks = ",".join("?" * len(chunk))
            rows = connection.execute(
                "SELECT l.track_id,l.path,l.size_bytes,l.mtime_ns,l.file_id,l.generation,"
                "l.file_created_at_ns,l.file_modified_at_ns,"
                f"{_ANALYSIS_COLUMNS}l.status,l.metadata_json,"
                "COALESCE(rt.relative_path,'') AS relative_path,rt.root_id AS root_id "
                "FROM track_locations l "
                "LEFT JOIN root_tracks rt ON rt.track_id=l.track_id AND rt.present=1 "
                "LEFT JOIN track_analysis a ON a.track_id=l.track_id "
                f"WHERE l.track_id IN ({marks}) ORDER BY rt.root_id",
                chunk,
            ).fetchall()
            for row in rows:
                identity = str(row["track_id"])
                if identity not in found:
                    found[identity] = _track_dict(
                        row, str(row["root_id"] or ""), track_id=identity, display=self._display
                    )
        return [found[identity] for identity in wanted if identity in found]

    def track_ids_in_tree(self, root_id: str, relative_folder: str) -> list[str]:
        """Return every readable track of a folder and of all its sub-folders."""
        prefix = relative_folder.strip("/")
        where = "AND substr(rt.relative_path,1,?)=?" if prefix else ""
        parameters: tuple[Any, ...] = (root_id,)
        if prefix:
            parameters += (len(prefix) + 1, prefix + "/")
        rows = (
            self._database.connection()
            .execute(
                "SELECT rt.track_id FROM root_tracks rt "
                "JOIN track_locations l ON l.track_id=rt.track_id "
                f"WHERE rt.root_id=? AND rt.present=1 AND l.status='readable' {where} "
                "ORDER BY rt.relative_path COLLATE NOCASE,rt.relative_path",
                parameters,
            )
            .fetchall()
        )
        return [str(row[0]) for row in rows]

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

    def tag_values(self, field: str, limit: int = 5000) -> list[str]:
        """Return the distinct values of ``album`` or ``genre`` used in the library."""
        if field not in {"album", "genre"}:
            return []
        rows = (
            self._database.connection()
            .execute(
                f"SELECT DISTINCT json_extract(metadata_json,'$.{field}[0]') AS value "
                "FROM track_locations WHERE value IS NOT NULL AND value<>'' "
                "ORDER BY value COLLATE NOCASE LIMIT ?",
                (limit,),
            )
            .fetchall()
        )
        return [str(row[0]) for row in rows]

    def artist_credit_rows(self) -> list[tuple[str, tuple[str, ...]]]:
        """Return ``(track_id, Artist tag values)`` of every track listed by a root.

        Only the Artist tag is read: the Album Artist tag and the titles never credit an artist.
        """
        rows = (
            self._database.connection()
            .execute(
                "SELECT l.track_id,l.metadata_json FROM track_locations l "
                "WHERE EXISTS (SELECT 1 FROM root_tracks rt "
                "WHERE rt.track_id=l.track_id AND rt.present=1)"
            )
            .fetchall()
        )
        return [
            (
                str(row["track_id"]),
                tuple(MetadataSnapshot.from_dict(json.loads(str(row["metadata_json"]))).artist),
            )
            for row in rows
        ]

    def track_folder(self, track_id: str) -> tuple[str, str] | None:
        """Return the ``(root_id, relative_folder)`` that lists the track, if it is present."""
        row = (
            self._database.connection()
            .execute(
                "SELECT root_id, relative_path FROM root_tracks "
                "WHERE track_id=? AND present=1 ORDER BY root_id LIMIT 1",
                (track_id,),
            )
            .fetchone()
        )
        if row is None:
            return None
        return str(row["root_id"]), _folder_of(str(row["relative_path"]))

    def track(self, track_id: str) -> dict[str, Any]:
        row = (
            self._database.connection()
            .execute(
                "SELECT l.path,l.size_bytes,l.mtime_ns,l.file_id,l.generation,l.status,"
                f"l.file_created_at_ns,l.file_modified_at_ns,{_ANALYSIS_COLUMNS}"
                "l.metadata_json,"
                "rt.root_id,COALESCE(rt.relative_path,'') AS relative_path "
                "FROM track_locations l LEFT JOIN root_tracks rt ON rt.track_id=l.track_id "
                "AND rt.present=1 "
                "LEFT JOIN track_analysis a ON a.track_id=l.track_id "
                "WHERE l.track_id=? ORDER BY rt.root_id LIMIT 1",
                (track_id,),
            )
            .fetchone()
        )
        if row is None:
            return {}
        return _track_dict(row, str(row["root_id"] or ""), track_id=track_id, display=self._display)

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

    def mark_recycled(self, track_id: str, expected_revision: SourceRevision) -> bool:
        """Hide confirmed recycled memberships only when the source snapshot still matches."""
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT size_bytes,mtime_ns,file_id,generation FROM track_locations WHERE track_id=?",
                (track_id,),
            ).fetchone()
            if row is None:
                return False
            current = SourceRevision(
                int(row["size_bytes"]),
                int(row["mtime_ns"]),
                row["file_id"],
                int(row["generation"]),
            )
            if not expected_revision.matches(current):
                return False
            connection.execute("UPDATE root_tracks SET present=0 WHERE track_id=?", (track_id,))
            return True

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


def _track_dict(
    row: sqlite3.Row,
    root_id: str,
    *,
    track_id: str | None = None,
    display: AnalysisDisplay | None = None,
) -> dict[str, Any]:
    display = display or AnalysisDisplay()
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
    tempo, tempo_text, key_text, key_camelot = _effective_tempo_and_key(row, values, display)
    loudness_lufs, sample_peak_dbfs = _stored_loudness(row, duration)
    return {
        "id": identity,
        "folder": folder_id,
        "rootId": root_id,
        "relativePath": relative,
        "title": title,
        "identityUncertain": not bool(values.title and values.artist),
        "artist": artist,
        "album": album,
        "genre": genre,
        "bpm": tempo,
        "bpmText": tempo_text,
        "key": key_text,
        "keyCamelot": key_camelot,
        "loudnessLufs": loudness_lufs,
        "samplePeakDbfs": sample_peak_dbfs,
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


def _stored_loudness(row: sqlite3.Row, duration_us: int) -> tuple[float | None, float | None]:
    """Return the integrated loudness and sample peak of a current measurement, else nothing.

    A measurement of an older version, or one made for audio of another length, is not
    handed out: the player plays such a track with no gain until Analyze measures it again.
    """
    columns = set(row.keys())
    if "analysis_loudness_version" not in columns:
        return None, None
    if row["analysis_loudness_version"] != LOUDNESS_ALGORITHM_VERSION:
        return None, None
    if not durations_agree(row["analysis_source_duration_us"], duration_us):
        return None, None
    lufs = row["analysis_lufs"]
    peak = row["analysis_peak_dbfs"]
    return (
        float(lufs) if lufs is not None else None,
        float(peak) if peak is not None else None,
    )


def _effective_tempo_and_key(
    row: sqlite3.Row, values: MetadataSnapshot, display: AnalysisDisplay
) -> tuple[int | float | str, str, str, str]:
    """Return tempo, tempo text, key text and Camelot code as the interface shows them.

    Order of precedence: value edited by the user (kept in the tag), calculated
    value, tag of the file.
    """
    columns = set(row.keys())
    tag_bpm = _number(_first(values.bpm))
    calculated_bpm = row["analysis_bpm"] if "analysis_bpm" in columns else None
    bpm_edited = bool(row["bpm_user_edited"]) if "bpm_user_edited" in columns else False
    if calculated_bpm is not None and not bpm_edited:
        tempo: int | float | str = float(calculated_bpm)
        tempo_text = format_bpm(tempo, display.decimals)
    else:
        tempo = tag_bpm
        tempo_text = "" if tag_bpm == "" else str(tag_bpm)

    tag_key = _first(values.key)
    tonic = row["analysis_key_tonic"] if "analysis_key_tonic" in columns else None
    minor = row["analysis_key_minor"] if "analysis_key_minor" in columns else None
    key_edited = bool(row["key_user_edited"]) if "key_user_edited" in columns else False
    if tonic is not None and minor is not None and not key_edited:
        key = MusicalKey(int(tonic), bool(minor))
        return tempo, tempo_text, key.text(display.notation), key.camelot
    parsed = parse_key(tag_key)
    return (
        tempo,
        tempo_text,
        format_key(tag_key, display.notation),
        parsed.camelot if parsed is not None else "",
    )


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
