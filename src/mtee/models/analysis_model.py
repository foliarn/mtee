"""Qt facade for local analysis jobs, measured values and manual confirmations."""

from __future__ import annotations

from contextlib import suppress
from typing import Any, cast

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot

from mtee.domain.analysis import AnalysisSpec
from mtee.domain.jobs import JobId, JobStatus
from mtee.services.analysis_service import AnalysisService
from mtee.services.jobs import JobService

__all__ = ["AnalysisModel"]


class _AnalysisBridge(QObject):
    completed = Signal()


class AnalysisModel(QObject):
    changed = Signal()

    def __init__(
        self,
        service: AnalysisService,
        jobs: JobService,
        selected_ids: Any,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._jobs = jobs
        self._selected_ids = selected_ids
        self._track_id = ""
        self._job_id: JobId | None = None
        self._error = ""
        self._progress = 0.0
        self._state = "idle"
        self._bridge = _AnalysisBridge(self)
        self._bridge.completed.connect(self.refresh, Qt.ConnectionType.QueuedConnection)
        jobs.jobUpdated.connect(self._on_job_updated)

    @Property(str, notify=changed)
    def trackId(self) -> str:
        return self._track_id

    @Property(str, notify=changed)
    def state(self) -> str:
        return self._state

    @Property(float, notify=changed)
    def progress(self) -> float:
        return self._progress

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(list, notify=changed)
    def results(self) -> list[dict[str, Any]]:
        return self._service.results(self._track_id) if self._track_id else []

    @Property(list, notify=changed)
    def overrides(self) -> list[dict[str, Any]]:
        return self._service.overrides(self._track_id) if self._track_id else []

    @Property(bool, notify=changed)
    def isRunning(self) -> bool:
        return self._job_id is not None

    @Slot(str)
    def setTrackId(self, track_id: str) -> None:
        track_id = str(track_id)
        if track_id == self._track_id:
            return
        self._track_id = track_id
        self._error = ""
        self.changed.emit()

    @Slot()
    def analyzeSelected(self) -> None:
        track_ids = list(dict.fromkeys(str(item) for item in self._selected_ids() if item))
        if not track_ids and self._track_id:
            track_ids = [self._track_id]
        self._submit(track_ids)

    @Slot(str)
    def analyzeTrack(self, track_id: str) -> None:
        self._submit([str(track_id)] if track_id else [])

    def _submit(self, track_ids: list[str]) -> None:
        if self._job_id is not None:
            return
        try:
            specs = [
                AnalysisSpec(name) for name in ("technical", "silence", "loudness", "tempo", "key")
            ]
            preview = self._service.preview(track_ids, specs)
            job_id = self._jobs.submit(
                lambda context: self._execute(preview, context),
                label=f"Analyze {len(preview.sources)} track(s)",
            )
            self._job_id = job_id
            self._state = "queued"
            self._progress = 0.0
            self._error = ""
            current = self._jobs.status(job_id)
            if current.is_terminal:
                self._job_id = None
                self._state = str(current.state.value)
                self._progress = float(current.progress)
                self._error = current.error.message if current.error is not None else ""
        except Exception as error:
            self._state = "failed"
            self._error = str(error)
        self.changed.emit()

    def _execute(self, preview: Any, context: Any) -> None:
        try:
            self._service.execute(preview, context)
        finally:
            self._bridge.completed.emit()

    @Slot()
    def cancel(self) -> None:
        if self._job_id is not None:
            with suppress(Exception):
                self._jobs.cancel(self._job_id)

    @Slot(str, object)
    def confirm(self, field_name: str, value: object) -> None:
        if not self._track_id:
            return
        try:
            parsed: float | str | None
            parsed = float(cast(Any, value)) if field_name == "tempo_bpm" else str(value).strip()
            self._service.confirm(self._track_id, field_name, parsed)
            self._error = ""
        except (TypeError, ValueError) as error:
            self._error = str(error)
        self.changed.emit()

    @Slot()
    def confirmCalculatedTempo(self) -> None:
        value = self._metric("tempo", "tempo_bpm")
        if value is not None:
            self.confirm("tempo_bpm", value)

    @Slot()
    def confirmCalculatedKey(self) -> None:
        value = self._metric("key", "key")
        if value:
            self.confirm("key", value)

    @Slot()
    def confirmHalfTempo(self) -> None:
        value = self._metric("tempo", "tempo_bpm")
        if isinstance(value, (int, float)) and value > 0:
            self.confirm("tempo_bpm", value / 2)

    @Slot()
    def confirmDoubleTempo(self) -> None:
        value = self._metric("tempo", "tempo_bpm")
        if isinstance(value, (int, float)) and value > 0:
            self.confirm("tempo_bpm", value * 2)

    @Slot(str)
    def useCalculatedValue(self, field_name: str) -> None:
        if not self._track_id:
            return
        self._service.clear_override(self._track_id, field_name)
        self.changed.emit()

    @Slot()
    def refresh(self) -> None:
        self.changed.emit()

    def _metric(self, analyzer: str, name: str) -> Any:
        rows = self._service.results(self._track_id) if self._track_id else []
        result = next((row for row in rows if row["analyzer"] == analyzer), None)
        if result is None:
            return None
        metric = next((item for item in result["metrics"] if item["name"] == name), None)
        return metric.get("value") if metric else None

    @Slot(str, result=object)
    def calculatedValue(self, field_name: str) -> object:
        return self._metric("tempo" if field_name == "tempo_bpm" else "key", field_name)

    @Slot()
    def _on_job_updated(self, status: JobStatus) -> None:
        if self._job_id is None or status.job_id != self._job_id:
            return
        self._state = str(status.state.value)
        self._progress = float(status.progress)
        if status.error is not None:
            self._error = status.error.message
        if status.is_terminal:
            self._job_id = None
            self._bridge.completed.emit()
        self.changed.emit()
