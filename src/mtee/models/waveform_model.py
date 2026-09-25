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
    completed = Signal(int, object, object)


class WaveformModel(QObject):
    changed = Signal()

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
        )
        self._bridge = _WaveformBridge(self)
        self._bridge.completed.connect(self._on_completed, Qt.ConnectionType.QueuedConnection)
        self._track_id = ""
        self._request_id = 0
        self._job_id: JobId | None = None
        self._data: WaveformData | None = None
        self._state = "idle"
        self._progress = 0.0
        self._error = ""
        self._zoom = 1.0
        self._view_start = 0.0
        self._marker_a: int | None = None
        self._marker_b: int | None = None
        self._player.stateChanged.connect(self._sync_track)
        self._sync_track()

    @Property(str, notify=changed)
    def state(self) -> str:
        return self._state

    @Property(float, notify=changed)
    def progress(self) -> float:
        return self._progress

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(int, notify=changed)
    def durationUs(self) -> int:
        return self._data.duration_us if self._data else 0

    @Property(float, notify=changed)
    def zoomFactor(self) -> float:
        return self._zoom

    @Property(float, notify=changed)
    def viewStart(self) -> float:
        return self._view_start

    @Property(list, notify=changed)
    def samples(self) -> list[list[float]]:
        if self._data is None:
            return []
        level = self._data.base
        window_bins = max(1, round(level.bin_count / self._zoom))
        first = min(level.bin_count - 1, round(self._view_start * level.bin_count))
        last = min(level.bin_count, first + window_bins)
        bins_per_point = max(1, (last - first + 1199) // 1200)
        result: list[list[float]] = []
        for begin in range(first, last, bins_per_point):
            finish = min(last, begin + bins_per_point)
            low, high = 32767, -32768
            for index in range(begin, finish):
                for channel in range(level.channels):
                    sample_low, sample_high = level.bin(index, channel)
                    low = min(low, sample_low)
                    high = max(high, sample_high)
            result.append([low / 32768.0, high / 32768.0])
        return result

    @Property(int, notify=changed)
    def markerA(self) -> int:
        return self._marker_a if self._marker_a is not None else -1

    @Property(int, notify=changed)
    def markerB(self) -> int:
        return self._marker_b if self._marker_b is not None else -1

    @Slot()
    def retry(self) -> None:
        self._start_current()

    @Slot()
    def zoomIn(self) -> None:
        self._set_zoom(min(32.0, self._zoom * 2.0))

    @Slot()
    def zoomOut(self) -> None:
        self._set_zoom(max(1.0, self._zoom / 2.0))

    @Slot(float)
    def pan(self, delta: float) -> None:
        maximum = max(0.0, 1.0 - 1.0 / self._zoom)
        self._view_start = max(0.0, min(maximum, self._view_start + float(delta) / self._zoom))
        self.changed.emit()

    @Slot(float)
    def seekRatio(self, ratio: float) -> None:
        duration = self._player.state.duration_us or (self._data.duration_us if self._data else 0)
        if duration <= 0:
            return
        bounded = max(0.0, min(1.0, float(ratio)))
        self._player.seek(round(bounded * duration))

    @Slot(float)
    def setLoopMarker(self, ratio: float) -> None:
        if self._data is None:
            return
        position = max(0, min(self._data.duration_us, round(float(ratio) * self._data.duration_us)))
        if self._marker_a is None or self._marker_b is not None:
            self._marker_a, self._marker_b = position, None
        elif position > self._marker_a:
            self._marker_b = position
            self._player.set_ab_loop(self._marker_a, self._marker_b)
        else:
            self._marker_a, self._marker_b = position, None
        self.changed.emit()

    @Slot()
    def markLoopA(self) -> None:
        self._marker_a = self._player.state.position_us
        self._marker_b = None
        self.changed.emit()

    @Slot()
    def markLoopB(self) -> None:
        position = self._player.state.position_us
        if self._marker_a is not None and position > self._marker_a:
            self._marker_b = position
            self._player.set_ab_loop(self._marker_a, self._marker_b)
            self.changed.emit()

    @Slot()
    def clearLoop(self) -> None:
        if self._marker_a is not None:
            self._player.set_ab_loop(None, None)
        self._marker_a = self._marker_b = None
        self.changed.emit()

    def _sync_track(self) -> None:
        track_id = self._player.state.current_id
        if track_id == self._track_id:
            return
        if self._marker_a is not None:
            self._player.set_ab_loop(None, None)
        self._track_id = track_id
        self._request_id += 1
        if self._job_id is not None:
            with suppress(LookupError):
                self._jobs.cancel(self._job_id)
        self._job_id = None
        self._data = None
        self._state = "idle"
        self._progress = 0.0
        self._error = ""
        self._zoom = 1.0
        self._view_start = 0.0
        self._marker_a = self._marker_b = None
        self._start_current()
        self.changed.emit()

    def _start_current(self) -> None:
        if not self._track_id:
            self._state = "idle"
            return
        try:
            source_record = self._library.source_record(self._track_id)
            if source_record is None or not source_record.path.is_file():
                raise FileNotFoundError("The playing audio source is unavailable.")
        except (OSError, ValueError) as error:
            self._state, self._error = "unavailable", str(error)
            self.changed.emit()
            return
        self._request_id += 1
        request_id = self._request_id
        self._state = "generating"
        self._progress = 0.0
        self._error = ""
        source = ConversionSource(self._track_id, source_record.path, source_record.revision)
        revision = source_record.revision
        config = WaveformConfig()

        def task(context: JobContext) -> None:
            try:
                data = self._service.request(
                    source,
                    revision,
                    config,
                    is_cancelled=lambda: context.is_cancelled,
                    report_progress=context.report_progress,
                )
                self._bridge.completed.emit(request_id, data, None)
            except Exception as error:
                self._bridge.completed.emit(request_id, None, error)

        self._job_id = self._jobs.submit(task, label="Generate waveform", visible=False)
        self.changed.emit()

    @Slot(int, object, object)
    def _on_completed(self, request_id: int, data: Any, error: Any) -> None:
        if request_id != self._request_id:
            return
        self._job_id = None
        if error is not None:
            self._state = "unavailable"
            self._error = str(error)
        elif isinstance(data, WaveformData):
            self._data = data
            self._state = "ready"
            self._progress = 1.0
        self.changed.emit()

    def _set_zoom(self, zoom: float) -> None:
        anchor = self._view_start + 0.5 / self._zoom
        self._zoom = zoom
        self._view_start = max(0.0, min(1.0 - 1.0 / zoom, anchor - 0.5 / zoom))
        self.changed.emit()
