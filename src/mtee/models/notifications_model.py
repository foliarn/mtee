"""Session notifications: one row per visible job that ended.

The list lives in memory only (decision U20): a restart empties it. It is filled from the
``jobUpdated`` signal of ``JobService``, on the graphical thread, once a job reaches a terminal
state and its one-sentence summary is written. Hidden jobs never notify.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from mtee.domain.jobs import JobId, JobState, JobStatus
from mtee.services.jobs import JobService

__all__ = ["NotificationRole", "NotificationsModel", "tone_for_status"]

TONE_NEUTRAL = "neutral"
TONE_WARNING = "warning"


class NotificationRole:
    """Roles exposed to QML (``UserRole`` + offsets, after the jobs model roles)."""

    ID = int(Qt.ItemDataRole.UserRole) + 1
    JOB_ID = int(Qt.ItemDataRole.UserRole) + 2
    TITLE = int(Qt.ItemDataRole.UserRole) + 3
    TEXT = int(Qt.ItemDataRole.UserRole) + 4
    TONE = int(Qt.ItemDataRole.UserRole) + 5
    CREATED_AT = int(Qt.ItemDataRole.UserRole) + 6
    READ = int(Qt.ItemDataRole.UserRole) + 7


_ROLE_NAMES = {
    NotificationRole.ID: QByteArray(b"id"),
    NotificationRole.JOB_ID: QByteArray(b"jobId"),
    NotificationRole.TITLE: QByteArray(b"title"),
    NotificationRole.TEXT: QByteArray(b"text"),
    NotificationRole.TONE: QByteArray(b"tone"),
    NotificationRole.CREATED_AT: QByteArray(b"createdAt"),
    NotificationRole.READ: QByteArray(b"read"),
}

_ROW_KEYS = {
    NotificationRole.ID: "id",
    NotificationRole.JOB_ID: "jobId",
    NotificationRole.TITLE: "title",
    NotificationRole.TEXT: "text",
    NotificationRole.TONE: "tone",
    NotificationRole.CREATED_AT: "createdAt",
    NotificationRole.READ: "read",
}


def tone_for_status(status: JobStatus) -> str:
    """A failed job, partial failure included, is a warning; the rest is neutral."""
    return TONE_WARNING if status.state is JobState.FAILED else TONE_NEUTRAL


class NotificationsModel(QAbstractListModel):
    """The notifications of this session, newest first."""

    countsChanged = Signal()

    def __init__(
        self,
        service: JobService,
        parent: QObject | None = None,
        *,
        open_tasks: Callable[[str], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._open_tasks = open_tasks
        self._rows: list[dict[str, Any]] = []
        self._notified: set[JobId] = set()
        self._ids = itertools.count(1)
        service.jobUpdated.connect(self._on_job_updated)

    def set_open_tasks(self, open_tasks: Callable[[str], object] | None) -> None:
        """Bind the callable that opens the Tasks window on a job (the workspace's)."""
        self._open_tasks = open_tasks

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows)

    def roleNames(self) -> dict[int, QByteArray]:
        return dict(_ROLE_NAMES)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        if role == int(Qt.ItemDataRole.DisplayRole):
            return row["text"]
        key = _ROW_KEYS.get(role)
        return None if key is None else row[key]

    @Property(int, notify=countsChanged)
    def unreadCount(self) -> int:
        return sum(1 for row in self._rows if not row["read"])

    @Property(dict, notify=countsChanged)
    def latest(self) -> dict[str, Any]:
        """The newest notification (for the balloon), or an empty map."""
        if not self._rows:
            return {}
        return dict(self._rows[0])

    @Slot()
    def markAllRead(self) -> None:
        changed = False
        for row in self._rows:
            if not row["read"]:
                row["read"] = True
                changed = True
        if changed:
            self._emit_all(NotificationRole.READ)
            self.countsChanged.emit()

    @Slot()
    def clear(self) -> None:
        if not self._rows:
            return
        self.beginResetModel()
        self._rows = []
        self.endResetModel()
        self.countsChanged.emit()

    @Slot(str)
    def dismiss(self, notification_id: str) -> None:
        row = self._row_of(notification_id)
        if row is None:
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._rows[row]
        self.endRemoveRows()
        self.countsChanged.emit()

    @Slot(str)
    def openDetails(self, notification_id: str) -> None:
        """Mark the notification read and ask the workspace to open its task in the Tasks window."""
        row = self._row_of(notification_id)
        if row is None:
            return
        if not self._rows[row]["read"]:
            self._rows[row]["read"] = True
            self._emit_row(row, NotificationRole.READ)
            self.countsChanged.emit()
        if self._open_tasks is not None:
            self._open_tasks(str(self._rows[row]["jobId"]))

    def seed_demo(self) -> None:
        """Fill the list with a fixed set of sentences for the demo mode (no job behind them)."""
        now = time.time()
        self._add("Analyze collection", "123 songs analysed, 0 errors", TONE_NEUTRAL, "", now - 120)
        self._add("Move files to Jazz", "8 files moved, 0 errors", TONE_NEUTRAL, "", now - 60)
        self._add("Save metadata", "4 files saved, 1 error", TONE_WARNING, "", now - 10)

    def _on_job_updated(self, status: JobStatus) -> None:
        if not status.is_terminal or status.job_id in self._notified:
            return
        if not self._service.is_visible(status.job_id):
            return
        self._notified.add(status.job_id)
        self._add(
            status.label,
            status.summary or status.label,
            tone_for_status(status),
            str(status.job_id),
            time.time(),
        )

    def _add(self, title: str, text: str, tone: str, job_id: str, created_at: float) -> None:
        row: dict[str, Any] = {
            "id": str(next(self._ids)),
            "jobId": job_id,
            "title": title,
            "text": text,
            "tone": tone,
            "createdAt": created_at,
            "read": False,
        }
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._rows.insert(0, row)
        self.endInsertRows()
        self.countsChanged.emit()

    def _row_of(self, notification_id: str) -> int | None:
        for position, row in enumerate(self._rows):
            if row["id"] == notification_id:
                return position
        return None

    def _emit_row(self, row: int, role: int) -> None:
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [role])

    def _emit_all(self, role: int) -> None:
        if self._rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, 0), [role])
