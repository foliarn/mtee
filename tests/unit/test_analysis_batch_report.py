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


def test_a_file_the_tag_writer_refuses_is_not_a_failed_analysis() -> None:

    class Writer:
        def __init__(self, status: str) -> None:
            self.status = status

        def tag_conflicts(self, _track_id, _fields):
            return {}

        def save(self, track_id, _revision, _patch, _draft_id):
            return SimpleNamespace(
                status=self.status, message="Only PCM WAV files have been verified."
            )

    record = SimpleNamespace(
        track_id="a",
        path=Path("music/a.wav"),
        revision="r",
        snapshot=SimpleNamespace(bpm=(), key=()),
    )
    stored = SimpleNamespace(bpm=120.0, bpm_user_edited=False, key=None, key_user_edited=False)
    settings = AnalysisSettings(write_tags=True)

    for status, expected in (("unsupported", ""), ("failed", "Only PCM WAV")):
        service = object.__new__(AnalysisService)
        service._tag_writer = Writer(status)  # type: ignore[attr-defined]
        service._library = SimpleNamespace(source_record=lambda _id: record)  # type: ignore[attr-defined]
        message, conflict = service._write_tags(record, stored, settings)  # type: ignore[arg-type]
        assert conflict is None
        assert message.startswith(expected)
