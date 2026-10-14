"""Loudness measured by Analyze: stored beside the tempo and key, never written to the tags."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import mutagen
import numpy as np
import pytest
from tests.helpers.analysis_audio import write_wav
from tests.helpers.analysis_library import RATE, AnalysisLibrary, require_ffmpeg

from mtee.domain.analysis import AnalysisSettings
from mtee.domain.tracks import sha256_of_file
from mtee.persistence.database import MIGRATIONS_DIR, Database
from mtee.services.analysis_service import AnalysisService
from mtee.services.metadata_reader import MetadataReader


@pytest.fixture
def library(tmp_path: Path):
    require_ffmpeg()
    fixture = AnalysisLibrary(tmp_path)
    yield fixture
    fixture.close()


class _SpyAnalyzer:
    """Forward to the real analyzer and remember which passes were asked for."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: list[dict[str, Any]] = []

    def analyze(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._inner.analyze(*args, **kwargs)


def _execute(library: AnalysisLibrary, sql: str, params: tuple[Any, ...]) -> None:
    library.database.connection().execute(sql, params)


def test_analyze_stores_loudness_and_peak_beside_the_tempo_and_key(
    library: AnalysisLibrary,
) -> None:
    track_id = library.add_track("house.wav", 124.0, 9, True, 30)

    report = library.service().analyze_track(track_id, AnalysisSettings())

    assert report.ok, report.message
    stored = library.repository.get(track_id)
    assert stored is not None
    assert stored.loudness_version == 1
    assert stored.integrated_lufs is not None and -40.0 < stored.integrated_lufs < 0.0
    assert stored.sample_peak_dbfs is not None and -6.0 < stored.sample_peak_dbfs < 0.0
    assert stored.bpm == pytest.approx(124.0, abs=0.05)
    # The player and the track list read the same values, while the measurement is current.
    row = library.library.track(track_id)
    assert row["loudnessLufs"] == pytest.approx(stored.integrated_lufs)
    assert row["samplePeakDbfs"] == pytest.approx(stored.sample_peak_dbfs)


def test_loudness_is_never_written_to_the_tags(library: AnalysisLibrary) -> None:
    track_id = library.add_track("house.wav", 124.0, 9, True, 30)
    path = library.base / "music" / "house.wav"

    report = library.service(write_tags=True).analyze_track(
        track_id, AnalysisSettings(write_tags=True)
    )

    assert report.ok, report.message
    assert library.repository.get(track_id).integrated_lufs is not None  # type: ignore[union-attr]
    tags = mutagen.File(path).tags or {}  # type: ignore[union-attr]
    raw_keys = [key.upper() for key in tags]
    assert not [key for key in raw_keys if "GAIN" in key or "R128" in key or "LOUD" in key]
    assert MetadataReader().read(path).bpm  # the tempo, as before, is what the tags receive


def test_a_track_analyzed_before_loudness_existed_gets_only_its_loudness(
    library: AnalysisLibrary,
) -> None:
    track_id = library.add_track("loop.wav", 128.0, 2, True, 30)
    service = library.service()
    assert service.analyze_track(track_id, AnalysisSettings()).ok
    before = library.repository.get(track_id)
    assert before is not None and before.bpm is not None
    path = library.base / "music" / "loop.wav"
    digest = sha256_of_file(path)
    # The state a database had before migration 025: tempo, key and waveform, no loudness.
    _execute(
        library,
        "UPDATE track_analysis SET integrated_lufs=NULL, sample_peak_dbfs=NULL, "
        "loudness_version=NULL WHERE track_id=?",
        (track_id,),
    )
    assert service.pending([track_id], force=False) == [track_id]
    spy = _SpyAnalyzer(library.analyzer)

    report = AnalysisService(library.library, library.repository, spy).analyze_track(
        track_id, AnalysisSettings()
    )

    assert report.ok, report.message
    # One decode for the loudness alone: the tempo and key are current and stay untouched.
    assert len(spy.calls) == 1
    assert spy.calls[0]["tonality"] is False
    assert spy.calls[0]["tempo_range"] is None
    assert spy.calls[0]["loudness"] is True
    after = library.repository.get(track_id)
    assert after is not None
    assert after.bpm == before.bpm
    assert after.key == before.key
    assert after.loudness_version == 1 and after.integrated_lufs is not None
    assert sha256_of_file(path) == digest  # the file itself is untouched
    assert service.pending([track_id], force=False) == []


def test_reanalyze_measures_everything_again(library: AnalysisLibrary) -> None:
    track_id = library.add_track("loop.wav", 128.0, 2, True, 30)
    spy = _SpyAnalyzer(library.analyzer)
    service = AnalysisService(library.library, library.repository, spy)
    assert service.analyze_track(track_id, AnalysisSettings()).ok

    assert service.analyze_track(track_id, AnalysisSettings(), force=True).ok

    assert spy.calls[-1]["tonality"] is True
    assert spy.calls[-1]["tempo_range"] is not None
    assert spy.calls[-1]["loudness"] is True


def test_a_silent_track_is_analyzed_with_no_loudness_value(library: AnalysisLibrary) -> None:
    write_wav(library.base / "music" / "silence.wav", np.zeros(RATE * 4, dtype=np.float32), RATE)
    track_id = library.register("silence.wav")
    service = library.service()

    assert service.analyze_track(track_id, AnalysisSettings()).ok

    stored = library.repository.get(track_id)
    assert stored is not None
    assert stored.loudness_version == 1
    assert stored.integrated_lufs is None and stored.sample_peak_dbfs is None
    assert library.library.track(track_id)["loudnessLufs"] is None
    assert service.pending([track_id], force=False) == []


def test_a_stored_loudness_of_other_audio_length_is_not_handed_out(
    library: AnalysisLibrary,
) -> None:
    track_id = library.add_track("loop.wav", 128.0, 2, True, 30)
    assert library.service().analyze_track(track_id, AnalysisSettings()).ok
    _execute(
        library,
        "UPDATE track_analysis SET source_duration_us=? WHERE track_id=?",
        (5_000_000, track_id),
    )

    assert library.library.track(track_id)["loudnessLufs"] is None


def test_migration_025_adds_empty_loudness_to_existing_analysis_rows(tmp_path: Path) -> None:
    before_025 = tmp_path / "before-025"
    before_025.mkdir()
    for path in MIGRATIONS_DIR.glob("*.sql"):
        if not path.name.startswith(("025_", "026_")):
            shutil.copy(path, before_025 / path.name)
    database_path = tmp_path / "mtee.sqlite3"
    legacy = Database(database_path, migrations_dir=before_025)
    legacy.migrate()
    connection = legacy.connection()
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("INSERT INTO tracks(track_id) VALUES('track-a')")
    connection.execute(
        "INSERT INTO track_analysis(track_id, bpm, source_duration_us, algorithm_version, "
        "analyzed_at_utc) VALUES('track-a', 120.5, 30000000, 2, '2026-10-01T00:00:00+00:00')"
    )
    legacy.close()

    upgraded = Database(database_path)
    applied = upgraded.migrate()

    assert [migration.version for migration in applied] == [25, 26]
    row = (
        upgraded.connection()
        .execute(
            "SELECT bpm, integrated_lufs, sample_peak_dbfs, loudness_version "
            "FROM track_analysis WHERE track_id='track-a'"
        )
        .fetchone()
    )
    assert tuple(row) == (120.5, None, None, None)
    upgraded.close()
