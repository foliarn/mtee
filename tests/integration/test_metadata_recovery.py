"""A failure after native publication remains visible for recovery."""

from __future__ import annotations

import wave
from pathlib import Path

from mutagen.id3 import TIT2
from mutagen.wave import WAVE

from mtee.domain.metadata_edit import MetadataPatch
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.metadata_history_repository import MetadataHistoryRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.metadata_reader import MetadataReader
from mtee.services.metadata_writer import MetadataEditService


def _tagged_wave(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 800)
    audio = WAVE(path)
    audio.add_tags()
    assert audio.tags is not None
    audio.tags.add(TIT2(encoding=3, text=["Original title"]))
    audio.save(v2_version=4)


def test_database_failure_after_replace_keeps_backup_and_reports_recovery(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "library" / "recover.wav"
    _tagged_wave(source)
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(source.parent)
    generation = library.begin_scan(str(root["id"]))
    snapshot = MetadataReader().read(source)
    track_id = library.upsert_location(
        str(root["id"]),
        source.name,
        source,
        SourceRevision.observe(source),
        snapshot,
        generation,
    )
    library.finish_scan(str(root["id"]), generation, complete=True)
    current = library.source_record(track_id)
    assert current is not None
    history = MetadataHistoryRepository(database)

    def fail_complete(**_kwargs: object) -> None:
        raise OSError("Injected SQLite publication failure")

    monkeypatch.setattr(history, "complete", fail_complete)
    service = MetadataEditService(library, history, FileAccessCoordinator())

    result = service.save(
        track_id,
        current.revision,
        MetadataPatch.one("title", "Published but not committed"),
        "draft-recovery-1",
    )

    assert result.status == "recovery"
    assert MetadataReader().read(source).title == ("Published but not committed",)
    assert not service.capabilities(track_id)["title"][0]
    retry = service.save(
        track_id,
        current.revision,
        MetadataPatch.one("title", "Do not write over a pending recovery"),
        "draft-recovery-retry",
    )
    assert retry.status == "recovery"
    operation = history.get(result.operation_id)
    assert operation is not None and operation["status"] == "needs_recovery"
    assert Path(operation["backup_path"]).is_file()
    pending = service.incomplete_operations()
    assert len(pending) == 1
    assert pending[0]["recovery_situation"] == "replacement_present"
    database.close()
