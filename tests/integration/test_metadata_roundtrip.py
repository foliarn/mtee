"""Verified field edits, preserved frames, recovery history, and Undo on copies."""

from __future__ import annotations

import struct
import wave
import zlib
from pathlib import Path

from mutagen.id3 import APIC, COMM, TALB, TIT2, TRCK, TXXX
from mutagen.wave import WAVE

from mtee.domain.metadata_edit import MetadataPatch
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.metadata_history_repository import MetadataHistoryRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.metadata_reader import MetadataReader
from mtee.services.metadata_writer import MetadataEditService


def _png_bytes() -> bytes:
    width = height = 1
    pixels = b"\x00\xff\x00\x00"

    def chunk(name: bytes, payload: bytes) -> bytes:
        content = name + payload
        return (
            struct.pack(">I", len(payload))
            + content
            + struct.pack(">I", zlib.crc32(content) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )


def _tagged_wave(path: Path, title: str = "Original title", *, multivalue: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 800)
    audio = WAVE(path)
    audio.add_tags()
    assert audio.tags is not None
    titles = [title, "Alternate title"] if multivalue else [title]
    audio.tags.add(TIT2(encoding=3, text=titles))
    audio.tags.add(TALB(encoding=3, text=["Synthetic album"]))
    audio.tags.add(TRCK(encoding=3, text=["3/12"]))
    audio.tags.add(TXXX(encoding=3, desc="CATALOGUE-ID", text=["keep-this-frame"]))
    audio.tags.add(APIC(encoding=3, mime="image/png", type=3, desc="front", data=_png_bytes()))
    audio.tags.add(COMM(encoding=3, lang="fra", desc="original", text=["other comment slot"]))
    audio.save(v2_version=4)


def _writer(
    path: Path, data_dir: Path
) -> tuple[Database, LibraryRepository, MetadataEditService, str]:
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(path.parent)
    generation = library.begin_scan(str(root["id"]))
    snapshot = MetadataReader().read(path)
    track_id = library.upsert_location(
        str(root["id"]),
        path.name,
        path,
        SourceRevision.observe(path),
        snapshot,
        generation,
    )
    library.finish_scan(str(root["id"]), generation, complete=True)
    service = MetadataEditService(
        library,
        MetadataHistoryRepository(database),
        FileAccessCoordinator(),
    )
    return database, library, service, track_id


def test_edit_preserves_unrelated_id3_frames_artwork_and_audio(tmp_path: Path) -> None:
    source = tmp_path / "library" / "cafe.wav"
    _tagged_wave(source)
    database, library, service, track_id = _writer(source, tmp_path / "data")
    with wave.open(str(source), "rb") as audio_before:
        original_audio = (
            audio_before.getparams(),
            audio_before.readframes(audio_before.getnframes()),
        )
    before = WAVE(source)
    assert before.tags is not None
    preserved = {
        frame.HashKey: bytes(frame._writeData())
        for frame in before.tags.values()
        if frame.FrameID in {"TALB", "TXXX", "APIC", "COMM"}
    }
    expected = library.source_record(track_id)
    assert expected is not None

    result = service.save(
        track_id,
        expected.revision,
        MetadataPatch.one("title", "Updated café title"),
        "draft-title-1",
    )

    assert result.status == "saved"
    assert result.snapshot is not None and result.snapshot.title == ("Updated café title",)
    assert result.revision is not None and result.revision.generation == 1
    reread = WAVE(source)
    assert reread.tags is not None
    actual_preserved = {
        frame.HashKey: bytes(frame._writeData())
        for frame in reread.tags.values()
        if frame.FrameID in {"TALB", "TXXX", "APIC", "COMM"}
    }
    assert actual_preserved == preserved
    assert reread.info.sample_rate == before.info.sample_rate
    with wave.open(str(source), "rb") as audio_after:
        assert (
            audio_after.getparams(),
            audio_after.readframes(audio_after.getnframes()),
        ) == original_audio
    updated_source = library.source_record(track_id)
    assert updated_source is not None
    assert updated_source.snapshot.title == ("Updated café title",)
    assert not list(source.parent.glob("*.mtee-edit-*.tmp.wav"))
    assert not list(source.parent.glob("*.mtee-edit-*.bak"))

    operation = MetadataHistoryRepository(database).get(result.operation_id)
    assert operation is not None
    database.close()

    reopened = Database(tmp_path / "data" / "mtee.sqlite3")
    reopened.migrate()
    restored = MetadataEditService(
        LibraryRepository(reopened),
        MetadataHistoryRepository(reopened),
        FileAccessCoordinator(),
    ).undo(result.operation_id, "draft-undo-1")

    assert restored.status == "saved"
    assert MetadataReader().read(source).title == ("Original title",)
    restored_audio = WAVE(source)
    assert restored_audio.tags is not None
    assert any(frame.FrameID == "APIC" for frame in restored_audio.tags.values())
    reopened.close()


def test_track_number_keeps_total_and_mixed_native_values_are_read_only(tmp_path: Path) -> None:
    source = tmp_path / "number.wav"
    _tagged_wave(source)
    database, library, service, track_id = _writer(source, tmp_path / "data")
    current = library.source_record(track_id)
    assert current is not None

    updated = service.save(
        track_id,
        current.revision,
        MetadataPatch.one("track_number", "4"),
        "draft-number-1",
    )
    assert updated.status == "saved"
    assert updated.snapshot is not None and updated.snapshot.track_number == ("4/12",)

    multivalue = tmp_path / "multiple.wav"
    _tagged_wave(multivalue, multivalue=True)
    database2, library2, service2, track_id2 = _writer(multivalue, tmp_path / "data-multiple")
    source2 = library2.source_record(track_id2)
    assert source2 is not None
    capability = service2.capabilities(track_id2)["title"]
    assert not capability[0]
    refused = service2.save(
        track_id2,
        source2.revision,
        MetadataPatch.one("title", "Replace both"),
        "draft-multivalue-1",
    )
    assert refused.status == "unsupported"
    assert MetadataReader().read(multivalue).title == ("Original title", "Alternate title")
    database.close()
    database2.close()


def test_explicit_removal_deletes_only_the_requested_tag(tmp_path: Path) -> None:
    source = tmp_path / "remove.wav"
    _tagged_wave(source)
    database, library, service, track_id = _writer(source, tmp_path / "data")
    current = library.source_record(track_id)
    assert current is not None

    result = service.save(
        track_id,
        current.revision,
        MetadataPatch.one("album", None),
        "draft-remove-album-1",
    )

    assert result.status == "saved"
    audio = WAVE(source)
    assert audio.tags is not None
    assert "TALB" not in audio.tags
    assert MetadataReader().read(source).title == ("Original title",)
    assert any(frame.FrameID == "TXXX" for frame in audio.tags.values())
    assert any(frame.FrameID == "APIC" for frame in audio.tags.values())
    database.close()


def test_external_revision_and_playback_lease_prevent_writes(tmp_path: Path) -> None:
    source = tmp_path / "locked.wav"
    _tagged_wave(source)
    database, library, service, track_id = _writer(source, tmp_path / "data")
    stale = library.source_record(track_id)
    assert stale is not None

    audio = WAVE(source)
    assert audio.tags is not None
    audio.tags.add(TIT2(encoding=3, text=["External title"]))
    audio.save(v2_version=4)
    source.touch()
    conflict = service.save(
        track_id,
        stale.revision,
        MetadataPatch.one("title", "MTEE must not overwrite"),
        "draft-conflict-1",
    )
    assert conflict.status == "conflict"
    assert MetadataReader().read(source).title == ("External title",)

    current = SourceRevision.observe(source, generation=stale.revision.generation)
    access = FileAccessCoordinator()
    history = MetadataHistoryRepository(database)
    service = MetadataEditService(library, history, access)
    from mtee.domain.tracks import TrackId

    lease = access.acquire_read(TrackId.parse(track_id), "playback fixture", timeout_seconds=0)
    lease.__enter__()
    busy = service.save(
        track_id,
        current,
        MetadataPatch.one("title", "Must wait"),
        "draft-busy-1",
    )
    lease.__exit__(None, None, None)
    assert busy.status == "busy"
    assert MetadataReader().read(source).title == ("External title",)
    database.close()
