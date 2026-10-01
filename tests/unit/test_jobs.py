"""Behaviour of the background jobs: progress, failure, cancellation, shutdown."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest

from mtee.domain.jobs import ERROR_INTERRUPTED, ERROR_UNHANDLED, JobId, JobState
from mtee.models.jobs_model import JobsListModel, label_for_status
from mtee.services.jobs import JobContext, JobService, UnknownJobError

_DEADLINE_SECONDS = 10.0


@pytest.fixture
def service(qapp) -> Iterator[JobService]:
    created = JobService(max_thread_count=4)
    yield created
    created.shutdown(2_000)


def _wait_until(condition, timeout: float = _DEADLINE_SECONDS) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_a_finished_task_reports_a_full_progress(service: JobService) -> None:
    def task(context: JobContext) -> None:
        context.report_progress(0.5)

    job_id = service.submit(task, label="Read tags")

    assert _wait_until(lambda: service.status(job_id).is_terminal)
    status = service.status(job_id)
    assert status.state is JobState.SUCCEEDED
    assert status.progress == 1.0
    assert status.error is None


def test_an_internal_background_job_is_not_shown_in_the_tasks_list(
    service: JobService,
) -> None:
    model = JobsListModel(service)
    job_id = service.submit(lambda _context: None, label="Routine catalog check", visible=False)

    assert _wait_until(lambda: service.status(job_id).is_terminal)
    assert service.status(job_id).state is JobState.SUCCEEDED
    assert service.statuses() == []
    assert model.rowCount() == 0


def test_a_failing_task_carries_a_structured_error_and_does_not_stay_running(
    service: JobService,
) -> None:
    def task(context: JobContext) -> None:
        raise RuntimeError("codec not understood")

    job_id = service.submit(task, label="Decode")

    assert _wait_until(lambda: service.status(job_id).is_terminal)
    status = service.status(job_id)
    assert status.state is JobState.FAILED
    assert status.error is not None
    assert status.error.code == ERROR_UNHANDLED
    assert "codec not understood" in status.error.message
    assert label_for_status(status) == "Failed"


def test_a_running_task_observes_its_cancellation(service: JobService) -> None:
    started = threading.Event()

    def task(context: JobContext) -> None:
        started.set()
        context.sleep(30.0)

    job_id = service.submit(task, label="Long waveform")
    assert started.wait(_DEADLINE_SECONDS)

    service.cancel(job_id)

    assert _wait_until(lambda: service.status(job_id).is_terminal)
    assert service.status(job_id).state is JobState.CANCELLED


def test_a_job_cancelled_before_it_starts_never_runs(service: JobService) -> None:
    blocker = threading.Event()
    ran = threading.Event()
    single = JobService(max_thread_count=1)

    def occupy(context: JobContext) -> None:
        blocker.wait(_DEADLINE_SECONDS)

    def never_runs(context: JobContext) -> None:
        ran.set()

    try:
        single.submit(occupy, label="Occupy")
        queued = single.submit(never_runs, label="Queued")

        single.cancel(queued)
        blocker.set()

        assert _wait_until(lambda: single.status(queued).is_terminal)
        assert single.status(queued).state is JobState.CANCELLED
        assert not ran.is_set()
    finally:
        blocker.set()
        single.shutdown(2_000)


def test_progress_stays_between_zero_and_one(service: JobService) -> None:
    seen: list[float] = []

    def task(context: JobContext) -> None:
        context.report_progress(-3.0)
        seen.append(service.status(context.job_id).progress)
        context.report_progress(7.0)
        seen.append(service.status(context.job_id).progress)

    job_id = service.submit(task, label="Bounded")

    assert _wait_until(lambda: service.status(job_id).is_terminal)
    assert seen == [0.0, 1.0]


def test_shutdown_marks_an_unfinished_job_as_interrupted() -> None:
    stubborn = JobService(max_thread_count=1)
    started = threading.Event()

    def task(context: JobContext) -> None:
        started.set()
        time.sleep(1.5)

    job_id = stubborn.submit(task, label="Stubborn scan")
    assert started.wait(_DEADLINE_SECONDS)

    interrupted = stubborn.shutdown(timeout_ms=50)

    assert [status.job_id for status in interrupted] == [job_id]
    status = stubborn.status(job_id)
    assert status.state is JobState.FAILED
    assert status.error is not None
    assert status.error.code == ERROR_INTERRUPTED
    assert label_for_status(status) == "Interrupted"
    stubborn.wait_for_done(5_000)


def test_an_unknown_job_is_reported_and_not_invented(service: JobService) -> None:
    with pytest.raises(UnknownJobError):
        service.status(JobId.new())
    with pytest.raises(UnknownJobError):
        service.cancel(JobId.new())


def test_the_model_shows_the_submitted_jobs(qtbot, service: JobService) -> None:
    model = JobsListModel(service)

    def nothing(context: JobContext) -> None:
        return None

    with qtbot.waitSignal(service.jobSubmitted, timeout=2_000):
        job_id = service.submit(nothing, label="Visible task")

    assert model.rowCount() == 1
    assert model.status_at(0).job_id == job_id
    assert _wait_until(lambda: service.status(job_id).is_terminal)


def test_status_validates_counters() -> None:
    from mtee.domain.jobs import JobStatus

    job_id = JobId.new()
    with pytest.raises(ValueError, match="exceed"):
        JobStatus(job_id, "x", completed=3, total=2)
    with pytest.raises(ValueError, match="negative"):
        JobStatus(job_id, "x", total=-1)
    with pytest.raises(ValueError, match="negative"):
        JobStatus(job_id, "x", completed=-1)
    assert JobStatus(job_id, "x", completed=2).total is None


def test_remaining_seconds_follows_the_counter_then_the_fraction() -> None:
    from dataclasses import replace

    from mtee.domain.jobs import JobStatus, remaining_seconds

    base = JobStatus(JobId.new(), "x", state=JobState.RUNNING, started_at=1_000.0)

    assert remaining_seconds(replace(base, completed=10, total=40), 1_020.0) == pytest.approx(60.0)
    assert remaining_seconds(replace(base, progress=0.25), 1_020.0) == pytest.approx(60.0)
    # too early, nothing to extrapolate, not running, never started
    assert remaining_seconds(replace(base, completed=1, total=40), 1_002.0) is None
    assert remaining_seconds(base, 1_020.0) is None
    assert remaining_seconds(replace(base, state=JobState.QUEUED, progress=0.5), 1_020.0) is None
    assert remaining_seconds(replace(base, started_at=None, progress=0.5), 1_020.0) is None
    assert remaining_seconds(replace(base, completed=0, total=40), 1_020.0) is None


def test_items_detail_and_failures_are_published_with_timestamps(service: JobService) -> None:
    gate = threading.Event()

    def task(context: JobContext) -> None:
        context.report_items(2, 4, "b.flac")
        context.report_failure("a.flac", "could not decode")
        gate.wait(5)

    job_id = service.submit(task, label="Analyze")
    assert _wait_until(lambda: service.status(job_id).failure_total == 1)
    status = service.status(job_id)
    assert (status.completed, status.total, status.detail) == (2, 4, "b.flac")
    assert status.progress == pytest.approx(0.5)
    assert status.started_at is not None and status.finished_at is None
    assert status.failures[0].name == "a.flac"
    gate.set()
    assert _wait_until(lambda: service.status(job_id).is_terminal)
    assert service.status(job_id).finished_at is not None


def test_the_counter_does_not_override_a_finer_progress(service: JobService) -> None:
    gate = threading.Event()

    def task(context: JobContext) -> None:
        context.report_progress(0.3)
        context.report_items(3, 4, "c")
        gate.wait(5)

    job_id = service.submit(task, label="Mixed")
    assert _wait_until(lambda: service.status(job_id).completed == 3)
    status = service.status(job_id)
    assert status.progress == pytest.approx(0.3)  # the finer progress keeps the last word
    gate.set()
    assert _wait_until(lambda: service.status(job_id).is_terminal)


def test_failures_are_capped_but_counted(service: JobService) -> None:
    from mtee.services.jobs import MAX_KEPT_FAILURES

    def task(context: JobContext) -> None:
        for index in range(MAX_KEPT_FAILURES + 20):
            context.report_failure(f"f{index}", "bad")

    job_id = service.submit(task, label="Many")
    assert _wait_until(lambda: service.status(job_id).is_terminal)
    status = service.status(job_id)
    assert len(status.failures) == MAX_KEPT_FAILURES
    assert status.failure_total == MAX_KEPT_FAILURES + 20


def test_clear_finished_forgets_terminal_jobs_only(qtbot, service: JobService) -> None:
    model = JobsListModel(service)
    gate = threading.Event()
    done = service.submit(lambda _context: None, label="Done")
    running = service.submit(lambda _context: gate.wait(5), label="Running")
    assert _wait_until(lambda: service.status(done).is_terminal)
    assert _wait_until(lambda: service.status(running).state is JobState.RUNNING)
    qtbot.waitUntil(lambda: model.finishedCount == 1 and model.activeCount == 1, timeout=2_000)

    cleared = service.clear_finished()

    assert cleared == [done]
    assert model.rowCount() == 1
    assert model.status_at(0).job_id == running
    assert model.finishedCount == 0 and model.activeCount == 1
    with pytest.raises(UnknownJobError):
        service.status(done)
    gate.set()


def test_the_model_exposes_counters_cancel_and_failures(qtbot, service: JobService) -> None:
    from mtee.models.jobs_model import JobRole

    model = JobsListModel(service)
    gate = threading.Event()

    def task(context: JobContext) -> None:
        context.report_items(5, 10, "five.wav")
        context.report_failure("one.wav", "unreadable")
        gate.wait(5)

    job_id = service.submit(task, label="Analyze")
    assert _wait_until(lambda: service.status(job_id).failure_total == 1)
    qtbot.waitUntil(lambda: model.status_at(0).failure_total == 1, timeout=2_000)
    index = model.index(0, 0)

    assert model.data(index, int(JobRole.COMPLETED)) == 5
    assert model.data(index, int(JobRole.TOTAL)) == 10
    assert model.data(index, int(JobRole.DETAIL)) == "five.wav"
    assert model.data(index, int(JobRole.FAILURE_COUNT)) == 1
    assert model.data(index, int(JobRole.FAILURES)) == [
        {"name": "one.wav", "message": "unreadable"}
    ]
    assert model.data(index, int(JobRole.CAN_CANCEL)) is True
    assert model.data(index, int(JobRole.REMAINING_SECONDS)) == -1.0
    assert model.data(index, int(JobRole.ELAPSED_SECONDS)) >= 0.0

    model.cancel(str(job_id))
    model.cancel("not-a-job")  # an unknown or malformed id is ignored
    gate.set()
    assert _wait_until(lambda: service.status(job_id).is_terminal)
    qtbot.waitUntil(lambda: model.status_at(0).is_terminal, timeout=2_000)
    assert model.data(index, int(JobRole.CAN_CANCEL)) is False
    assert model.data(index, int(JobRole.FINISHED_RANK)) == 0
    model.clearFinished()
    assert model.rowCount() == 0
