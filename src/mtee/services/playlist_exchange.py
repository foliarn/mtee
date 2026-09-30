"""Cancellable portable manifests and exact audio ZIP copies, without clobbering."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import unicodedata
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from mtee.domain.jobs import JobCancelledError
from mtee.domain.playlist_exchange import (
    MAX_ARCHIVE_BYTES,
    MAX_COVER_BYTES,
    MAX_ENTRIES,
    MAX_MANIFEST_BYTES,
    decode_manifest,
    safe_archive_path,
)
from mtee.domain.playlists import musical_identity, portable_snapshot
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.jobs import JobContext
from mtee.services.library_scanner import LibraryScanner
from mtee.services.metadata_reader import MetadataReader
from mtee.services.playlist_images import copy_cover
from mtee.services.playlist_service import PlaylistService


class PlaylistExchange:
    def __init__(
        self, playlists: PlaylistService, access: FileAccessCoordinator, data_dir: Path
    ) -> None:
        self.playlists = playlists
        self.library = playlists.library
        self.repository = playlists.repository
        self.access = access
        self.data_dir = data_dir

    def _read_source(self, identity: str, context: JobContext, target: Any = None) -> str:
        source = self.library.source_record(identity)
        if source is None:
            raise ValueError("The source is no longer in the library.")
        with self.access.acquire_read(TrackId.parse(identity), "Export playlist"):
            before = SourceRevision.observe(source.path, generation=source.revision.generation)
            if not before.matches(source.revision):
                raise ValueError("A source changed. Rescan the library before exporting.")
            digest = hashlib.sha256()
            with source.path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    context.raise_if_cancelled()
                    digest.update(chunk)
                    if target is not None:
                        target.write(chunk)
            after = SourceRevision.observe(source.path, generation=source.revision.generation)
            current = self.library.source_record(identity)
            if not before.matches(after) or current is None or current.revision != source.revision:
                raise ValueError("A source changed during export. Retry after rescanning.")
            return digest.hexdigest()

    def export(
        self, identity: str, destination: Path, complete: bool, context: JobContext
    ) -> dict[str, Any]:
        if destination.exists():
            raise FileExistsError("This destination already exists. Choose another file name.")
        with self.playlists.lock:
            playlist = self.repository.playlist(identity)
            rows = self.playlists.rows(identity)
        manifest: dict[str, Any] = {
            "format": "mtee-playlist",
            "version": 1,
            "name": playlist["name"],
            "description": playlist["description"],
            "entries": [],
            "cover": "",
        }
        if playlist["cover_ref"]:
            cover = self.data_dir / "playlist-covers" / playlist["cover_ref"]
            if cover.stat().st_size > MAX_COVER_BYTES:
                raise ValueError("The cover is too large to export.")
            manifest["cover"] = base64.b64encode(cover.read_bytes()).decode("ascii")
        temporary = destination.with_name("." + str(uuid4()) + ".mtee-export.tmp")
        archive = None
        try:
            if complete:
                archive = zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_STORED)
            for index, row in enumerate(rows):
                context.raise_if_cancelled()
                entry: dict[str, Any] = {"snapshot": portable_snapshot(row), "sha256": ""}
                if row["available"]:
                    if archive is not None:
                        suffix = Path(row["filename"]).suffix.lower()
                        internal = safe_archive_path(
                            f"audio/{index + 1:06d}-{Path(row['filename']).stem[:220]}{suffix}"
                        )
                        with archive.open(internal, "w", force_zip64=True) as handle:
                            entry["sha256"] = self._read_source(row["trackId"], context, handle)
                        entry["audio"] = internal
                    else:
                        entry["sha256"] = self._read_source(row["trackId"], context)
                manifest["entries"].append(entry)
                context.report_progress((index + 1) / max(1, len(rows)) * 0.95)
            data = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            decode_manifest(data)
            if archive is not None:
                archive.writestr("playlist.mteeplaylist", data)
                archive.close()
                archive = None
            else:
                with temporary.open("xb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
            context.raise_if_cancelled()
            # Atomic creation on the same filesystem, with no destination replacement.
            os.link(temporary, destination)
            context.report_progress(1)
            return {"missing": sum(not r["available"] for r in rows), "path": str(destination)}
        finally:
            if archive is not None:
                archive.close()
            temporary.unlink(missing_ok=True)

    def read(self, path: Path) -> dict[str, Any]:
        if path.suffix.lower() != ".zip":
            with path.open("rb") as handle:
                return decode_manifest(handle.read(MAX_MANIFEST_BYTES + 1))
        with zipfile.ZipFile(path) as archive:
            self._validate_archive(archive)
            info = archive.getinfo("playlist.mteeplaylist")
            if info.file_size > MAX_MANIFEST_BYTES:
                raise ValueError("This manifest exceeds the 20 MB limit.")
            manifest = decode_manifest(archive.read(info))
            for entry in manifest["entries"]:
                if entry.get("audio") and entry["audio"] not in archive.namelist():
                    raise ValueError("The archive is missing an audio file listed in its manifest.")
            return manifest

    @staticmethod
    def _validate_archive(archive: zipfile.ZipFile) -> None:
        files = archive.infolist()
        if len(files) > MAX_ENTRIES + 2 or sum(f.file_size for f in files) > MAX_ARCHIVE_BYTES:
            raise ValueError("This archive exceeds 100,002 files or 20 GB uncompressed.")
        seen: set[str] = set()
        for info in files:
            name = safe_archive_path(info.filename.rstrip("/"))
            key = unicodedata.normalize("NFC", name).casefold()
            if key in seen or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("The archive contains duplicate names or symbolic links.")
            if info.flag_bits & 1:
                raise ValueError("Encrypted playlist archives are unsupported.")
            seen.add(key)
        if "playlist.mteeplaylist" not in seen:
            raise ValueError("This ZIP does not contain a MTEE playlist manifest.")

    def preview(self, manifest: dict[str, Any], context: JobContext) -> list[dict[str, Any]]:
        catalogue = [
            self.library.track(r[0])
            for r in self.repository.database.connection().execute(
                "SELECT DISTINCT track_id FROM root_tracks WHERE present=1"
            )
        ]
        by_music: dict[Any, list[dict[str, Any]]] = {}
        for row in catalogue:
            key = musical_identity(row)
            if key is not None:
                by_music.setdefault(key, []).append(row)
        fingerprints: dict[str, str] = {}
        matches = []
        for index, entry in enumerate(manifest["entries"]):
            context.raise_if_cancelled()
            snapshot = entry["snapshot"]
            candidates = by_music.get(musical_identity(snapshot), [])
            if not candidates:
                candidates = [r for r in catalogue if r.get("filename") == snapshot.get("filename")]
            # Different tags must not prevent an exact same-file transfer match.
            if entry.get("sha256"):
                candidates = candidates + [r for r in catalogue if r not in candidates]
            exact = []
            if entry.get("sha256"):
                for row in candidates:
                    context.raise_if_cancelled()
                    try:
                        if row["id"] not in fingerprints:
                            fingerprints[row["id"]] = self._read_source(row["id"], context)
                        if fingerprints[row["id"]] == entry["sha256"]:
                            exact.append(row)
                    except (OSError, ValueError):
                        continue
            suggested = exact or by_music.get(musical_identity(snapshot), [])
            if not suggested and snapshot.get("filename"):
                suggested = [r for r in catalogue if r.get("filename") == snapshot["filename"]]
            chosen = exact[0]["id"] if len(exact) == 1 else ""
            matches.append(
                {
                    "snapshot": snapshot,
                    "track_id": chosen or None,
                    "status": "matched" if chosen else "ambiguous" if suggested else "missing",
                    "candidates": [
                        {
                            "id": r["id"],
                            "title": r["title"],
                            "artist": r["artist"],
                            "filename": r["filename"],
                            "path": r["path"],
                        }
                        for r in suggested
                    ],
                }
            )
            context.report_progress((index + 1) / max(1, len(manifest["entries"])))
        return matches

    def commit_import(
        self, manifest: dict[str, Any], matches: list[dict[str, Any]], operation_id: str = ""
    ) -> str:
        entries = []
        ids: set[str] = set()
        music: set[Any] = set()
        for match in matches:
            identity = match.get("track_id")
            key = (
                musical_identity(self.library.track(identity))
                if identity
                else musical_identity(match["snapshot"])
            )
            if identity and (identity in ids or (key is not None and key in music)):
                raise ValueError(
                    "Two imported entries resolve to the same song. Keep one unmatched."
                )
            if identity:
                ids.add(identity)
                if key is not None:
                    music.add(key)
            entries.append({"track_id": identity, "snapshot": match["snapshot"]})
        cover_ref = ""
        if manifest.get("cover"):
            data = base64.b64decode(manifest["cover"], validate=True)
            cover_ref = copy_cover(data, self.data_dir / "playlist-covers")
        with self.playlists.lock:
            return self.repository.create(
                manifest["name"],
                description=manifest.get("description", ""),
                cover=cover_ref,
                entries=entries,
                operation_id=operation_id,
            )

    def pending_imports(self) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.repository.database.connection().execute(
                "SELECT operation_id,folder_path,phase,error FROM playlist_imports "
                "WHERE phase<>'completed' ORDER BY rowid DESC"
            )
        ]

    def _phase(self, operation: str, phase: str, error: str = "") -> None:
        with self.repository.database.transaction() as connection:
            connection.execute(
                "UPDATE playlist_imports SET phase=?,error=? WHERE operation_id=?",
                (phase, error, operation),
            )

    @staticmethod
    def _hash(path: Path, context: JobContext) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                context.raise_if_cancelled()
                digest.update(chunk)
        return digest.hexdigest()

    def extract_and_scan(
        self, archive_path: Path, destination: Path, context: JobContext, operation_id: str = ""
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        manifest = self.read(archive_path)
        if operation_id:
            row = (
                self.repository.database.connection()
                .execute("SELECT * FROM playlist_imports WHERE operation_id=?", (operation_id,))
                .fetchone()
            )
            if row is None or row["phase"] == "completed":
                raise ValueError("This import is already completed or unavailable.")
            if json.loads(row["manifest_json"]) != manifest:
                raise ValueError("The archive changed. Import it as a new playlist.")
            folder = Path(row["folder_path"])
            if not folder.is_dir() or folder.is_symlink() or folder.is_junction():
                raise ValueError("The extraction folder is unavailable or was replaced by a link.")
        else:
            if not destination.is_dir():
                raise ValueError("Choose an existing extraction folder.")
            operation_id = str(uuid4())
            folder = destination.resolve() / ("MTEE playlist " + operation_id)
            folder.mkdir()
            with self.repository.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO playlist_imports(operation_id,archive_path,folder_path,"
                    "manifest_json,phase) "
                    "VALUES(?,?,?,?, 'extracting')",
                    (operation_id, str(archive_path.resolve()), str(folder), json.dumps(manifest)),
                )
        try:
            self._phase(operation_id, "extracting")
            with zipfile.ZipFile(archive_path) as archive:
                self._validate_archive(archive)
                for index, entry in enumerate(manifest["entries"]):
                    context.raise_if_cancelled()
                    if not entry.get("audio"):
                        continue
                    relative = safe_archive_path(entry["audio"])
                    target = folder.joinpath(*relative.split("/"))
                    if not target.resolve().is_relative_to(folder.resolve()):
                        raise ValueError("An extraction path was replaced by a link.")
                    if target.is_symlink() or target.is_junction():
                        raise ValueError("An extraction file was replaced by a link.")
                    if target.exists():
                        if self._hash(target, context) != entry["sha256"]:
                            raise ValueError("An extracted file changed. It was left untouched.")
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_name("." + str(uuid4()) + ".part")
                    try:
                        digest = hashlib.sha256()
                        with archive.open(relative) as source, temporary.open("xb") as output:
                            while chunk := source.read(1024 * 1024):
                                context.raise_if_cancelled()
                                digest.update(chunk)
                                output.write(chunk)
                        if digest.hexdigest() != entry["sha256"]:
                            raise ValueError(
                                "An archived audio file does not match its fingerprint."
                            )
                        context.raise_if_cancelled()
                        os.link(temporary, target)
                    finally:
                        temporary.unlink(missing_ok=True)
                    context.report_progress((index + 1) / max(1, len(manifest["entries"])) * 0.6)
            self._phase(operation_id, "scanning")
            root = self.library.add_root(folder)
            generation = self.library.begin_scan(root["id"])
            try:
                for batch in LibraryScanner().scan(
                    folder, is_cancelled=lambda: context.is_cancelled
                ):
                    context.raise_if_cancelled()
                    if batch.issues:
                        raise OSError(batch.issues[0].message)
                    self.library.upsert_folders(root["id"], list(batch.folders), generation)
                    self.library.upsert_locations(
                        root["id"],
                        [
                            (e.relative_path, e.path, e.revision, MetadataReader().read(e.path))
                            for e in batch.entries
                        ],
                        generation,
                    )
                self.library.finish_scan(root["id"], generation, complete=True)
            except BaseException:
                self.library.finish_scan(root["id"], generation, complete=False)
                raise
            tracks = {
                r["relativePath"]: r for r in self.library.tracks_in_folder(root["id"], "audio")
            }
            matches = [
                {
                    "snapshot": e["snapshot"],
                    "track_id": tracks.get(e.get("audio", ""), {}).get("id"),
                    "status": "matched" if e.get("audio") in tracks else "missing",
                    "candidates": [],
                }
                for e in manifest["entries"]
            ]
            self._phase(operation_id, "ready")
            manifest["_operation_id"] = operation_id
            return manifest, matches, str(folder)
        except BaseException as error:
            self._phase(operation_id, "incomplete", str(error))
            if isinstance(error, JobCancelledError):
                raise
            raise ValueError(
                f"Import incomplete in {folder}. Files are preserved. {error}"
            ) from error

    def resume(
        self, operation_id: str, context: JobContext
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        row = (
            self.repository.database.connection()
            .execute(
                "SELECT archive_path,folder_path FROM playlist_imports WHERE operation_id=?",
                (operation_id,),
            )
            .fetchone()
        )
        if row is None:
            raise LookupError("This import is unavailable.")
        return self.extract_and_scan(
            Path(row["archive_path"]), Path(row["folder_path"]).parent, context, operation_id
        )
