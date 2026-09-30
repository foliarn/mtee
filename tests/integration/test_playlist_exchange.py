from __future__ import annotations

import hashlib
import json
import shutil
import wave
import zipfile
from pathlib import Path
from typing import cast

import pytest

from mtee.domain.jobs import JobCancelledError
from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.playlist_exchange import decode_manifest, safe_archive_path
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.jobs import JobContext
from mtee.services.metadata_reader import MetadataReader
from mtee.services.playlist_exchange import PlaylistExchange
from mtee.services.playlist_service import PlaylistService


class Context:
    is_cancelled = False

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise JobCancelledError("test cancelled")

    def report_progress(self, _value: float) -> None:
        pass


def _collection(folder: Path):
    folder.mkdir()
    database = Database(folder / "catalogue.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    repository = PlaylistsRepository(database)
    service = PlaylistService(repository, library)
    exchange = PlaylistExchange(service, FileAccessCoordinator(), folder)
    return database, library, repository, service, exchange


def _add(library: LibraryRepository, path: Path, metadata: MetadataSnapshot | None = None) -> str:
    root = library.add_root(path.parent)
    return library.upsert_location(
        root["id"],
        path.name,
        path,
        SourceRevision.observe(path),
        metadata or MetadataReader().read(path),
        root["scanGeneration"],
    )


def _wave(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)


def test_portable_match_across_uuid_and_root_changes_and_zip_bytes(tmp_path: Path) -> None:
    first = _collection(tmp_path / "first")
    second = _collection(tmp_path / "second")
    context = cast(JobContext, Context())
    try:
        source = tmp_path / "first" / "song.wav"
        _wave(source)
        source_id = _add(first[1], source, MetadataSnapshot(title=("Song",), artist=("Alice",)))
        playlist = first[2].create(
            "Road", entries=[{"snapshot": {"title": "Missing", "artist": "X"}}]
        )
        first[3].add(playlist, [source_id])
        manifest_path = tmp_path / "backup.mteeplaylist"
        first[4].export(playlist, manifest_path, False, context)
        assert str(tmp_path) not in manifest_path.read_text()
        copy = tmp_path / "second" / "different-name.wav"
        shutil.copyfile(source, copy)
        local_id = _add(second[1], copy)
        assert local_id != source_id
        manifest = second[4].read(manifest_path)
        matches = second[4].preview(manifest, context)
        assert matches[0]["status"] == "missing"
        assert matches[1]["track_id"] == local_id
        restored = second[4].commit_import(manifest, matches)
        assert [e["track_id"] for e in second[2].entries(restored)] == [None, local_id]
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        archive_path = tmp_path / "complete.zip"
        result = first[4].export(playlist, archive_path, True, context)
        assert result["missing"] == 1
        with zipfile.ZipFile(archive_path) as archive:
            archived = second[4].read(archive_path)["entries"][1]["audio"]
            assert archive.read(archived) == source.read_bytes()
        manifest, matches, extracted = second[4].extract_and_scan(archive_path, tmp_path, context)
        assert matches[0]["status"] == "missing"
        assert matches[1]["track_id"]
        assert Path(extracted).is_dir()
        second[4].commit_import(manifest, matches)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        with pytest.raises(FileExistsError):
            first[4].export(playlist, archive_path, True, context)
        assert first[4].read(archive_path)["name"] == "Road"
    finally:
        first[0].close()
        second[0].close()


def test_two_exact_local_copies_require_a_choice(tmp_path: Path) -> None:
    database, library, _repository, _service, exchange = _collection(tmp_path / "library")
    try:
        first = tmp_path / "library" / "one.wav"
        second = tmp_path / "library" / "two.wav"
        _wave(first)
        shutil.copyfile(first, second)
        ids = {_add(library, first), _add(library, second)}
        manifest = {
            "entries": [
                {
                    "snapshot": {"title": "Unknown", "artist": ""},
                    "sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
                }
            ]
        }
        matches = exchange.preview(manifest, cast(JobContext, Context()))
        assert matches[0]["track_id"] is None
        assert matches[0]["status"] == "ambiguous"
        assert {c["id"] for c in matches[0]["candidates"]} == ids
    finally:
        database.close()


@pytest.mark.parametrize(
    "name",
    [
        "../evil.wav",
        "/absolute.wav",
        "C:/audio.wav",
        "a\\b.wav",
        "audio/CON.wav",
        "a/file.wav:ads",
        "a/foo. ",
    ],
)
def test_unsafe_archive_paths_are_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        safe_archive_path(name)


def test_archive_collisions_and_unknown_formats(tmp_path: Path) -> None:
    database, _library, _repository, _service, exchange = _collection(tmp_path / "library")
    try:
        archive = tmp_path / "bad.zip"
        with zipfile.ZipFile(archive, "w") as writer:
            writer.writestr("playlist.mteeplaylist", "{}")
            writer.writestr("audio/A.wav", b"one")
            writer.writestr("audio/a.wav", b"two")
        with pytest.raises(ValueError, match="duplicate"):
            exchange.read(archive)
        with pytest.raises(ValueError, match="version"):
            decode_manifest(json.dumps({"format": "mtee-playlist", "version": 999}).encode())
    finally:
        database.close()


def test_cancelled_export_and_stale_source_leave_no_destination(tmp_path: Path) -> None:
    database, library, repository, service, exchange = _collection(tmp_path / "library")
    try:
        source = tmp_path / "library" / "song.wav"
        _wave(source)
        identity = _add(library, source)
        playlist = repository.create("Cancel")
        service.add(playlist, [identity])
        destination = tmp_path / "cancelled.zip"
        cancelled = Context()
        cancelled.is_cancelled = True
        with pytest.raises(JobCancelledError):
            exchange.export(playlist, destination, True, cast(JobContext, cancelled))
        assert not destination.exists()
        assert not list(tmp_path.glob("*.mtee-export.tmp"))
        source.write_bytes(source.read_bytes() + b"changed")
        with pytest.raises(ValueError, match="changed"):
            exchange.export(playlist, destination, True, cast(JobContext, Context()))
        assert not destination.exists()
    finally:
        database.close()


def test_interrupted_zip_resumes_without_overwrite_and_publishes_once(tmp_path: Path) -> None:
    database, library, repository, service, exchange = _collection(tmp_path / "library")
    context = cast(JobContext, Context())
    try:
        source = tmp_path / "library" / "song.wav"
        _wave(source)
        identity = _add(library, source)
        playlist = repository.create("Resume")
        service.add(playlist, [identity])
        archive = tmp_path / "resume.zip"
        exchange.export(playlist, archive, True, context)
        cancelled = Context()
        cancelled.is_cancelled = True
        with pytest.raises(JobCancelledError):
            exchange.extract_and_scan(archive, tmp_path, cast(JobContext, cancelled))
        operation = exchange.pending_imports()[0]["operation_id"]
        manifest, matches, folder = exchange.resume(operation, context)
        copied = Path(folder) / manifest["entries"][0]["audio"]
        assert copied.read_bytes() == source.read_bytes()
        copied.write_bytes(b"external change")
        with pytest.raises(ValueError, match="left untouched"):
            exchange.resume(operation, context)
        assert copied.read_bytes() == b"external change"
        copied.write_bytes(source.read_bytes())
        manifest, matches, _folder = exchange.resume(operation, context)
        imported = exchange.commit_import(manifest, matches, operation)
        assert exchange.commit_import(manifest, matches, operation) == imported
        assert exchange.pending_imports() == []
        assert len(repository.playlists()) == 2
    finally:
        database.close()
