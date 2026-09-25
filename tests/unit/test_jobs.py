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

    job_id = service.submit(task, label="Long analysis")
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
