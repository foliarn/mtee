from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from mtee.domain.conversion import ConversionSource
from mtee.domain.jobs import JobCancelledError
from mtee.domain.tracks import SourceRevision
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.media_decode_service import MediaDecodeService


def test_pcm_decode_emits_bounded_complete_frames(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    fixture = repository / ".local" / "fixtures" / "07-metadata" / "audio" / "wav.wav"
    if not fixture.is_file():
        pytest.skip("The locally generated synthetic WAV fixture is unavailable.")
    stream = MediaDecodeService(FileAccessCoordinator()).stream_pcm(
        fixture, sample_rate=22_050, channels=1, block_bytes=4097, duration_us=3_000_000
    )
    blocks = list(stream)

    assert stream.format.sample_rate == 22_050
    assert stream.format.channels == 1
    assert blocks
    assert all(0 < len(block) <= 4096 and len(block) % 2 == 0 for block in blocks)
    assert sum(map(len, blocks)) == pytest.approx(22_050 * 2 * 3, abs=4096)


def test_pcm_decode_observes_cancellation_before_start(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    fixture = repository / ".local" / "fixtures" / "07-metadata" / "audio" / "wav.wav"
    if not fixture.is_file():
        pytest.skip("The locally generated synthetic WAV fixture is unavailable.")
    service = MediaDecodeService(FileAccessCoordinator())
    stream = service.stream_pcm(fixture, is_cancelled=lambda: True)

    with pytest.raises(JobCancelledError):
        next(iter(stream))


def test_pcm_decode_stops_active_process_and_releases_source_read() -> None:
    repository = Path(__file__).resolve().parents[2]
    fixture = repository / ".local" / "fixtures" / "07-metadata" / "audio" / "wav.wav"
    if not fixture.is_file():
        pytest.skip("The locally generated synthetic WAV fixture is unavailable.")
    coordinator = FileAccessCoordinator()
    source = ConversionSource(str(uuid.uuid4()), fixture, SourceRevision.observe(fixture))
    checks = 0

    def cancel_after_first_block() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    iterator = iter(
        MediaDecodeService(coordinator).stream_pcm(source, is_cancelled=cancel_after_first_block)
    )
    assert next(iterator)
    with pytest.raises(JobCancelledError):
        next(iterator)
    assert coordinator.tracked_count() == 0
