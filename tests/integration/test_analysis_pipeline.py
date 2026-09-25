from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from tests.helpers.analysis_audio import write_music_fixture

from mtee.domain.analysis import AnalysisSpec
from mtee.domain.jobs import JobCancelledError
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.analysis_service import AnalysisService
from mtee.services.file_access import FileAccessCoordinator


class _Context:
    is_cancelled = False
    progress: list[float]

    def __init__(self) -> None:
        self.progress = []

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise JobCancelledError("cancelled")

    def report_progress(self, progress: float) -> None:
        self.progress.append(progress)


def _registered_track(path: Path, database: Database, library: LibraryRepository) -> str:
    root = library.add_root(path.parent)
    generation = library.begin_scan(root["id"])
    track_id = library.upsert_location(
        root["id"],
        path.name,
        path,
        SourceRevision.observe(path),
        MetadataSnapshot(title=("Synthetic C-major pulse",), technical=TechnicalInfo()),
        generation,
    )
    library.finish_scan(root["id"], generation, complete=True)
    return track_id


def test_complete_analysis_is_persisted_with_provenance_without_source_writes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fixture" / "synthetic.wav"
    write_music_fixture(path)
    original_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    track_id = _registered_track(path, database, library)
    repository = AnalysisRepository(database)
    service = AnalysisService(library, repository, FileAccessCoordinator())
    methods = [AnalysisSpec(name) for name in ("technical", "silence", "loudness", "tempo", "key")]
    preview = service.preview([track_id], methods)
    context = _Context()

    service.execute(preview, context)

    results = {row["analyzer"]: row for row in service.results(track_id)}
    assert set(results) == {"technical", "silence", "loudness", "tempo", "key"}
    assert all(
        row["status"] in {"available", "uncertain", "not_applicable"} for row in results.values()
    ), {name: (row["status"], row["diagnostics"]) for name, row in results.items()}
    assert results["technical"]["status"] == "available"
    assert results["key"]["config"]["profile_source"]
    assert context.progress[-1] == 1.0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original_digest
    assert (
        repository._database.connection().execute("SELECT status FROM analysis_runs").fetchone()[0]
        == "succeeded"
    )
    database.close()


def test_manual_tempo_survives_reanalysis_and_is_marked_stale_after_source_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fixture" / "pulse.wav"
    write_music_fixture(path)
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    track_id = _registered_track(path, database, library)
    repository = AnalysisRepository(database)
    service = AnalysisService(library, repository, FileAccessCoordinator())

    service.execute(service.preview([track_id], [AnalysisSpec("tempo")]), _Context())
    service.confirm(track_id, "tempo_bpm", 118.5)
    service.execute(service.preview([track_id], [AnalysisSpec("tempo")]), _Context())

    active = [item for item in service.overrides(track_id) if int(item["active"]) == 1]
    assert len(active) == 1 and active[0]["value"] == 118.5
    assert len(repository.overrides(track_id)) == 1
    with path.open("ab") as handle:
        handle.write(b"source revision changed")
    assert all(item["source_stale"] for item in service.results(track_id))
    assert all(item["source_stale"] for item in service.overrides(track_id))
    database.close()


def test_cancellation_keeps_completed_methods_and_marks_the_run_cancelled(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fixture" / "pulse.wav"
    write_music_fixture(path)
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    track_id = _registered_track(path, database, library)
    repository = AnalysisRepository(database)
    service = AnalysisService(library, repository, FileAccessCoordinator())
    context = _Context()
    original_report_progress = context.report_progress

    def cancel_after_first(progress: float) -> None:
        original_report_progress(progress)
        if progress >= 1 / 3:
            context.is_cancelled = True

    context.report_progress = cancel_after_first
    preview = service.preview(
        [track_id], [AnalysisSpec(name) for name in ("technical", "silence", "loudness")]
    )

    with pytest.raises(JobCancelledError):
        service.execute(preview, context)

    assert (
        database.connection().execute("SELECT status FROM analysis_runs").fetchone()[0]
        == "cancelled"
    )
    assert len(repository.results(track_id)) == 1
    database.close()
