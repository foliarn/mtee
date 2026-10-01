"""Background job vocabulary shared by the service, the models and the views."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "ERROR_CANCELLED",
    "ERROR_INTERRUPTED",
    "ERROR_UNHANDLED",
    "TERMINAL_STATES",
    "JobCancelledError",
    "JobError",
    "JobId",
    "JobItemFailure",
    "JobState",
    "JobStatus",
    "remaining_seconds",
]

ERROR_CANCELLED = "cancelled"
ERROR_INTERRUPTED = "interrupted"
ERROR_UNHANDLED = "unhandled_exception"


@dataclass(frozen=True, slots=True, order=True)
class JobId:
    """Identifier of a submitted job."""

    value: uuid.UUID

    @staticmethod
    def new() -> JobId:
        return JobId(uuid.uuid4())

    @staticmethod
    def parse(text: str) -> JobId:
        """Return the identifier written as ``text``; raises ``ValueError`` otherwise."""
        return JobId(uuid.UUID(str(text)))

    def __str__(self) -> str:
        return str(self.value)


class JobState(StrEnum):
    """Persisted state of a job.

    A job interrupted by a shutdown becomes ``FAILED`` with the error code
    ``interrupted``. Views may label that case ``Interrupted``; they do not
    create a second state model.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATES = frozenset({JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED})


@dataclass(frozen=True, slots=True)
class JobError:
    """Structured error carried by a failed job."""

    code: str
    message: str

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("an error code is required")


@dataclass(frozen=True, slots=True)
class JobItemFailure:
    """One element of a job that failed while the job went on."""

    name: str
    message: str


@dataclass(frozen=True, slots=True)
class JobStatus:
    """Immutable snapshot of a job.

    ``completed`` and ``total`` count the elements of a job that has several (files,
    tracks); both stay ``None`` when the job cannot tell. ``started_at`` and
    ``finished_at`` are epoch seconds. ``failures`` keeps the first failed elements;
    ``failure_total`` counts them all.
    """

    job_id: JobId
    label: str
    state: JobState = JobState.QUEUED
    progress: float = 0.0
    error: JobError | None = field(default=None)
    completed: int | None = None
    total: int | None = None
    detail: str = ""
    started_at: float | None = None
    finished_at: float | None = None
    failures: tuple[JobItemFailure, ...] = ()
    failure_total: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.progress <= 1.0:
            raise ValueError("progress must stay between 0.0 and 1.0")
        if self.total is not None and self.total < 0:
            raise ValueError("total cannot be negative")
        if self.completed is not None:
            if self.completed < 0:
                raise ValueError("completed cannot be negative")
            if self.total is not None and self.completed > self.total:
                raise ValueError("completed cannot exceed total")
        if self.state is JobState.FAILED and self.error is None:
            raise ValueError("a failed job must carry an error")
        if self.state is not JobState.FAILED and self.error is not None:
            raise ValueError("only a failed job carries an error")

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def is_interrupted(self) -> bool:
        """Return whether the job failed because MTEE stopped while it was running."""
        return self.error is not None and self.error.code == ERROR_INTERRUPTED


_ESTIMATE_AFTER_SECONDS = 3.0


def remaining_seconds(status: JobStatus, now: float) -> float | None:
    """Estimate the time left of a running job, or ``None`` when it cannot be told.

    The estimate extrapolates the average pace so far, from the element counter when
    the job has one and from the progress fraction otherwise. It stays silent during
    the first seconds, when a pace means nothing.
    """
    if status.state is not JobState.RUNNING or status.started_at is None:
        return None
    elapsed = now - status.started_at
    if elapsed < _ESTIMATE_AFTER_SECONDS:
        return None
    if status.completed and status.total:
        return elapsed / status.completed * (status.total - status.completed)
    if 0.0 < status.progress < 1.0:
        return elapsed / status.progress * (1.0 - status.progress)
    return None


class JobCancelledError(Exception):
    """Raised inside a task when its cancellation has been requested."""
