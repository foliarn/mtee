from __future__ import annotations

import shutil
import struct
import uuid
from pathlib import Path

from mtee.domain.conversion import ConversionSource
from mtee.domain.tracks import SourceRevision, sha256_of_file
from mtee.domain.waveform import WaveformConfig, WaveformData, WaveformLevel
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.media_decode_service import MediaDecodeService
from mtee.services.media_probe import MediaProbeService
from mtee.services.waveform_cache import WaveformCache
from mtee.services.waveform_service import WaveformService


def test_waveform_cache_round_trips_and_ignores_truncated_items(tmp_path: Path) -> None:
    cache = WaveformCache(tmp_path)
    revision = SourceRevision(12, 34, "vol:file", 2)
    data = WaveformData(
        "track-id",
        revision,
        WaveformConfig(sample_rate=8_000, channels=1, bin_ms=10),
        100_000,
        (WaveformLevel(2, 1, (-20, 20, -32768, 32767)), WaveformLevel(1, 1, (-32768, 32767))),
    )
    path = cache.store(data)
    assert cache.load(data.track_id, revision, data.config) == data
    assert cache.load(data.track_id, revision.bumped(), data.config) is None
    path.write_bytes(b"MTEEWFM1\x01")
    assert cache.load(data.track_id, revision, data.config) is None


def test_cache_item_publishes_under_owned_directory(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    cache = WaveformCache(root)
    data = WaveformData(
        "track-id",
        SourceRevision(1, 1),
        WaveformConfig(),
        1,
        (WaveformLevel(1, 2, (0, 1, 0, 1)),),
    )
    result = cache.store(data)
    assert result.resolve().parent == (root / "waveforms").resolve()
    assert struct.unpack("<hhhh", struct.pack("<hhhh", *data.base.values)) == data.base.values


def test_revision_invalidation_keeps_only_compatible_cache_items(tmp_path: Path) -> None:
    cache = WaveformCache(tmp_path)
    original_revision = SourceRevision(10, 20, generation=0)
    updated_revision = original_revision.bumped()
    config = WaveformConfig()
    original = WaveformData(
        "track-id", original_revision, config, 10, (WaveformLevel(1, 2, (0, 0, 0, 0)),)
    )
    updated = WaveformData(
        "track-id", updated_revision, config, 10, (WaveformLevel(1, 2, (1, 1, 1, 1)),)
    )
    cache.store(original)
    cache.store(updated)

    assert cache.invalidate("track-id", updated_revision) == 1
    assert cache.load("track-id", updated_revision, config) == updated
    assert cache.load("track-id", original_revision, config) is None


def test_waveform_generation_decodes_a_copy_and_reuses_the_versioned_cache(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    fixture = repository / ".local" / "fixtures" / "07-metadata" / "audio" / "wav.wav"
    if not fixture.is_file():
        import pytest

        pytest.skip("The local synthetic WAV fixture is unavailable.")
    source_path = tmp_path / "àudio with spaces ' copy.wav"
    shutil.copy2(fixture, source_path)
    before = sha256_of_file(source_path)
    source_id = str(uuid.uuid4())
    revision = SourceRevision.observe(source_path)
    source = ConversionSource(source_id, source_path, revision)
    cache = WaveformCache(tmp_path / "cache")
    service = WaveformService(
        MediaDecodeService(FileAccessCoordinator()), cache, MediaProbeService()
    )

    data = service.request(source, revision)
    cached = service.request(source, revision)

    assert data == cached
    assert data.duration_us > 2_900_000
    assert data.base.bin_count > 100
    assert len(data.levels) > 1
    assert source_path.is_file()
    assert sha256_of_file(source_path) == before
