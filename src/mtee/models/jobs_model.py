"""List model of the background jobs.

The model carries the visible roles only. It is filled from the signals of
``JobService``, which Qt delivers on the graphical thread, and it never starts
nor writes anything by itself.
"""

from __future__ import annotations

from enum import IntEnum

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from mtee.domain.jobs import JobId, JobState, JobStatus
from mtee.services.jobs import JobService

__all__ = ["JobRole", "JobsListModel", "label_for_status"]


class JobRole(IntEnum):
    """Roles exposed to QML."""

    JOB_ID = int(Qt.ItemDataRole.UserRole) + 1
    LABEL = int(Qt.ItemDataRole.UserRole) + 2
    STATE = int(Qt.ItemDataRole.UserRole) + 3
    STATE_LABEL = int(Qt.ItemDataRole.UserRole) + 4
    PROGRESS = int(Qt.ItemDataRole.UserRole) + 5
    ERROR_CODE = int(Qt.ItemDataRole.UserRole) + 6
    ERROR_MESSAGE = int(Qt.ItemDataRole.UserRole) + 7


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
    return _STATE_LABELS[status.state]


class JobsListModel(QAbstractListModel):
    """Shows the jobs of a ``JobService``, newest first."""

    def __init__(self, service: JobService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._statuses: list[JobStatus] = []
        self._rows_by_id: dict[JobId, int] = {}
        service.jobSubmitted.connect(self._on_job_submitted)
        service.jobUpdated.connect(self._on_job_updated)

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
            case _:
                return None

    def status_at(self, row: int) -> JobStatus:
        """Return the snapshot shown at ``row``."""
        return self._statuses[row]

    def _on_job_submitted(self, status: JobStatus) -> None:
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._statuses.insert(0, status)
        self._reindex()
        self.endInsertRows()

    def _on_job_updated(self, status: JobStatus) -> None:
        row = self._rows_by_id.get(status.job_id)
        if row is None:
            self._on_job_submitted(status)
            return
        self._statuses[row] = status
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, list(self.roleNames().keys()))

    def _reindex(self) -> None:
        self._rows_by_id = {status.job_id: row for row, status in enumerate(self._statuses)}
