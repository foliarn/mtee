"""Cross-container metadata writes preserve unrelated tags, covers, and decoded audio."""

from __future__ import annotations

import base64
import importlib.util
import shutil
from pathlib import Path
from typing import Any, cast

import pytest
from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, TRCK, TXXX, TYER
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm

from mtee.domain.metadata_edit import MetadataPatch
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.metadata_history_repository import MetadataHistoryRepository
from mtee.services.ffmpeg_runtime import FfmpegRuntime
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.metadata_adapters.id3 import Id3WaveAdapter
from mtee.services.metadata_reader import MetadataReader
from mtee.services.metadata_writer import MetadataEditService

_SUPPORTED = (
    "wav.wav",
    "mp3.mp3",
    "aiff.aiff",
    "flac.flac",
    "vorbis.ogg",
    "opus.opus",
    "m4a-aac.m4a",
    "m4a-alac.m4a",
)


def _create_fixtures(output: Path, runtime: FfmpegRuntime) -> None:
    repository = Path(__file__).resolve().parents[2]
    script = repository / "scripts" / "create_audio_fixtures.py"
    spec = importlib.util.spec_from_file_location("mtee_test_audio_fixture_generator", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.create_fixtures(output, runtime)


def _tag_preservation_markers(path: Path, cover: bytes) -> None:
    audio = MutagenFile(path, easy=False)
    assert audio is not None
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    assert tags is not None
    if hasattr(tags, "add") and audio.__class__.__name__ in {"WAVE", "MP3", "AIFF"}:
        if not tags.getall("TRCK"):
            tags.add(TRCK(encoding=3, text=["3/12"]))
        tags.add(TXXX(encoding=3, desc="MTEE-PRESERVE", text=["keep-this-frame"]))
        tags.add(APIC(encoding=3, mime="image/png", type=3, desc="synthetic", data=cover))
    elif isinstance(audio, FLAC):
        tags["MTEE_FIXTURE_MARKER"] = ["keep-this-comment"]
        picture = Picture()
        picture.type = 3
        picture.mime = "image/png"
        picture.desc = "synthetic"
        picture.data = cover
        audio.add_picture(picture)
    elif audio.__class__.__name__ in {"OggVorbis", "OggOpus"}:
        tags["MTEE_FIXTURE_MARKER"] = ["keep-this-comment"]
        tags["COVERART"] = [base64.b64encode(cover).decode("ascii")]
    elif isinstance(audio, MP4):
        tags["----:com.apple.iTunes:mtee_fixture_marker"] = [MP4FreeForm(b"keep-this-atom")]
        tags["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_PNG)]
    audio.save()


def _decoded_hash(runtime: FfmpegRuntime, path: Path) -> str:
    result = runtime.run(
        "ffmpeg",
        [
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        timeout_seconds=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _register(path: Path, data_dir: Path) -> tuple[Database, LibraryRepository, str]:
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(path.parent)
    generation = library.begin_scan(str(root["id"]))
    snapshot = MetadataReader().read(path)
    track_id = library.upsert_location(
        str(root["id"]), path.name, path, SourceRevision.observe(path), snapshot, generation
    )
    library.finish_scan(str(root["id"]), generation, complete=True)
    return database, library, track_id


@pytest.mark.parametrize("fixture_name", _SUPPORTED)
def test_metadata_edit_preserves_each_supported_format(fixture_name: str, tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    runtime = FfmpegRuntime(repository / "vendor" / "ffmpeg" / "bin")
    fixtures = tmp_path / "fixtures"
    _create_fixtures(fixtures, runtime)
    source = tmp_path / "library" / fixture_name
    source.parent.mkdir()
    shutil.copy2(fixtures / fixture_name, source)
    cover = (fixtures / "cover.png").read_bytes()
    _tag_preservation_markers(source, cover)
    source_hash = _decoded_hash(runtime, source)
    original_snapshot = MetadataReader().read(source)
    database, library, track_id = _register(source, tmp_path / "data")
    service = MetadataEditService(
        library, MetadataHistoryRepository(database), FileAccessCoordinator()
    )
    current = library.source_record(track_id)
    assert current is not None

    result = service.save(
        track_id,
        current.revision,
        MetadataPatch.from_mapping(
            {
                "title": "Verified edit",
                "artist": "Edited artist",
                "album": "Edited album",
                "genre": "Edited genre",
                "date": "2024-03-01",
                "comment": "Edited comment",
                "track_number": "4",
                "bpm": "128",
                "key": "F#m",
            }
        ),
        f"format-{fixture_name}",
    )

    assert result.status == "saved", result.message
    assert result.snapshot is not None
    assert result.snapshot.title == ("Verified edit",)
    assert result.snapshot.artist == ("Edited artist",)
    assert result.snapshot.album == ("Edited album",)
    assert result.snapshot.genre == ("Edited genre",)
    assert result.snapshot.date == ("2024-03-01",)
    assert result.snapshot.comment == ("Edited comment",)
    assert result.snapshot.track_number == ("4/12",)
    assert result.snapshot.bpm == ("128",)
    assert result.snapshot.key == ("F#m",)
    assert _decoded_hash(runtime, source) == source_hash
    after = MutagenFile(source, easy=False)
    assert after is not None and after.tags is not None
    after_tags = cast(Any, after.tags)
    if after.__class__.__name__ in {"WAVE", "MP3", "AIFF"}:
        assert after_tags.getall("TXXX:MTEE-PRESERVE")
        covers = after_tags.getall("APIC")
        assert len(covers) == 1 and bytes(covers[0].data) == cover
        if fixture_name == "aiff.aiff":
            compressed = source.with_name("compressed.aiff")
            shutil.copy2(source, compressed)
            raw = bytearray(compressed.read_bytes())
            raw[8:12] = b"AIFC"
            compressed.write_bytes(raw)
            capability = Id3WaveAdapter().capabilities(compressed)["title"]
            assert not capability[0]
            assert "uncompressed AIFF PCM" in capability[1]
    elif isinstance(after, FLAC):
        assert after_tags["MTEE_FIXTURE_MARKER"] == ["keep-this-comment"]
        assert len(after.pictures) == 1 and after.pictures[0].data == cover
    elif after.__class__.__name__ in {"OggVorbis", "OggOpus"}:
        assert after_tags["MTEE_FIXTURE_MARKER"] == ["keep-this-comment"]
        assert after_tags["COVERART"] == [base64.b64encode(cover).decode("ascii")]
    elif isinstance(after, MP4):
        assert (
            bytes(after_tags["----:com.apple.iTunes:mtee_fixture_marker"][0]) == b"keep-this-atom"
        )
        assert bytes(after_tags["covr"][0]) == cover
    undone = service.undo(result.operation_id, f"undo-{fixture_name}")
    assert undone.status == "saved", undone.message
    restored = MetadataReader().read(source)
    for field in (
        "title",
        "artist",
        "album",
        "genre",
        "date",
        "comment",
        "track_number",
        "bpm",
        "key",
    ):
        assert getattr(restored, field) == getattr(original_snapshot, field)
    assert _decoded_hash(runtime, source) == source_hash
    database.close()


def test_raw_aac_is_readable_but_metadata_write_is_explicitly_disabled(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    runtime = FfmpegRuntime(repository / "vendor" / "ffmpeg" / "bin")
    fixtures = tmp_path / "fixtures"
    _create_fixtures(fixtures, runtime)
    source = tmp_path / "library" / "aac-adts.adts"
    source.parent.mkdir()
    shutil.copy2(fixtures / "aac-adts.adts", source)
    database, library, track_id = _register(source, tmp_path / "data")
    service = MetadataEditService(
        library, MetadataHistoryRepository(database), FileAccessCoordinator()
    )
    assert not service.capabilities(track_id)["title"][0]
    assert "safe tag round-trip" in service.capabilities(track_id)["title"][1]
    database.close()


def test_id3_v23_date_is_read_only_until_round_trip_is_unambiguous(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    runtime = FfmpegRuntime(repository / "vendor" / "ffmpeg" / "bin")
    fixtures = tmp_path / "fixtures"
    _create_fixtures(fixtures, runtime)
    source = tmp_path / "library" / "mp3.mp3"
    source.parent.mkdir()
    shutil.copy2(fixtures / "mp3.mp3", source)
    audio = MP3(source)
    assert audio.tags is not None
    audio.tags.update_to_v23()
    audio.tags.add(TYER(encoding=3, text=["2001"]))
    audio.save(v2_version=3)
    database, library, track_id = _register(source, tmp_path / "data")
    service = MetadataEditService(
        library, MetadataHistoryRepository(database), FileAccessCoordinator()
    )
    current = library.source_record(track_id)
    assert current is not None

    result = service.save(
        track_id,
        current.revision,
        MetadataPatch.one("date", "2024"),
        "id3-v23-date",
    )

    assert result.status == "unsupported"
    assert "ID3v2.3 Date editing is disabled" in result.message
    tagged_v23 = MP3(source)
    assert tagged_v23.tags is not None and tagged_v23.tags.getall("TDRC")
    title_edit = service.save(
        track_id,
        current.revision,
        MetadataPatch.one("title", "ID3v2.3 title edit"),
        "id3-v23-title",
    )
    assert title_edit.status == "saved", title_edit.message
    assert title_edit.snapshot is not None
    assert title_edit.snapshot.title == ("ID3v2.3 title edit",)
    tagged_v23 = MP3(source)
    assert tagged_v23.tags is not None and tagged_v23.tags.getall("TDRC")
    database.close()


def test_m4a_bpm_and_key_use_integer_tempo_and_initialkey_atoms(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    runtime = FfmpegRuntime(repository / "vendor" / "ffmpeg" / "bin")
    fixtures = tmp_path / "fixtures"
    _create_fixtures(fixtures, runtime)
    source = tmp_path / "library" / "m4a-aac.m4a"
    source.parent.mkdir()
    shutil.copy2(fixtures / source.name, source)
    database, library, track_id = _register(source, tmp_path / "data")
    service = MetadataEditService(
        library, MetadataHistoryRepository(database), FileAccessCoordinator()
    )
    current = library.source_record(track_id)
    assert current is not None

    result = service.save(
        track_id,
        current.revision,
        MetadataPatch.from_mapping({"bpm": "128", "key": "F#m"}),
        "m4a-tempo-key",
    )

    assert result.status == "saved", result.message
    assert result.snapshot is not None
    assert result.snapshot.bpm == ("128",)
    assert result.snapshot.key == ("F#m",)
    audio = MP4(source)
    assert audio.tags is not None
    assert audio.tags["tmpo"] == [128]
    assert bytes(audio.tags["----:com.apple.iTunes:initialkey"][0]) == b"F#m"
    undone = service.undo(result.operation_id, "m4a-tempo-key-undo")
    assert undone.status == "saved", undone.message
    assert MetadataReader().read(source).bpm == ()
    assert MetadataReader().read(source).key == ()
    database.close()
