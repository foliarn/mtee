from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from mutagen.id3 import TIT2
from mutagen.wave import WAVE

from mtee.domain.conversion import (
    ConversionRequest,
    ConversionSettings,
    ConversionSource,
)
from mtee.domain.jobs import JobCancelledError
from mtee.domain.tracks import SourceRevision, sha256_of_file
from mtee.persistence.database import Database
from mtee.persistence.derivations_repository import DerivationsRepository
from mtee.services.conversion_service import ConversionService
from mtee.services.media_probe import MediaProbeService


@pytest.mark.parametrize(
    ("format_id", "quality", "expected_codec"),
    [
        ("mp3", "192k", "mp3"),
        ("flac", "5", "flac"),
        ("wav", "16-bit PCM", "pcm_s16le"),
        ("aiff", "16-bit PCM", "pcm_s16be"),
        ("vorbis", "q3", "vorbis"),
        ("opus", "96k", "opus"),
        ("m4a-aac", "128k", "aac"),
        ("m4a-alac", "lossless", "alac"),
    ],
)
def test_conversion_verifies_and_publishes_a_copy_without_touching_source(
    tmp_path: Path, format_id: str, quality: str, expected_codec: str
) -> None:
    repository = Path(__file__).resolve().parents[2]
    fixture = repository / ".local" / "fixtures" / "07-metadata" / "audio" / "wav.wav"
    if not fixture.is_file():
        pytest.skip("The locally generated synthetic WAV fixture is unavailable.")
    source_dir = tmp_path / "àudio with spaces ' & brackets"
    source_dir.mkdir()
    source = source_dir / fixture.name
    shutil.copy2(fixture, source)
    tagged = WAVE(source)
    tagged.add_tags()
    assert tagged.tags is not None
    tagged.tags.add(TIT2(encoding=3, text="Source title"))
    tagged.save()
    source_digest = sha256_of_file(source)
    output_dir = tmp_path / "Converted"
    output_dir.mkdir()
    source_ref = ConversionSource(str(uuid.uuid4()), source, SourceRevision.observe(source))
    request = ConversionRequest((source_ref,), output_dir, ConversionSettings(format_id, quality))
    service = ConversionService()
    preview = service.preview(request)
    assert preview.executable
    item = preview.items[0]

    result = service.convert_item(preview, item)

    assert result.status == "completed", result.message
    assert result.output_probe is not None
    assert result.output_probe.codec == expected_codec
    assert item.destination.is_file()
    assert result.source_sha256 == source_digest == sha256_of_file(source)
    assert result.output_sha256 == sha256_of_file(item.destination)
    assert dict(result.metadata_report)["Title"] in {
        "Copied and verified",
        "Changed representation",
    }
    assert dict(result.metadata_report)["Cover art"] == "No source artwork"
    assert not list(output_dir.glob("*.tmp"))
    if format_id == "flac":
        database = Database(tmp_path / "conversion.sqlite3")
        database.migrate()
        lineage = DerivationsRepository(database)
        lineage.record(result, preview.ffmpeg_version)
        assert lineage.attempts()[0]["status"] == "completed"
        assert result.derivation is not None
        assert lineage.derivation(result.derivation.derived_track_id) is not None
        database.close()


def test_conversion_collision_never_replaces_existing_output(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    fixture = repository / ".local" / "fixtures" / "07-metadata" / "audio" / "wav.wav"
    if not fixture.is_file():
        pytest.skip("The locally generated synthetic WAV fixture is unavailable.")
    source = tmp_path / "wav.wav"
    shutil.copy2(fixture, source)
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    service = ConversionService()
    source_ref = ConversionSource(str(uuid.uuid4()), source, SourceRevision.observe(source))
    request = ConversionRequest((source_ref,), output_dir, ConversionSettings("flac", "5"))
    preview = service.preview(request)
    assert preview.executable
    sentinel = b"keep existing bytes"
    preview.items[0].destination.write_bytes(sentinel)

    result = service.convert_item(preview, preview.items[0])

    assert result.status == "conflict"
    assert preview.items[0].destination.read_bytes() == sentinel
    assert not list(output_dir.glob("*.tmp"))


def test_active_conversion_cancellation_leaves_no_partial_output(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    fixture = repository / ".local" / "fixtures" / "07-metadata" / "audio" / "wav.wav"
    if not fixture.is_file():
        pytest.skip("The locally generated synthetic WAV fixture is unavailable.")
    source = tmp_path / "wav.wav"
    shutil.copy2(fixture, source)
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    source_ref = ConversionSource(str(uuid.uuid4()), source, SourceRevision.observe(source))
    request = ConversionRequest((source_ref,), output_dir, ConversionSettings("flac", "5"))
    preview = ConversionService().preview(request)
    checks = 0

    def cancel_during_process() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    with pytest.raises(JobCancelledError):
        ConversionService().convert_item(
            preview, preview.items[0], is_cancelled=cancel_during_process
        )
    assert not preview.items[0].destination.exists()
    assert not list(output_dir.iterdir())


def test_probe_exposes_only_the_verified_pinned_runtime_matrix() -> None:
    capabilities = MediaProbeService().capabilities()
    assert {"mp3", "flac", "wav", "aiff", "vorbis", "opus", "m4a-aac", "m4a-alac"}.issubset(
        {output.format_id for output in capabilities.outputs}
    )
