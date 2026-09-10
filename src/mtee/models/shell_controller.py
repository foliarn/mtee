"""Bridge between the QML shell and the services of the foundation step.

The controller exposes the state of the window and forwards the actions to the
services. It performs no file access and holds no business rule of its own.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee import __version__
from mtee.domain.jobs import JobId, JobStatus
from mtee.persistence.settings_repository import SettingsRepository
from mtee.services.app_paths import AppPaths
from mtee.services.jobs import JobContext, JobService, UnknownJobError

__all__ = ["SETTING_DETAILS_VISIBLE", "SETTING_LAST_STATUS", "ShellController"]

SETTING_LAST_STATUS = "shell/last_status"
SETTING_DETAILS_VISIBLE = "shell/details_visible"
_DEMO_JOB_SECONDS = 2.0


class ShellController(QObject):
    """State of the window shown by the foundation step."""

    statusMessageChanged = Signal()
    detailsVisibleChanged = Signal()

    def __init__(
        self,
        *,
        paths: AppPaths,
        settings: SettingsRepository,
        jobs: JobService,
        demo_mode: bool,
        font_family: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._paths = paths
        self._settings = settings
        self._jobs = jobs
        self._demo_mode = demo_mode
        self._font_family = font_family
        self._status_message = "Ready"
        self._details_visible = bool(settings.get_json(SETTING_DETAILS_VISIBLE, False))
        jobs.jobUpdated.connect(self._on_job_updated)

    @Property(str, constant=True)
    def applicationVersion(self) -> str:
        return __version__

    @Property(str, constant=True)
    def modeLabel(self) -> str:
        """Return the label of the current run, so a demo run is never mistaken."""
        return "Demo data" if self._demo_mode else "Local collection"

    @Property(bool, constant=True)
    def demoMode(self) -> bool:
        return self._demo_mode

    @Property(str, constant=True)
    def dataDirectory(self) -> str:
        return str(self._paths.data_dir)

    @Property(str, constant=True)
    def fontFamily(self) -> str:
        return self._font_family

    @Property(str, notify=statusMessageChanged)
    def statusMessage(self) -> str:
        return self._status_message

    @Property(bool, notify=detailsVisibleChanged)
    def detailsVisible(self) -> bool:
        return self._details_visible

    @Slot(bool)
    def setDetailsVisible(self, visible: bool) -> None:
        """Show or hide the metadata inspector and remember the choice."""
        if bool(visible) == self._details_visible:
            return
        self._details_visible = bool(visible)
        self._settings.set_json(SETTING_DETAILS_VISIBLE, self._details_visible)
        self.detailsVisibleChanged.emit()

    @Slot(result=str)
    def startSampleJob(self) -> str:
        """Submit the artificial two second task and return its identifier."""
        job_id = self._jobs.submit(_sample_task, label="Sample background task")
        return str(job_id)

    @Slot(str)
    def cancelJob(self, job_id: str) -> None:
        """Ask the service to cancel ``job_id``; an unknown job is only reported."""
        try:
            self._jobs.cancel(JobId.parse(job_id))
        except (UnknownJobError, ValueError):
            self._set_status_message("This task is no longer running.")

    def _on_job_updated(self, status: JobStatus) -> None:
        self._set_status_message(f"{status.label}: {_describe(status)}")

    def _set_status_message(self, message: str) -> None:
        if message == self._status_message:
            return
        self._status_message = message
        self._settings.set(SETTING_LAST_STATUS, message)
        self.statusMessageChanged.emit()


def _describe(status: JobStatus) -> str:
    """Return a short English description of ``status`` for the status bar."""
    if status.is_interrupted:
        return "interrupted"
    if status.error is not None:
        return f"failed ({status.error.code})"
    return status.state.value


def _sample_task(context: JobContext) -> None:
    """Artificial task of two seconds, cancellable and reporting its progress."""
    steps = 20
    for step in range(steps):
        context.sleep(_DEMO_JOB_SECONDS / steps)
        context.report_progress((step + 1) / steps)
