"""List model of the background jobs.

The model carries the visible roles only. It is filled from the signals of
``JobService``, which Qt delivers on the graphical thread, and it never starts
nor writes anything by itself.
"""

from __future__ import annotations

import time
from enum import IntEnum

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QTimer,
    Signal,
    Slot,
)

from mtee.domain.jobs import JobId, JobState, JobStatus, remaining_seconds
from mtee.services.jobs import JobService, UnknownJobError
from mtee.services.platform.shell_reveal import WindowsShellReveal

__all__ = ["JobRole", "JobsListModel", "label_for_status", "outcome_for_status"]


class JobRole(IntEnum):
    """Roles exposed to QML."""

    JOB_ID = int(Qt.ItemDataRole.UserRole) + 1
    LABEL = int(Qt.ItemDataRole.UserRole) + 2
    STATE = int(Qt.ItemDataRole.UserRole) + 3
    STATE_LABEL = int(Qt.ItemDataRole.UserRole) + 4
    PROGRESS = int(Qt.ItemDataRole.UserRole) + 5
    ERROR_CODE = int(Qt.ItemDataRole.UserRole) + 6
    ERROR_MESSAGE = int(Qt.ItemDataRole.UserRole) + 7
    COMPLETED = int(Qt.ItemDataRole.UserRole) + 8
    TOTAL = int(Qt.ItemDataRole.UserRole) + 9
    DETAIL = int(Qt.ItemDataRole.UserRole) + 10
    STARTED_AT = int(Qt.ItemDataRole.UserRole) + 11
    FINISHED_AT = int(Qt.ItemDataRole.UserRole) + 12
    ELAPSED_SECONDS = int(Qt.ItemDataRole.UserRole) + 13
    REMAINING_SECONDS = int(Qt.ItemDataRole.UserRole) + 14
    FAILURES = int(Qt.ItemDataRole.UserRole) + 15
    FAILURE_COUNT = int(Qt.ItemDataRole.UserRole) + 16
    CAN_CANCEL = int(Qt.ItemDataRole.UserRole) + 17
    FINISHED_RANK = int(Qt.ItemDataRole.UserRole) + 18
    OUTCOME = int(Qt.ItemDataRole.UserRole) + 19
    GROUP = int(Qt.ItemDataRole.UserRole) + 20
    SUMMARY = int(Qt.ItemDataRole.UserRole) + 21


_STATE_LABELS = {
    JobState.QUEUED: "Queued",
    JobState.RUNNING: "Running",
    JobState.SUCCEEDED: "Succeeded",
    JobState.FAILED: "Failed",
    JobState.CANCELLED: "Cancelled",
}


def label_for_status(status: JobStatus) -> str:
    """Return the label shown for ``status``.

    A job interrupted by a shutdown keeps the ``failed`` state and is shown as
    ``Interrupted``; the visual label does not create a second state model.
    """
    if status.is_interrupted:
        return "Interrupted"
    if status.is_partial:
        return "Completed with errors"
    return _STATE_LABELS[status.state]


def outcome_for_status(status: JobStatus) -> str:
    """Return the outcome that colours and words a job: ``partial`` is not ``failed``."""
    if status.is_interrupted:
        return "interrupted"
    if status.is_partial:
        return "partial"
    return status.state.value


# A job that just succeeded stays with the running ones for a few seconds, so the
# user sees it complete, then settles into the finished list.
SETTLE_SECONDS = 6.0


class JobsListModel(QAbstractListModel):
    """Shows the jobs of a ``JobService``, newest first."""

    runningCountChanged = Signal()
    countsChanged = Signal()

    def __init__(self, service: JobService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._statuses: list[JobStatus] = []
        self._rows_by_id: dict[JobId, int] = {}
        service.jobSubmitted.connect(self._on_job_submitted)
        service.jobUpdated.connect(self._on_job_updated)
        service.jobsCleared.connect(self._on_jobs_cleared)
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.timeout.connect(self._regroup)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._statuses)

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            int(JobRole.JOB_ID): QByteArray(b"jobId"),
            int(JobRole.LABEL): QByteArray(b"label"),
            int(JobRole.STATE): QByteArray(b"jobState"),
            int(JobRole.STATE_LABEL): QByteArray(b"stateLabel"),
            int(JobRole.PROGRESS): QByteArray(b"progress"),
            int(JobRole.ERROR_CODE): QByteArray(b"errorCode"),
            int(JobRole.ERROR_MESSAGE): QByteArray(b"errorMessage"),
            int(JobRole.COMPLETED): QByteArray(b"completed"),
            int(JobRole.TOTAL): QByteArray(b"total"),
            int(JobRole.DETAIL): QByteArray(b"detail"),
            int(JobRole.STARTED_AT): QByteArray(b"startedAt"),
            int(JobRole.FINISHED_AT): QByteArray(b"finishedAt"),
            int(JobRole.ELAPSED_SECONDS): QByteArray(b"elapsedSeconds"),
            int(JobRole.REMAINING_SECONDS): QByteArray(b"remainingSeconds"),
            int(JobRole.FAILURES): QByteArray(b"failures"),
            int(JobRole.FAILURE_COUNT): QByteArray(b"failureCount"),
            int(JobRole.CAN_CANCEL): QByteArray(b"canCancel"),
            int(JobRole.FINISHED_RANK): QByteArray(b"finishedRank"),
            int(JobRole.OUTCOME): QByteArray(b"outcome"),
            int(JobRole.GROUP): QByteArray(b"group"),
            int(JobRole.SUMMARY): QByteArray(b"summary"),
        }

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ):
        if not index.isValid() or not 0 <= index.row() < len(self._statuses):
            return None
        status = self._statuses[index.row()]
        match role:
            case JobRole.JOB_ID:
                return str(status.job_id)
            case JobRole.LABEL | Qt.ItemDataRole.DisplayRole:
                return status.label
            case JobRole.STATE:
                return status.state.value
            case JobRole.STATE_LABEL:
                return label_for_status(status)
            case JobRole.PROGRESS:
                return status.progress
            case JobRole.ERROR_CODE:
                return status.error.code if status.error else ""
            case JobRole.ERROR_MESSAGE:
                return status.error.message if status.error else ""
            case JobRole.COMPLETED:
                return -1 if status.completed is None else status.completed
            case JobRole.TOTAL:
                return -1 if status.total is None else status.total
            case JobRole.DETAIL:
                return status.detail
            case JobRole.STARTED_AT:
                return status.started_at or 0.0
            case JobRole.FINISHED_AT:
                return status.finished_at or 0.0
            case JobRole.ELAPSED_SECONDS:
                return _elapsed(status)
            case JobRole.REMAINING_SECONDS:
                left = remaining_seconds(status, time.time())
                return -1.0 if left is None else left
            case JobRole.FAILURES:
                return [{"name": item.name, "message": item.message} for item in status.failures]
            case JobRole.FAILURE_COUNT:
                return max(status.failure_total, len(status.failures))
            case JobRole.CAN_CANCEL:
                return status.state in (JobState.QUEUED, JobState.RUNNING)
            case JobRole.FINISHED_RANK:
                if not status.is_terminal:
                    return -1
                return sum(item.is_terminal for item in self._statuses[: index.row()])
            case JobRole.OUTCOME:
                return outcome_for_status(status)
            case JobRole.GROUP:
                return _group(status, time.time())
            case JobRole.SUMMARY:
                return status.summary
            case _:
                return None

    def status_at(self, row: int) -> JobStatus:
        """Return the snapshot shown at ``row``."""
        return self._statuses[row]

    @Property(int, notify=runningCountChanged)
    def runningCount(self) -> int:
        return sum(status.state is JobState.RUNNING for status in self._statuses)

    @Property(int, notify=countsChanged)
    def activeCount(self) -> int:
        return sum(not status.is_terminal for status in self._statuses)

    @Property(int, notify=countsChanged)
    def finishedCount(self) -> int:
        return sum(status.is_terminal for status in self._statuses)

    @Property(int, notify=countsChanged)
    def liveCount(self) -> int:
        """Jobs shown with the running ones: unfinished, or succeeded a moment ago."""
        return self._count_group("live")

    @Property(int, notify=countsChanged)
    def attentionCount(self) -> int:
        """Finished jobs that failed, wholly or in part."""
        return self._count_group("attention")

    @Property(int, notify=countsChanged)
    def settledCount(self) -> int:
        """Finished jobs that went well or were cancelled, past the settle delay."""
        return self._count_group("done")

    def _count_group(self, group: str) -> int:
        now = time.time()
        return sum(_group(status, now) == group for status in self._statuses)

    @Slot(result=list)
    def runningJobs(self) -> list[dict[str, object]]:
        """The jobs that run now, most recently started first, as the header strip reads them.

        Each entry carries the keys the task rows use (``jobId``, ``label``, ``progress``,
        ``completed``, ``total``, ``detail``, ``elapsedSeconds``, ``remainingSeconds``,
        ``canCancel``, ...); a missing count is ``-1``.
        """
        now = time.time()
        running = [status for status in self._statuses if status.state is JobState.RUNNING]
        running.sort(key=lambda status: status.started_at or 0.0, reverse=True)
        return [
            {
                "jobId": str(status.job_id),
                "label": status.label,
                "jobState": status.state.value,
                "outcome": outcome_for_status(status),
                "stateLabel": label_for_status(status),
                "progress": status.progress,
                "completed": -1 if status.completed is None else status.completed,
                "total": -1 if status.total is None else status.total,
                "detail": status.detail,
                "elapsedSeconds": _elapsed(status),
                "remainingSeconds": _remaining_or_minus_one(status, now),
                "errorMessage": "",
                "failureCount": 0,
                "failures": [],
                "canCancel": True,
            }
            for status in running
        ]

    @Slot(result=list)
    def taskList(self) -> list[dict[str, object]]:
        """The session tasks of the Tasks window: unfinished first (latest start first), then the
        finished ones, newest first. Each row is the task dictionary of ``taskDetail``."""
        now = time.time()
        active = [status for status in self._statuses if not status.is_terminal]
        active.sort(key=lambda status: status.started_at or 0.0, reverse=True)
        finished = [status for status in self._statuses if status.is_terminal]
        return [_task_dict(status, now) for status in [*active, *finished]]

    @Slot(str, result=dict)
    def taskDetail(self, job_id: str) -> dict[str, object]:
        """The full record of one session task, or an empty map when it is gone."""
        parsed = _parse_job_id(job_id)
        row = self._rows_by_id.get(parsed) if parsed is not None else None
        if row is None:
            return {}
        return _task_dict(self._statuses[row], time.time())

    @Slot(str)
    def showInFolder(self, path: str) -> None:
        """Select a failed item's file in Explorer when its name is an existing file path."""
        try:
            WindowsShellReveal().reveal(path)
        except (OSError, ValueError):
            return

    @Slot(str)
    def cancel(self, job_id: str) -> None:
        """Ask a queued or running job to stop; a job that is already gone is ignored."""
        try:
            self._service.cancel(JobId.parse(job_id))
        except (UnknownJobError, ValueError):
            return

    @Slot()
    def clearFinished(self) -> None:
        self._service.clear_finished()

    def _on_job_submitted(self, status: JobStatus) -> None:
        if not self._service.is_visible(status.job_id):
            return
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._statuses.insert(0, status)
        self._reindex()
        self.endInsertRows()
        self._sync_clock()
        self.countsChanged.emit()

    def _on_jobs_cleared(self, job_ids: object) -> None:
        gone = set(job_ids) if isinstance(job_ids, list) else set()
        for row in sorted(
            (self._rows_by_id[i] for i in gone if i in self._rows_by_id), reverse=True
        ):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._statuses[row]
            self._reindex()
            self.endRemoveRows()
        self._sync_clock()
        self.countsChanged.emit()

    def _tick(self) -> None:
        roles = [int(JobRole.ELAPSED_SECONDS), int(JobRole.REMAINING_SECONDS)]
        for row, status in enumerate(self._statuses):
            if not status.is_terminal:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, roles)

    def _sync_clock(self) -> None:
        if any(not status.is_terminal for status in self._statuses):
            if not self._clock.isActive():
                self._clock.start()
        else:
            self._clock.stop()

    def _on_job_updated(self, status: JobStatus) -> None:
        if not self._service.is_visible(status.job_id):
            return
        row = self._rows_by_id.get(status.job_id)
        if row is None:
            self._on_job_submitted(status)
            return
        was_running = self._statuses[row].state is JobState.RUNNING
        was_terminal = self._statuses[row].is_terminal
        self._statuses[row] = status
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, list(self.roleNames().keys()))
        if was_running != (status.state is JobState.RUNNING):
            self.runningCountChanged.emit()
        if was_terminal != status.is_terminal or was_running != (status.state is JobState.RUNNING):
            self._sync_clock()
            if status.state is JobState.SUCCEEDED:
                self._settle.start(int((SETTLE_SECONDS + 0.1) * 1000))
            self.countsChanged.emit()

    def _regroup(self) -> None:
        """Move the jobs whose settle delay is over from the live list to the finished one."""
        if self._statuses:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._statuses) - 1, 0), [int(JobRole.GROUP)]
            )
        self.countsChanged.emit()

    def _reindex(self) -> None:
        self._rows_by_id = {status.job_id: row for row, status in enumerate(self._statuses)}


def _group(status: JobStatus, now: float) -> str:
    if not status.is_terminal:
        return "live"
    if status.state is JobState.FAILED:
        return "attention"
    if (
        status.state is JobState.SUCCEEDED
        and status.finished_at is not None
        and now - status.finished_at < SETTLE_SECONDS
    ):
        return "live"
    return "done"


def _remaining_or_minus_one(status: JobStatus, now: float) -> float:
    left = remaining_seconds(status, now)
    return -1.0 if left is None else left


def _elapsed(status: JobStatus) -> float:
    if status.started_at is None:
        return 0.0
    end = status.finished_at if status.finished_at is not None else time.time()
    return max(0.0, end - status.started_at)


def _parse_job_id(job_id: str) -> JobId | None:
    try:
        return JobId.parse(job_id)
    except ValueError:
        return None


def _task_dict(status: JobStatus, now: float) -> dict[str, object]:
    """One task of the Tasks window: the keys the task rows and the record read."""
    outcome = outcome_for_status(status)
    if not status.is_terminal:
        tone = "primary"
    elif outcome in ("partial", "failed", "interrupted"):
        tone = "warning"
    else:
        tone = "neutral"
    return {
        "jobId": str(status.job_id),
        "label": status.label,
        "title": status.label,
        "subtitle": status.summary or status.detail,
        "tag": label_for_status(status),
        "tagTone": tone,
        "jobState": status.state.value,
        "outcome": outcome,
        "stateLabel": label_for_status(status),
        "progress": status.progress,
        "completed": -1 if status.completed is None else status.completed,
        "total": -1 if status.total is None else status.total,
        "detail": status.detail,
        "summary": status.summary,
        "startedAt": status.started_at or 0.0,
        "finishedAt": status.finished_at or 0.0,
        "elapsedSeconds": _elapsed(status),
        "remainingSeconds": _remaining_or_minus_one(status, now),
        "errorMessage": status.error.message if status.error else "",
        "failures": [{"name": item.name, "message": item.message} for item in status.failures],
        "failureCount": max(status.failure_total, len(status.failures)),
        "canCancel": status.state in (JobState.QUEUED, JobState.RUNNING),
    }
