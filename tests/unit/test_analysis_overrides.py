from __future__ import annotations

import uuid
from pathlib import Path

from mtee.domain.analysis import AnalysisOverride
from mtee.domain.tracks import SourceRevision
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.database import Database


def test_override_history_is_separate_from_results_and_clear_only_deactivates(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "analysis.sqlite3")
    database.migrate()
    repository = AnalysisRepository(database)
    track_id = str(uuid.uuid4())
    revision = SourceRevision(12, 34, "test-file-id", 2)
    first = AnalysisOverride(str(uuid.uuid4()), track_id, "tempo_bpm", 120.0, revision)
    second = AnalysisOverride(str(uuid.uuid4()), track_id, "tempo_bpm", 60.0, revision)
    repository.save_override(first)
    repository.save_override(second)

    history = repository.overrides(track_id)
    assert len(history) == 2
    assert sum(int(item["active"]) for item in history) == 1
    assert any(item["value"] == 120.0 and int(item["active"]) == 0 for item in history)
    assert not repository.results(track_id)

    repository.clear_override(track_id, "tempo_bpm")
    assert all(int(item["active"]) == 0 for item in repository.overrides(track_id))
    database.close()
