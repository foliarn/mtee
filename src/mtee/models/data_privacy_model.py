"""Qt model of the Data & privacy page: backup, scheduled restore and statistics reset.

File choices arrive as local file URLs from the QML file dialogs; QML never opens
the files. Backup, validation and reset run as background jobs. The restore itself
is applied at the next start (see ``mtee.services.data_privacy``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from mtee.persistence.database import Database
from mtee.persistence.play_log_repository import PlayLogRepository
from mtee.services.data_privacy import (
    BackupValidationError,
    RestoreLayout,
    back_up_database,
    cancel_pending_restore,
    default_backup_name,
    read_pending_restore,
    reset_statistics,
    stage_restore,
)
from mtee.services.jobs import JobContext, JobService

__all__ = ["DataPrivacyModel"]


class DataPrivacyModel(QObject):
    """Expose the backup, restore and reset actions and their last outcome."""

    changed = Signal()
    noticeRaised = Signal(str)
    finished = Signal(str)
    _taskDone = Signal(str, str)

    def __init__(
        self,
        database: Database,
        layout: RestoreLayout,
        play_log: PlayLogRepository,
        jobs: JobService,
        parent: QObject | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._layout = layout
        self._play_log = play_log
        self._jobs = jobs
        self._clock = clock
        self._busy = False
        self._taskDone.connect(self._on_task_done)

    @Property(bool, notify=changed)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=changed)
    def defaultBackupName(self) -> str:
        return default_backup_name(self._clock())

    @Property(dict, notify=changed)
    def pendingRestore(self) -> dict[str, Any]:
        """The scheduled restore, or an empty dict when none is scheduled."""
        pending = read_pending_restore(self._layout)
        if pending is None:
            return {}
        return {
            "sourceName": pending.source_name,
            "stagedAtUtc": pending.staged_at_utc,
            "schemaVersion": pending.info.schema_version,
            "trackCount": pending.info.track_count,
        }

    @Property(str, notify=changed)
    def lastRestoreMessage(self) -> str:
        """The outcome of the restore applied at the last start, or an empty string."""
        try:
            record = json.loads(self._layout.result_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        return str(record.get("message", "")) if isinstance(record, dict) else ""

    @Slot(str)
    def backUpTo(self, url: str) -> None:
        """Write a consistent backup to the local file ``url`` (chosen in a save dialog)."""
        destination = _local_path(url)
        if destination is None:
            self.noticeRaised.emit("Choose a file name on this computer.")
            return

        def back_up() -> str:
            back_up_database(self._database, destination)
            return f"Backup saved as {destination.name}."

        self._start("Back up database", back_up)

    @Slot(str)
    def restoreFrom(self, url: str) -> None:
        """Validate the backup at ``url`` and schedule it for the next start."""
        source = _local_path(url)
        if source is None:
            self.noticeRaised.emit("Choose a backup file on this computer.")
            return
        database = self._database
        layout = self._layout
        now = self._clock()

        def stage() -> str:
            pending = stage_restore(
                source,
                layout,
                database_path=database.path,
                supported_version=database.supported_version,
                migrations=database.migrations,
                now=now,
            )
            return (
                f"Restore scheduled from {pending.source_name}. MTEE restores it the next time "
                "it starts."
            )

        self._start("Check backup", stage)

    @Slot()
    def cancelRestore(self) -> None:
        cancel_pending_restore(self._layout)
        self.changed.emit()
        self.finished.emit("The scheduled restore was cancelled.")

    @Slot()
    def resetStatistics(self) -> None:
        self._start(
            "Reset listening statistics",
            lambda: (
                f"Statistics reset. Listening events removed: {reset_statistics(self._play_log)}."
            ),
        )

    def _start(self, label: str, action: Callable[[], str]) -> None:
        if self._busy:
            self.noticeRaised.emit("Wait for the current action to finish.")
            return
        self._busy = True
        self.changed.emit()

        def task(context: JobContext) -> None:
            del context
            try:
                message = action()
            except Exception as error:
                # Any failure must release the busy flag; the reason is shown to the user.
                self._taskDone.emit("", _readable(error))
                return
            self._taskDone.emit(message, "")

        self._jobs.submit(task, label=label, visible=True)

    @Slot(str, str)
    def _on_task_done(self, message: str, error: str) -> None:
        self._busy = False
        self.changed.emit()
        if error:
            self.noticeRaised.emit(error)
        elif message:
            self.finished.emit(message)


def _local_path(url: str) -> Path | None:
    local = QUrl(url).toLocalFile()
    return Path(local) if local else None


def _readable(error: BaseException) -> str:
    """A message for the user; the exception type is not shown."""
    if isinstance(error, FileExistsError):
        return "A file with that name already exists. Choose another name."
    if isinstance(error, BackupValidationError | OSError | ValueError):
        return str(error) or "The action did not complete."
    return f"The action did not complete: {error}"
