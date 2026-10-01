"""A batch analysis reports a growing counter and one failure per track in error."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mtee.domain.analysis import AnalysisSettings
from mtee.services.analysis_service import AnalysisBatchError, AnalysisService, TrackReport


def _service(failing: set[str]) -> AnalysisService:
    service = object.__new__(AnalysisService)
    service._library = SimpleNamespace(  # type: ignore[attr-defined]
        source_record=lambda track_id: SimpleNamespace(path=Path(f"music/{track_id}.flac"))
    )

    def analyze_track(track_id, settings, **options):
        options["report_progress"](0.5)
        if track_id in failing:
            return TrackReport(track_id, False, "could not decode")
        return TrackReport(track_id, True)

    service.analyze_track = analyze_track  # type: ignore[method-assign]
    return service


def test_the_counter_grows_to_the_total_and_failures_carry_the_file_name() -> None:
    counters: list[tuple[int, int, str]] = []
    failures: list[tuple[str, str]] = []

    with pytest.raises(AnalysisBatchError, match="1 of 3 tracks"):
        _service({"b"}).run_batch(
            ["a", "b", "c"],
            AnalysisSettings(parallel_jobs=1),
            is_cancelled=lambda: False,
            report_progress=lambda _value: None,
            report_items=lambda done, total, name: counters.append((done, total, name)),
            report_failure=lambda name, message: failures.append((name, message)),
        )

    done_values = [done for done, _total, _name in counters]
    assert done_values == sorted(done_values)
    assert counters[0] == (0, 3, "a.flac")
    assert counters[-1] == (3, 3, "c.flac")
    assert all(total == 3 for _done, total, _name in counters)
    assert failures == [("b.flac", "could not decode")]
