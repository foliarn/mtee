"""Qt model for the playing track's cached, cancellable waveform."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot

from mtee.domain.conversion import ConversionSource
from mtee.domain.jobs import JobId
from mtee.domain.waveform import WaveformConfig, WaveformData
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.jobs import JobContext, JobService
from mtee.services.media_decode_service import MediaDecodeService
from mtee.services.media_probe import MediaProbeService
from mtee.services.player_service import PlayerService
from mtee.services.waveform_cache import WaveformCache
from mtee.services.waveform_service import WaveformService

__all__ = ["WaveformModel"]


class _WaveformBridge(QObject):
    completed = Signal(int, str, object, object, object)


class WaveformModel(QObject):
    stateChanged = Signal()
    progressChanged = Signal()
    errorChanged = Signal()
    durationChanged = Signal()
    samplesChanged = Signal()

    def __init__(
        self,
        player: PlayerService,
        library: LibraryRepository,
        jobs: JobService,
        file_access: FileAccessCoordinator,
        cache_dir: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._library = library
        self._jobs = jobs
        self._service = WaveformService(
            MediaDecodeService(file_access),
            WaveformCache(cache_dir),
            MediaProbeService(),
            file_access,
        )
        self._bridge = _WaveformBridge(self)
        self._bridge.completed.connect(self._on_completed, Qt.ConnectionType.QueuedConnection)
        self._track_id = ""
        self._request_id = 0
        self._request_key: tuple[str, object, WaveformConfig] | None = None
        self._job_id: JobId | None = None
        self._job_has_started = False
        self._pending_start = False
        self._data: WaveformData | None = None
        self._samples: list[list[float]] = []
        self._state = "idle"
        self._progress = 0.0
        self._error = ""
        self._player.stateChanged.connect(self._sync_track)
        self._jobs.jobUpdated.connect(self._on_job_updated)
        self._sync_track()

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return self._state

    @Property(float, notify=progressChanged)
    def progress(self) -> float:
        return self._progress

    @Property(str, notify=errorChanged)
    def error(self) -> str:
        return self._error

    @Property(int, notify=durationChanged)
    def durationUs(self) -> int:
        return self._data.duration_us if self._data else 0

    @Property(list, notify=samplesChanged)
    def samples(self) -> list[list[float]]:
        return [list(point) for point in self._samples]

    @Slot()
    def retry(self) -> None:
        self._request_key = None
        self._sync_track()

    @Slot(float)
    def seekRatio(self, ratio: float) -> None:
        duration = self._player.state.duration_us or (self._data.duration_us if self._data else 0)
        if duration <= 0:
            return
        bounded = max(0.0, min(1.0, float(ratio)))
        self._player.seek(round(bounded * duration))

    @Slot()
    def _sync_track(self) -> None:
        track_id = self._player.state.current_id
        source_record = self._library.source_record(track_id) if track_id else None
        config = WaveformConfig()
        key = (
            (track_id, source_record.revision, config)
            if source_record is not None
            else (track_id, None, config)
        )
        if key == self._request_key:
            return

        self._track_id = track_id
        self._request_key = key
        self._request_id += 1
        self._clear_data()
        self._set_state("idle" if not track_id else "generating")
        if self._job_id is not None:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(self._job_id)
            self._pending_start = bool(track_id)
            return
        self._pending_start = False
        self._start_current(source_record)

    def _start_current(self, source_record=None) -> None:
        if not self._track_id:
            self._set_state("idle")
            return
        if source_record is None:
            source_record = self._library.source_record(self._track_id)
        if source_record is None:
            self._set_state("unavailable", "The playing audio source is unavailable.")
            return

        self._request_id += 1
        request_id = self._request_id
        source = ConversionSource(self._track_id, source_record.path, source_record.revision)
        revision = source_record.revision
        config = WaveformConfig()
        self._request_key = (self._track_id, revision, config)
        self._set_progress(0.0)
        self._set_error("")
        self._set_state("generating")

        def task(context: JobContext) -> None:
            try:
                data = self._service.request(
                    source,
                    revision,
                    config,
                    is_cancelled=lambda: context.is_cancelled,
                    report_progress=context.report_progress,
                )
                context.raise_if_cancelled()
                self._bridge.completed.emit(
                    request_id, str(context.job_id), data, _display_samples(data), None
                )
            except Exception as error:
                self._bridge.completed.emit(
                    request_id, str(context.job_id), None, None, error
                )
                raise

        self._job_id = self._jobs.submit(task, label="Generate waveform", visible=False)
        self._job_has_started = False

    @Slot(object)
    def _on_job_updated(self, status: object) -> None:
        if self._job_id is None or getattr(status, "job_id", None) != self._job_id:
            return
        progress = float(getattr(status, "progress", 0.0))
        self._set_progress(progress)
        state = getattr(getattr(status, "state", None), "value", "")
        if state == "running":
            self._job_has_started = True
        elif state in {"succeeded", "failed", "cancelled"} and not self._job_has_started:
            self._job_id = None
            if self._pending_start:
                self._pending_start = False
                self._start_current()

    @Slot(int, str, object, object, object)
    def _on_completed(
        self, request_id: int, job_id: str, data: Any, samples: Any, error: Any
    ) -> None:
        if self._job_id is None or str(self._job_id) != job_id:
            return
        self._job_id = None
        self._job_has_started = False
        if request_id != self._request_id:
            if self._pending_start:
                self._pending_start = False
                self._start_current()
            return
        if error is not None:
            self._set_state("unavailable", str(error))
        elif isinstance(data, WaveformData) and isinstance(samples, list):
            self._data = data
            self._samples = samples
            self._set_progress(1.0)
            self.durationChanged.emit()
            self.samplesChanged.emit()
            self._set_state("ready")
        if self._pending_start:
            self._pending_start = False
            self._start_current()

    def _clear_data(self) -> None:
        had_data = self._data is not None
        had_samples = bool(self._samples)
        self._data = None
        self._samples = []
        self._set_progress(0.0)
        self._set_error("")
        if had_data:
            self.durationChanged.emit()
        if had_samples:
            self.samplesChanged.emit()

    def _set_state(self, state: str, error: str = "") -> None:
        changed = state != self._state
        self._state = state
        self._set_error(error)
        if changed:
            self.stateChanged.emit()

    def _set_error(self, error: str) -> None:
        if error != self._error:
            self._error = error
            self.errorChanged.emit()

    def _set_progress(self, progress: float) -> None:
        bounded = max(0.0, min(1.0, float(progress)))
        if bounded != self._progress:
            self._progress = bounded
            self.progressChanged.emit()


def _display_samples(data: WaveformData) -> list[list[float]]:
    """Prepare no more than 1,200 display points from a reduced pyramid level."""
    level = next((item for item in data.levels if item.bin_count <= 1200), data.levels[-1])
    points: list[list[float]] = []
    for index in range(level.bin_count):
        lows, highs = zip(
            *(level.bin(index, channel) for channel in range(level.channels)), strict=True
        )
        points.append([min(lows) / 32768.0, max(highs) / 32768.0])
    return points
