"""One sentence per finished job: core job kinds, the generic fallback, plugin summaries."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from mtee.domain.job_summaries import (
    analysis_summary,
    count_sentence,
    fallback_summary,
    fixed,
    job_summary,
    moved_summary,
    recorded,
    recycled_summary,
    saved_summary,
    scan_summary,
)
from mtee.domain.jobs import (
    ERROR_CANCELLED,
    ERROR_INTERRUPTED,
    ERROR_UNHANDLED,
    JobError,
    JobId,
    JobItemFailure,
    JobState,
    JobStatus,
)
from mtee.services.jobs import JobContext, JobService


def _status(
    label: str,
    state: JobState,
    *,
    completed: int | None = None,
    total: int | None = None,
    failures: int = 0,
    error: JobError | None = None,
) -> JobStatus:
    items = tuple(
        JobItemFailure(f"file{index}.flac", "unreadable") for index in range(min(failures, 3))
    )
    return JobStatus(
        job_id=JobId.new(),
        label=label,
        state=state,
        completed=completed,
        total=total,
        failures=items,
        failure_total=failures,
        error=error,
        progress=1.0 if state is JobState.SUCCEEDED else 0.0,
    )


_PARTIAL = JobError(code="analysis_incomplete", message="Some tracks could not be analysed.")
_FAILED = JobError(code=ERROR_UNHANDLED, message="RuntimeError: disk is full")
_CANCELLED = JobError(code=ERROR_CANCELLED, message="Cancelled by the user.")


@pytest.mark.parametrize(
    ("summary", "label", "completed", "failures", "expected"),
    [
        (analysis_summary(), "Analyze collection", 123, 0, "123 songs analysed, 0 errors"),
        (analysis_summary(), "Analyze collection", 1, 1, "1 song analysed, 1 error"),
        (
            scan_summary("Music"),
            "Indexing Music",
            340,
            0,
            "Music scanned: 340 files read, 0 errors",
        ),
        (moved_summary(), "Move files to Jazz", 8, 0, "8 files moved, 0 errors"),
        (moved_summary(), "Move files to Jazz", 8, 2, "6 files moved, 2 errors"),
        (saved_summary(), "Save metadata", 5, 0, "5 files saved, 0 errors"),
        (
            recycled_summary(),
            "Move audio to Recycle Bin",
            1,
            0,
            "1 file moved to the Recycle Bin, 0 errors",
        ),
    ],
)
def test_a_succeeded_core_job_says_its_counts(
    summary, label: str, completed: int, failures: int, expected: str
) -> None:
    status = _status(label, JobState.SUCCEEDED, completed=completed, failures=failures)
    if failures:
        status = _status(
            label, JobState.FAILED, completed=completed, failures=failures, error=_PARTIAL
        )

    assert job_summary(status, summary) == expected


def test_a_partial_failure_keeps_the_counts_and_the_error_count() -> None:
    status = _status(
        "Analyze collection", JobState.FAILED, completed=120, failures=3, error=_PARTIAL
    )

    assert job_summary(status, analysis_summary()) == "120 songs analysed, 3 errors"


def test_a_failed_core_job_falls_back_to_its_error_sentence() -> None:
    status = _status("Move files to Jazz", JobState.FAILED, completed=None, error=_FAILED)

    assert job_summary(status, moved_summary()) == (
        "Move files to Jazz: failed (RuntimeError: disk is full)"
    )


def test_a_cancelled_core_job_says_it_was_cancelled() -> None:
    status = _status("Analyze collection", JobState.CANCELLED, completed=34)

    assert job_summary(status, analysis_summary()) == "Analyze collection: cancelled"


def test_a_count_is_only_written_when_the_job_counted() -> None:
    status = _status("Analyze collection", JobState.SUCCEEDED)

    assert job_summary(status, analysis_summary()) == "Analysis finished, 0 errors"


def test_a_summary_that_raises_falls_back_to_the_generic_sentence() -> None:
    def broken(_status: JobStatus) -> str:
        raise KeyError("completed")

    status = _status("Analyze collection", JobState.SUCCEEDED, completed=3)

    assert job_summary(status, broken) == "Analyze collection: done"


def test_a_job_without_summary_has_the_generic_sentences() -> None:
    assert job_summary(_status("Decode", JobState.SUCCEEDED), None) == "Decode: done"
    assert job_summary(_status("Decode", JobState.CANCELLED), None) == "Decode: cancelled"
    partial = _status("Decode", JobState.FAILED, total=120, failures=3, error=_PARTIAL)
    assert job_summary(partial, None) == "Decode: 3 of 120 failed"
    interrupted = _status(
        "Decode",
        JobState.FAILED,
        error=JobError(code=ERROR_INTERRUPTED, message="Stopped before completion."),
    )
    assert job_summary(interrupted, None) == "Decode: stopped before completion"


def test_fixed_and_recorded_sentences_only_speak_for_a_success() -> None:
    succeeded = _status("Plugin Hello", JobState.SUCCEEDED)
    failed = _status("Plugin Hello", JobState.FAILED, error=_FAILED)
    sentences: list[str] = ["Plugin Hello installed"]

    assert job_summary(succeeded, fixed("Plugin Hello installed")) == "Plugin Hello installed"
    assert job_summary(failed, fixed("Plugin Hello installed")).startswith("Plugin Hello: failed")
    assert job_summary(succeeded, recorded(sentences)) == "Plugin Hello installed"
    assert job_summary(failed, recorded(sentences)).startswith("Plugin Hello: failed")


def test_count_sentence_uses_the_singular_for_one() -> None:
    assert count_sentence(1, 0, one="song", many="songs", finished="Done") == "1 song, 0 errors"
    assert count_sentence(None, 1, one="song", many="songs", finished="Done") == "Done, 1 error"


def test_the_fallback_is_a_single_line_of_plain_words() -> None:
    status = _status(
        "Decode", JobState.FAILED, error=JobError(code="x", message="first line\nsecond")
    )

    assert fallback_summary(status) == "Decode: failed (first line)"


@pytest.fixture
def service(qapp) -> Iterator[JobService]:
    created = JobService(max_thread_count=2)
    yield created
    created.shutdown(2_000)


def _summary_of(qtbot, service: JobService, job_id: JobId) -> str:
    qtbot.waitUntil(lambda: bool(service.status(job_id).summary))
    return service.status(job_id).summary


def test_a_plugin_job_with_a_summary_writes_it(qtbot, service: JobService) -> None:
    def task(context: JobContext) -> None:
        context.report_items(1, 1, "Hello")

    job_id = service.submit(
        task,
        label="Install Hello",
        summary=lambda status: f"Plugin Hello installed ({status.completed})",
    )

    assert _summary_of(qtbot, service, job_id) == "Plugin Hello installed (1)"


def test_a_plugin_job_without_a_summary_gets_the_generic_one(qtbot, service: JobService) -> None:
    job_id = service.submit(lambda _context: None, label="Install Hello")

    assert _summary_of(qtbot, service, job_id) == "Install Hello: done"


def test_a_core_job_summary_is_written_on_the_graphical_thread(qtbot, service: JobService) -> None:
    seen: list[bool] = []

    import threading

    main = threading.current_thread()

    def summary(status: JobStatus) -> str:
        seen.append(threading.current_thread() is main)
        return "Done"

    def task(context: JobContext) -> None:
        context.report_items(2, 2, "x")

    job_id = service.submit(task, label="Scan", summary=summary)

    assert _summary_of(qtbot, service, job_id) == "Done"
    assert seen == [True]
