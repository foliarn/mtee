"""Background jobs.

``JobService`` keeps the long work out of the graphical thread. The registry of
states is guarded by a lock so a snapshot can be read from any thread, and the
Qt signals notify the models, which are updated on the graphical thread.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot

from mtee.domain.jobs import (
    ERROR_CANCELLED,
    ERROR_INTERRUPTED,
    ERROR_UNHANDLED,
    JobCancelledError,
    JobError,
    JobId,
    JobItemFailure,
    JobState,
    JobStatus,
)

__all__ = [
    "MAX_KEPT_FAILURES",
    "JobContext",
    "JobService",
    "JobTask",
    "UnknownJobError",
    "cancelled_error",
]

MAX_KEPT_FAILURES = 500


class UnknownJobError(LookupError):
    """Raised when a job identifier does not belong to this service."""


class JobContext:
    """Handle given to a running task to report progress and observe cancellation."""

    def __init__(self, job_id: JobId, service: JobService) -> None:
        self._job_id = job_id
        self._service = service
        self._cancelled = threading.Event()
        self._fine_progress = False

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
        self._fine_progress = True
        self._service.publish_progress(self._job_id, bounded)

    def report_items(self, completed: int, total: int | None, detail: str = "") -> None:
        """Publish how many elements are done, out of ``total`` when it is known.

        ``detail`` names the element being handled. The progress fraction follows the
        counter (``completed / total``) unless the task publishes its own finer
        progress with ``report_progress``, which then keeps the last word.
        """
        self._service.publish_items(
            self._job_id,
            max(0, int(completed)),
            total,
            detail,
            follow_counter=not self._fine_progress,
        )

    def report_detail(self, text: str) -> None:
        """Publish what the job is doing now, without a counter."""
        self._service.publish_items(self._job_id, None, None, text, follow_counter=False)

    def report_failure(self, name: str, message: str) -> None:
        """Record an element that failed while the job goes on."""
        self._service.publish_failure(self._job_id, JobItemFailure(name, message))

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
            code = getattr(error, "code", ERROR_UNHANDLED)
            if not isinstance(code, str) or not code:
                code = ERROR_UNHANDLED
            service.finish(
                job_id,
                JobState.FAILED,
                JobError(code=code, message=f"{type(error).__name__}: {error}"),
            )
        else:
            service.finish(job_id, JobState.SUCCEEDED, None)


class JobService(QObject):
    """Submits, follows and cancels the background work of the application."""

    jobSubmitted = Signal(object)
    jobUpdated = Signal(object)
    jobsCleared = Signal(object)
    _progressFlushRequested = Signal()

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
        self._pending_progress: set[JobId] = set()
        self._progress_flush_enqueued = False
        self._accepting = True
        self._progressFlushRequested.connect(
            self._schedule_progress_flush, Qt.ConnectionType.QueuedConnection
        )
        self._progress_timer = QTimer(self)
        self._progress_timer.setSingleShot(True)
        self._progress_timer.setInterval(100)
        self._progress_timer.timeout.connect(self._flush_progress)

    def submit(
        self,
        task: JobTask,
        *,
        label: str = "Background task",
        visible: bool = True,
        priority: int = 0,
        job_id: JobId | None = None,
    ) -> JobId:
        """Queue ``task`` and return its identifier."""
        job_id = job_id or JobId.new()
        context = JobContext(job_id, self)
        status = JobStatus(job_id=job_id, label=label, state=JobState.QUEUED)
        with self._lock:
            if not self._accepting:
                raise RuntimeError("The application is shutting down; no new jobs are accepted.")
            if job_id in self._statuses:
                raise ValueError(f"Job identifier is already registered: {job_id}")
            self._statuses[job_id] = status
            self._contexts[job_id] = context
            if not visible:
                self._hidden.add(job_id)
        self.jobSubmitted.emit(status)
        self._pool.start(_JobRunnable(self, context, task), priority)
        return job_id

    @property
    def accepting(self) -> bool:
        """Return whether new jobs are still accepted (false once shutdown has begun)."""
        with self._lock:
            return self._accepting

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
        self.begin_shutdown()
        self._pool.waitForDone(timeout_ms)
        interrupted: list[JobStatus] = []
        with self._lock:
            for job_id, status in list(self._statuses.items()):
                if status.is_terminal:
                    continue
                stopped = replace(
                    status,
                    finished_at=time.time(),
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

    def begin_shutdown(self) -> None:
        """Reject new jobs and request cancellation before native services close."""
        with self._lock:
            self._accepting = False
            contexts = list(self._contexts.values())
        for context in contexts:
            context.request_cancel()

    def start(self, job_id: JobId) -> bool:
        """Move a queued job to ``running``; return whether it may run.

        Called by the worker of the job, never by the interface.
        """
        with self._lock:
            status = self._statuses.get(job_id)
            if status is None or status.is_terminal:
                return False
            running = replace(status, state=JobState.RUNNING, started_at=time.time())
            self._statuses[job_id] = running
        self.jobUpdated.emit(running)
        return True

    def publish_progress(self, job_id: JobId, progress: float) -> None:
        """Keep the latest progress and coalesce UI notifications to 100 ms."""
        with self._lock:
            status = self._statuses.get(job_id)
            if status is None or status.is_terminal:
                return
            updated = replace(status, progress=progress)
            self._statuses[job_id] = updated
        self._request_flush(job_id)

    def _request_flush(self, job_id: JobId) -> None:
        request_flush = False
        with self._lock:
            self._pending_progress.add(job_id)
            if not self._progress_flush_enqueued:
                self._progress_flush_enqueued = True
                request_flush = True
        if request_flush:
            self._progressFlushRequested.emit()

    def publish_items(
        self,
        job_id: JobId,
        completed: int | None,
        total: int | None,
        detail: str,
        *,
        follow_counter: bool,
    ) -> None:
        """Keep the latest counter and detail; notifications are coalesced like progress."""
        with self._lock:
            status = self._statuses.get(job_id)
            if status is None or status.is_terminal:
                return
            changes: dict[str, object] = {"detail": detail}
            if completed is not None:
                known_total = total if total is not None else None
                if known_total is not None:
                    completed = min(completed, known_total)
                changes["completed"] = completed
                changes["total"] = known_total
                if follow_counter and known_total:
                    changes["progress"] = min(1.0, completed / known_total)
            self._statuses[job_id] = replace(status, **changes)  # type: ignore[arg-type]
        self._request_flush(job_id)

    def publish_failure(self, job_id: JobId, failure: JobItemFailure) -> None:
        """Record a failed element; only the first ``MAX_KEPT_FAILURES`` are kept."""
        with self._lock:
            status = self._statuses.get(job_id)
            if status is None or status.is_terminal:
                return
            kept = status.failures
            if len(kept) < MAX_KEPT_FAILURES:
                kept = (*kept, failure)
            self._statuses[job_id] = replace(
                status, failures=kept, failure_total=status.failure_total + 1
            )
        self._request_flush(job_id)

    def clear_finished(self) -> list[JobId]:
        """Forget the finished jobs of the user's list and report which ones went."""
        with self._lock:
            cleared = [
                job_id
                for job_id, status in self._statuses.items()
                if status.is_terminal and job_id not in self._hidden
            ]
            for job_id in cleared:
                del self._statuses[job_id]
        if cleared:
            self.jobsCleared.emit(cleared)
        return cleared

    def finish(self, job_id: JobId, state: JobState, error: JobError | None) -> None:
        """Record the terminal state reported by the worker of ``job_id``."""
        with self._lock:
            status = self._statuses.get(job_id)
            if status is None or status.is_terminal:
                return
            progress = 1.0 if state is JobState.SUCCEEDED else status.progress
            finished = replace(
                status, state=state, progress=progress, error=error, finished_at=time.time()
            )
            self._statuses[job_id] = finished
            self._contexts.pop(job_id, None)
            self._pending_progress.discard(job_id)
        self.jobUpdated.emit(finished)

    @Slot()
    def _schedule_progress_flush(self) -> None:
        if not self._progress_timer.isActive():
            self._progress_timer.start()

    @Slot()
    def _flush_progress(self) -> None:
        with self._lock:
            pending = tuple(self._pending_progress)
            self._pending_progress.clear()
            self._progress_flush_enqueued = False
            statuses = [
                self._statuses[job_id]
                for job_id in pending
                if job_id in self._statuses and not self._statuses[job_id].is_terminal
            ]
        for status in statuses:
            self.jobUpdated.emit(status)


def cancelled_error() -> JobError:
    """Return the structured error describing a cancellation, for the views."""
    return JobError(code=ERROR_CANCELLED, message="Cancelled by the user.")
