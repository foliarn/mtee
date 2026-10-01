"""Qt model for the playing track's stored, cancellable waveform."""

from __future__ import annotations

import struct
from contextlib import suppress
from typing import Any

from PySide6.QtCore import Property, QByteArray, QObject, Qt, Signal, Slot

from mtee.domain.conversion import ConversionSource
from mtee.domain.jobs import JobId
from mtee.domain.waveform import WaveformPoints
from mtee.domain.waveform_levels import WAVEFORM_DISPLAY_GAMMA, bar_levels
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.library_repository import LibraryRepository, TrackSource
from mtee.services.audio_analyzer import AudioAnalyzer
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.jobs import JobContext, JobService
from mtee.services.media_decode_service import MediaDecodeService
from mtee.services.player_service import PlayerService
from mtee.services.waveform_service import WaveformService

__all__ = ["WaveformModel"]


class _WaveformBridge(QObject):
    completed = Signal(int, str, object, object)


class WaveformModel(QObject):
    stateChanged = Signal()
    progressChanged = Signal()
    errorChanged = Signal()
    durationChanged = Signal()
    samplesChanged = Signal()
    levelsChanged = Signal()

    def __init__(
        self,
        player: PlayerService,
        library: LibraryRepository,
        jobs: JobService,
        file_access: FileAccessCoordinator,
        analysis: AnalysisRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._library = library
        self._jobs = jobs
        self._service = WaveformService(
            AudioAnalyzer(MediaDecodeService(file_access), file_access), analysis
        )
        self._bridge = _WaveformBridge(self)
        self._bridge.completed.connect(self._on_completed, Qt.ConnectionType.QueuedConnection)
        self._track_id = ""
        self._request_id = 0
        self._request_key: tuple[str, int | None] | None = None
        self._job_id: JobId | None = None
        self._job_has_started = False
        self._pending_start = False
        self._points: WaveformPoints | None = None
        self._samples = QByteArray()
        self._bar_count = 0
        self._levels = QByteArray()
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
        return self._points.duration_us if self._points else 0

    @Property(QByteArray, notify=samplesChanged)
    def samples(self) -> QByteArray:
        """Packed little-endian float32 ``(low, high)`` pairs, see ``WaveformPoints.packed``."""
        return self._samples

    @Property(QByteArray, notify=levelsChanged)
    def levels(self) -> QByteArray:
        """Little-endian float32 bar heights in ``[0, 1]``, one per bar (see ``setBarCount``)."""
        return self._levels

    @Slot(int)
    def setBarCount(self, count: int) -> None:
        """Ask for ``count`` bars; the levels follow the width the view can draw."""
        bounded = max(0, int(count))
        if bounded == self._bar_count:
            return
        self._bar_count = bounded
        self._refresh_levels()

    @Slot()
    def retry(self) -> None:
        self._request_key = None
        self._sync_track()

    @Slot(float)
    def seekRatio(self, ratio: float) -> None:
        duration = self._player.state.duration_us or (
            self._points.duration_us if self._points else 0
        )
        if duration <= 0:
            return
        bounded = max(0.0, min(1.0, float(ratio)))
        self._player.seek(round(bounded * duration))

    @Slot()
    def _sync_track(self) -> None:
        track_id = self._player.state.current_id
        source_record = self._library.source_record(track_id) if track_id else None
        # Editing a tag rewrites the file but not the audio, so the request is keyed
        # on the audio length, which is what decides whether a stored waveform fits.
        key = (track_id, _audio_duration_us(source_record))
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

    def _start_current(self, source_record: TrackSource | None = None) -> None:
        if not self._track_id:
            self._set_state("idle")
            return
        if source_record is None:
            source_record = self._library.source_record(self._track_id)
        if source_record is None:
            self._set_state("unavailable", "The playing audio source is unavailable.")
            return

        duration_us = _audio_duration_us(source_record)
        self._request_key = (self._track_id, duration_us)
        self._set_error("")
        stored = self._service.stored(self._track_id, duration_us)
        if stored is not None:
            # One indexed row of a few kilobytes: read it in place, no job, no flash.
            self._apply(stored)
            return

        self._request_id += 1
        request_id = self._request_id
        source = ConversionSource(self._track_id, source_record.path, source_record.revision)
        revision = source_record.revision
        self._set_progress(0.0)
        self._set_state("generating")

        def task(context: JobContext) -> None:
            try:
                points = self._service.request(
                    source,
                    revision,
                    duration_us,
                    is_cancelled=lambda: context.is_cancelled,
                    report_progress=context.report_progress,
                )
                context.raise_if_cancelled()
                self._bridge.completed.emit(request_id, str(context.job_id), points, None)
            except Exception as error:
                self._bridge.completed.emit(request_id, str(context.job_id), None, error)
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

    @Slot(int, str, object, object)
    def _on_completed(self, request_id: int, job_id: str, points: Any, error: Any) -> None:
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
        elif isinstance(points, WaveformPoints):
            self._apply(points)
        if self._pending_start:
            self._pending_start = False
            self._start_current()

    def _apply(self, points: WaveformPoints) -> None:
        self._points = points
        self._samples = QByteArray(points.packed())
        self._set_progress(1.0)
        self.durationChanged.emit()
        self.samplesChanged.emit()
        self._refresh_levels()
        self._set_state("ready")

    def _clear_data(self) -> None:
        had_data = self._points is not None
        had_samples = not self._samples.isEmpty()
        self._points = None
        self._samples = QByteArray()
        self._set_progress(0.0)
        self._set_error("")
        if had_data:
            self.durationChanged.emit()
        if had_samples:
            self.samplesChanged.emit()
        self._refresh_levels()

    def _refresh_levels(self) -> None:
        if self._points is None or self._bar_count < 1:
            levels = QByteArray()
        else:
            values = bar_levels(self._points, self._bar_count, WAVEFORM_DISPLAY_GAMMA)
            levels = QByteArray(struct.pack(f"<{len(values)}f", *values))
        if levels != self._levels:
            self._levels = levels
            self.levelsChanged.emit()

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


def _audio_duration_us(source: TrackSource | None) -> int | None:
    return source.snapshot.technical.duration_us if source is not None else None
