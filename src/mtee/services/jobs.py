"""Background jobs.

``JobService`` keeps the long work out of the graphical thread. The registry of
states is guarded by a lock so a snapshot can be read from any thread, and the
Qt signals notify the models, which are updated on the graphical thread.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from mtee.domain.jobs import (
    ERROR_CANCELLED,
    ERROR_INTERRUPTED,
    ERROR_UNHANDLED,
    JobCancelledError,
    JobError,
    JobId,
    JobState,
    JobStatus,
)

__all__ = ["JobContext", "JobService", "JobTask", "UnknownJobError", "cancelled_error"]


class UnknownJobError(LookupError):
    """Raised when a job identifier does not belong to this service."""


class JobContext:
    """Handle given to a running task to report progress and observe cancellation."""

    def __init__(self, job_id: JobId, service: JobService) -> None:
        self._job_id = job_id
        self._service = service
        self._cancelled = threading.Event()

    @property
    def job_id(self) -> JobId:
        return self._job_id

    @property
    def is_cancelled(self) -> bool:
        """Return whether a cancellation has been requested for this job."""
        return self._cancelled.is_set()

    def request_cancel(self) -> None:
        """Mark the job as cancelled; the task observes it at its next check."""
        self._cancelled.set()

    def raise_if_cancelled(self) -> None:
        """Raise ``JobCancelledError`` when the task must stop."""
        if self._cancelled.is_set():
            raise JobCancelledError(str(self._job_id))

    def report_progress(self, progress: float) -> None:
        """Publish a progress between 0.0 and 1.0; values outside are clamped."""
        bounded = min(1.0, max(0.0, float(progress)))
        self._service.publish_progress(self._job_id, bounded)

    def sleep(self, seconds: float, *, step_seconds: float = 0.05) -> None:
        """Wait while staying cancellable, for artificial or polling tasks."""
        remaining = max(0.0, float(seconds))
        while remaining > 0.0:
            if self._cancelled.wait(min(step_seconds, remaining)):
                raise JobCancelledError(str(self._job_id))
            remaining -= step_seconds


JobTask = Callable[[JobContext], None]


class _JobRunnable(QRunnable):
    """Runs one task in a worker thread of the pool."""

    def __init__(self, service: JobService, context: JobContext, task: JobTask) -> None:
        super().__init__()
        self._service = service
        self._context = context
        self._task = task
        self.setAutoDelete(True)

    def run(self) -> None:
        service = self._service
        job_id = self._context.job_id
        if self._context.is_cancelled:
            service.finish(job_id, JobState.CANCELLED, None)
            return
        if not service.start(job_id):
            return
        try:
            self._task(self._context)
        except JobCancelledError:
            service.finish(job_id, JobState.CANCELLED, None)
        except Exception as error:
            service.finish(
                job_id,
                JobState.FAILED,
                JobError(code=ERROR_UNHANDLED, message=f"{type(error).__name__}: {error}"),
            )
        else:
            service.finish(job_id, JobState.SUCCEEDED, None)


class JobService(QObject):
    """Submits, follows and cancels the background work of the application."""

    jobSubmitted = Signal(object)
    jobUpdated = Signal(object)

    def __init__(
        self, parent: QObject | None = None, *, max_thread_count: int | None = None
    ) -> None:
        super().__init__(parent)
        self._pool = QThreadPool()
        if max_thread_count is not None:
            self._pool.setMaxThreadCount(max_thread_count)
        self._lock = threading.RLock()
        self._statuses: dict[JobId, JobStatus] = {}
        self._contexts: dict[JobId, JobContext] = {}
        self._hidden: set[JobId] = set()

    def submit(
        self,
        task: JobTask,
        *,
        label: str = "Background task",
        visible: bool = True,
        priority: int = 0,
    ) -> JobId:
        """Queue ``task`` and return its identifier."""
        job_id = JobId.new()
        context = JobContext(job_id, self)
        status = JobStatus(job_id=job_id, label=label, state=JobState.QUEUED)
        with self._lock:
            self._statuses[job_id] = status
            self._contexts[job_id] = context
            if not visible:
                self._hidden.add(job_id)
        self.jobSubmitted.emit(status)
        self._pool.start(_JobRunnable(self, context, task), priority)
        return job_id

    def cancel(self, job_id: JobId) -> None:
        """Request the cancellation of ``job_id``.

        A queued job that never starts is reported as cancelled by its runnable;
        a running job stops at its next cancellation check.
        """
        with self._lock:
            context = self._contexts.get(job_id)
        if context is None:
            raise UnknownJobError(str(job_id))
        context.request_cancel()

    def status(self, job_id: JobId) -> JobStatus:
        """Return the current snapshot of ``job_id``."""
        with self._lock:
            status = self._statuses.get(job_id)
        if status is None:
            raise UnknownJobError(str(job_id))
        return status

    def is_visible(self, job_id: JobId) -> bool:
        """Return whether the status belongs in the user's task list."""
        with self._lock:
            return job_id not in self._hidden

    def statuses(self) -> list[JobStatus]:
        """Return a snapshot of user-visible jobs."""
        with self._lock:
            return [
                status for job_id, status in self._statuses.items() if job_id not in self._hidden
            ]

    def active_count(self) -> int:
        """Return how many jobs are neither finished nor cancelled."""
        with self._lock:
            return sum(1 for status in self._statuses.values() if not status.is_terminal)

    def wait_for_done(self, timeout_ms: int = 30_000) -> bool:
        """Wait for the pool to drain; return whether it emptied in time."""
        return self._pool.waitForDone(timeout_ms)

    def shutdown(self, timeout_ms: int = 5_000) -> list[JobStatus]:
        """Cancel every unfinished job, wait, then report what stayed incomplete.

        A job still running when the deadline expires is recorded as ``failed``
        with the code ``interrupted``; no incomplete work is left invisible and
        no success is invented.
        """
        with self._lock:
            contexts = list(self._contexts.values())
        for context in contexts:
            context.request_cancel()
        self._pool.waitForDone(timeout_ms)
        interrupted: list[JobStatus] = []
        with self._lock:
            for job_id, status in list(self._statuses.items()):
                if status.is_terminal:
                    continue
                stopped = replace(
                    status,
                    state=JobState.FAILED,
                    error=JobError(
                        code=ERROR_INTERRUPTED,
                        message="Stopped before completion while MTEE was closing.",
                    ),
                )
                self._statuses[job_id] = stopped
                interrupted.append(stopped)
        for status in interrupted:
            self.jobUpdated.emit(status)
        return interrupted

    def start(self, job_id: JobId) -> bool:
        """Move a queued job to ``running``; return whether it may run.

        Called by the worker of the job, never by the interface.
        """
        with self._lock:
            status = self._statuses.get(job_id)
            if status is None or status.is_terminal:
                return False
            running = replace(status, state=JobState.RUNNING)
            self._statuses[job_id] = running
        self.jobUpdated.emit(running)
        return True

    def publish_progress(self, job_id: JobId, progress: float) -> None:
        """Record the progress reported by the worker of ``job_id``."""
        with self._lock:
            status = self._statuses.get(job_id)
            if status is None or status.is_terminal:
                return
            updated = replace(status, progress=progress)
            self._statuses[job_id] = updated
        self.jobUpdated.emit(updated)

    def finish(self, job_id: JobId, state: JobState, error: JobError | None) -> None:
        """Record the terminal state reported by the worker of ``job_id``."""
        with self._lock:
            status = self._statuses.get(job_id)
            if status is None or status.is_terminal:
                return
            progress = 1.0 if state is JobState.SUCCEEDED else status.progress
            finished = replace(status, state=state, progress=progress, error=error)
            self._statuses[job_id] = finished
            self._contexts.pop(job_id, None)
        self.jobUpdated.emit(finished)


def cancelled_error() -> JobError:
    """Return the structured error describing a cancellation, for the views."""
    return JobError(code=ERROR_CANCELLED, message="Cancelled by the user.")
