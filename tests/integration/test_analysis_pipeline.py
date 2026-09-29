"""End-to-end analysis of a real decoded file: tempo, key, waveform, permanence and tags."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from mutagen.wave import WAVE
from tests.helpers.analysis_audio import drum_loop, key_progression, write_wav

from mtee.domain.analysis import AnalysisSettings
from mtee.domain.conversion import ConversionSource
from mtee.domain.jobs import JobCancelledError
from mtee.domain.musical_key import MusicalKey
from mtee.domain.tracks import SourceRevision, sha256_of_file
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.metadata_history_repository import MetadataHistoryRepository
from mtee.services.analysis_service import AnalysisBatchError, AnalysisService
from mtee.services.audio_analyzer import AudioAnalyzer
from mtee.services.ffmpeg_runtime import FfmpegRuntime, FfmpegRuntimeError
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.media_decode_service import MediaDecodeService
from mtee.services.metadata_reader import MetadataReader
from mtee.services.metadata_writer import MetadataEditService
from mtee.services.waveform_service import WaveformService

_RATE = 44_100


def _require_ffmpeg() -> None:
    try:
        FfmpegRuntime().executable("ffmpeg")
    except FfmpegRuntimeError:
        pytest.skip("The bundled FFmpeg runtime is unavailable.")


class _Library:
    """A scanned library holding synthetic tracks, with the services around it."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.repository = AnalysisRepository(self.database)
        self.access = FileAccessCoordinator()
        self.analyzer = AudioAnalyzer(MediaDecodeService(self.access), self.access)
        self.writer = MetadataEditService(
            self.library, MetadataHistoryRepository(self.database), self.access
        )
        self.root_id = self.library.add_root(base / "music")["id"]
        self._entries: list[tuple[str, Path, SourceRevision, object]] = []

    def add_track(self, relative: str, bpm: float, tonic: int, minor: bool, seconds: int) -> str:
        path = self.base / "music" / relative
        signal = 0.5 * key_progression(tonic, minor, seconds, rate=_RATE)
        signal = signal + 0.6 * drum_loop(bpm, seconds, rate=_RATE)
        write_wav(path, signal, _RATE)
        generation = self.library.begin_scan(self.root_id)
        snapshot = MetadataReader().read(path)
        self.library.upsert_locations(
            self.root_id,
            [(relative, path, SourceRevision.observe(path), snapshot)],
            generation,
        )
        owner = self.library.path_owner(path)
        assert owner is not None
        return owner

    def service(self, *, write_tags: bool = False) -> AnalysisService:
        return AnalysisService(
            self.library,
            self.repository,
            self.analyzer,
            self.writer if write_tags else None,
        )

    def close(self) -> None:
        self.database.close()


@pytest.fixture
def library(tmp_path: Path):
    _require_ffmpeg()
    fixture = _Library(tmp_path)
    yield fixture
    fixture.close()


def test_a_track_is_analyzed_once_and_stored_without_touching_the_file(library: _Library) -> None:
    track_id = library.add_track("house.wav", 127.98, 9, True, 60)
    path = library.base / "music" / "house.wav"
    digest = sha256_of_file(path)
    progress: list[float] = []

    report = library.service().analyze_track(
        track_id, AnalysisSettings(), report_progress=progress.append
    )

    assert report.ok, report.message
    stored = library.repository.get(track_id)
    assert stored is not None
    assert stored.bpm == pytest.approx(127.98, abs=0.05)
    assert stored.key == MusicalKey(9, True)
    waveform = library.repository.load_waveform(track_id, None)
    assert waveform is not None and len(waveform) == 1200
    assert waveform.duration_us == pytest.approx(60_000_000, abs=50_000)
    assert max(waveform.highs) > 5_000
    assert progress == sorted(progress) and progress[-1] == 1.0
    assert sha256_of_file(path) == digest
    assert MetadataReader().read(path).bpm == ()  # nothing written to the tags


def test_the_stored_waveform_is_used_without_decoding_again(library: _Library) -> None:
    track_id = library.add_track("loop.wav", 124.0, 0, False, 30)
    record = library.library.source_record(track_id)
    assert record is not None
    duration = record.snapshot.technical.duration_us
    source = ConversionSource(track_id, record.path, record.revision)

    class _Forbidden:
        def analyze(self, *args, **kwargs):
            raise AssertionError("the waveform must come from the database")

    first = WaveformService(library.analyzer, library.repository).request(
        source, record.revision, duration
    )
    again = WaveformService(_Forbidden(), library.repository).request(  # type: ignore[arg-type]
        source, record.revision, duration
    )
    assert again == first
    assert len(first) == 1200

    # A tag edit rewrites the file; the audio, its length and its waveform stay.
    tags = WAVE(record.path)
    tags.add_tags()
    tags.save()
    assert (
        WaveformService(_Forbidden(), library.repository).stored(  # type: ignore[arg-type]
            track_id, duration
        )
        == first
    )


def test_a_batch_reports_progress_and_can_run_tracks_in_parallel(library: _Library) -> None:
    ids = [
        library.add_track("a.wav", 120.0, 0, False, 30),
        library.add_track("b.wav", 128.0, 2, True, 30),
        library.add_track("c.wav", 140.0, 7, False, 30),
    ]
    finished: list[str] = []
    progress: list[float] = []

    reports = library.service().run_batch(
        ids,
        AnalysisSettings(parallel_jobs=2),
        is_cancelled=lambda: False,
        report_progress=progress.append,
        on_track_done=finished.append,
    )

    assert [report.ok for report in reports] == [True, True, True]
    assert sorted(finished) == sorted(ids)
    assert progress[-1] == pytest.approx(1.0)
    bpms = [library.repository.get(track_id).bpm for track_id in ids]  # type: ignore[union-attr]
    assert bpms == [
        pytest.approx(120.0, abs=0.05),
        pytest.approx(128.0, abs=0.05),
        pytest.approx(140.0, abs=0.05),
    ]


def test_pending_skips_finished_tracks_unless_forced(library: _Library) -> None:
    first = library.add_track("a.wav", 120.0, 0, False, 20)
    second = library.add_track("b.wav", 128.0, 2, True, 20)
    service = library.service()
    assert service.pending([first, second], force=False) == [first, second]
    assert service.analyze_track(first, AnalysisSettings()).ok
    assert service.pending([first, second], force=False) == [second]
    assert service.pending([first, second], force=True) == [first, second]


def test_cancellation_stops_the_batch(library: _Library) -> None:
    track_id = library.add_track("a.wav", 120.0, 0, False, 20)
    with pytest.raises(JobCancelledError):
        library.service().run_batch(
            [track_id],
            AnalysisSettings(),
            is_cancelled=lambda: True,
            report_progress=lambda _value: None,
        )
    assert library.repository.get(track_id) is None


def test_a_failing_track_is_reported_and_the_others_are_kept(library: _Library) -> None:
    good = library.add_track("good.wav", 120.0, 0, False, 20)
    bad = library.add_track("bad.wav", 120.0, 0, False, 20)
    (library.base / "music" / "bad.wav").write_bytes(b"this is not audio")

    with pytest.raises(AnalysisBatchError, match="1 of 2 tracks"):
        library.service().run_batch(
            [bad, good],
            AnalysisSettings(),
            is_cancelled=lambda: False,
            report_progress=lambda _value: None,
        )

    assert library.repository.get(good) is not None
    assert library.repository.get(bad) is None


def test_edited_values_survive_a_reanalysis_and_tags_follow_the_option(library: _Library) -> None:
    track_id = library.add_track("tagged.wav", 126.0, 5, False, 40)
    path = library.base / "music" / "tagged.wav"
    settings = AnalysisSettings(notation="classic", write_tags=True)
    service = library.service(write_tags=True)

    report = service.analyze_track(track_id, settings)

    assert report.ok, report.message
    tags = MetadataReader().read(path)
    assert len(tags.bpm) == 1 and float(tags.bpm[0]) == pytest.approx(126.0, abs=0.05)
    assert tags.key == ("F",)
    stored = library.repository.get(track_id)
    assert stored is not None and not stored.bpm_user_edited
    assert stored.bpm == pytest.approx(126.0, abs=0.05)
    assert float(tags.bpm[0]) == pytest.approx(stored.bpm, abs=0.006)  # the tag keeps two decimals

    # The user edits the tempo: the flag protects it from the next analysis and tag write.
    library.repository.mark_user_edited([track_id], "bpm")
    record = library.library.source_record(track_id)
    assert record is not None
    from mtee.domain.metadata_edit import MetadataPatch

    saved = library.writer.save(
        track_id, record.revision, MetadataPatch.one("bpm", "130"), "draft-edit"
    )
    assert saved.status == "saved"

    assert service.analyze_track(track_id, settings).ok
    assert MetadataReader().read(path).bpm == ("130",)
    protected = library.repository.get(track_id)
    assert protected is not None and protected.bpm == pytest.approx(126.0, abs=0.05)
    assert protected.bpm_user_edited


def test_a_track_that_is_being_written_is_reported_not_skipped(library: _Library) -> None:
    track_id = library.add_track("busy.wav", 120.0, 0, False, 20)
    from mtee.domain.tracks import TrackId

    with library.access.acquire(TrackId.parse(track_id), "test edit", timeout_seconds=0):
        report = library.service().analyze_track(track_id, AnalysisSettings())
    assert not report.ok
    assert library.repository.get(track_id) is None
    assert np.isfinite(1.0)
