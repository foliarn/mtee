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
    "JobState",
    "JobStatus",
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
class JobStatus:
    """Immutable snapshot of a job."""

    job_id: JobId
    label: str
    state: JobState = JobState.QUEUED
    progress: float = 0.0
    error: JobError | None = field(default=None)

    def __post_init__(self) -> None:
        if not 0.0 <= self.progress <= 1.0:
            raise ValueError("progress must stay between 0.0 and 1.0")
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


class JobCancelledError(Exception):
    """Raised inside a task when its cancellation has been requested."""
