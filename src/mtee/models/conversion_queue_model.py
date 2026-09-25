"""Conversion settings, preview and background queue exposed to QML."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from mtee.domain.conversion import (
    ConversionRequest,
    ConversionResult,
    ConversionSettings,
    ConversionSource,
)
from mtee.domain.jobs import JobCancelledError, JobId
from mtee.domain.tracks import SourceRevision
from mtee.persistence.derivations_repository import DerivationsRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.conversion_service import ConversionService
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError
from mtee.services.jobs import JobContext, JobService

__all__ = ["ConversionQueueModel"]


class ConversionQueueModel(QObject):
    """Own conversion queue UI state while all media work stays in JobService."""

    changed = Signal()

    def __init__(
        self,
        library: LibraryRepository,
        jobs: JobService,
        service: ConversionService,
        file_access: FileAccessCoordinator,
        derivations: DerivationsRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._library = library
        self._jobs = jobs
        self._service = service
        self._file_access = file_access
        self._derivations = derivations
        self._sources: list[ConversionSource] = []
        self._format_index = 0
        self._quality_index = 0
        self._sample_rate_index = 0
        self._channels_index = 0
        self._bit_depth_index = 0
        self._dither = False
        self._copy_metadata = True
        self._output = Path.home() / "Music" / "Converted"
        self._preview = None
        self._jobs_by_conversion: dict[str, str] = {}
        self._job_results: dict[str, dict[str, Any]] = {}
        jobs.jobUpdated.connect(self._on_job_updated)
        jobs.jobSubmitted.connect(self._on_job_submitted)

    @Property(list, notify=changed)
    def inputs(self) -> list[dict[str, Any]]:
        rows = []
        for source in self._sources:
            snapshot = self._library.source_record(source.track_id)
            meta = snapshot.snapshot if snapshot is not None else None
            rows.append(
                {
                    "trackId": source.track_id,
                    "filename": source.path.name,
                    "format": source.path.suffix.removeprefix(".").upper(),
                    "bitrate": "Ready for inspection",
                    "duration": "—",
                    "cover": 0,
                    "status": self._job_results.get(source.track_id, {}).get("status", "ready"),
                    "progress": self._job_results.get(source.track_id, {}).get("progress", 0),
                    "summary": self._job_results.get(source.track_id, {}).get("message", ""),
                    "metadataReport": self._job_results.get(source.track_id, {}).get(
                        "metadataReport", ""
                    ),
                    "destination": self._job_results.get(source.track_id, {}).get(
                        "destination", ""
                    ),
                    "title": (meta.title[0] if meta and meta.title else source.path.stem),
                }
            )
        return rows

    @Property(list, notify=changed)
    def formats(self) -> list[dict[str, str]]:
        return [
            {"id": item.format_id, "name": item.label, "quality": self._quality_for(item.qualities)}
            for item in self._service.capabilities().outputs
        ]

    @Property(int, notify=changed)
    def formatIndex(self) -> int:
        return self._format_index

    @Property(str, notify=changed)
    def outputFolder(self) -> str:
        return str(self._output)

    @Property(list, notify=changed)
    def sampleRateOptions(self) -> list[str]:
        rates = self._current_capability().sample_rates
        return ["Keep source", *(f"{rate / 1000:g} kHz" for rate in rates)]

    @Property(str, notify=changed)
    def sampleRate(self) -> str:
        rates = self._current_capability().sample_rates
        options = ["Keep source", *(f"{rate / 1000:g} kHz" for rate in rates)]
        return options[min(self._sample_rate_index, len(options) - 1)]

    @Property(list, notify=changed)
    def channelOptions(self) -> list[str]:
        return [
            "Keep source",
            *("Mono" if item == 1 else "Stereo" for item in self._current_capability().channels),
        ]

    @Property(str, notify=changed)
    def channels(self) -> str:
        channels = self._current_capability().channels
        options = ["Keep source", *("Mono" if item == 1 else "Stereo" for item in channels)]
        return options[min(self._channels_index, len(options) - 1)]

    @Property(list, notify=changed)
    def bitDepthOptions(self) -> list[str]:
        depths = self._current_capability().bit_depths
        return ["Keep source", *(f"{depth}-bit" for depth in depths)]

    @Property(str, notify=changed)
    def bitDepth(self) -> str:
        depths = self._current_capability().bit_depths
        options = ["Keep source", *(f"{depth}-bit" for depth in depths)]
        return options[min(self._bit_depth_index, len(options) - 1)]

    @Property(bool, notify=changed)
    def dither(self) -> bool:
        return self._dither

    @Property(bool, notify=changed)
    def copyMetadata(self) -> bool:
        return self._copy_metadata

    @Property(bool, notify=changed)
    def error(self) -> bool:
        return any(
            row.get("status") in {"failed", "conflict", "unsupported"}
            for row in self._job_results.values()
        )

    @Property(bool, notify=changed)
    def hasPreview(self) -> bool:
        return self._preview is not None

    @Property(bool, notify=changed)
    def previewExecutable(self) -> bool:
        return self._preview is not None and self._preview.executable

    @Property(str, notify=changed)
    def previewSummary(self) -> str:
        finished = sum(row.get("status") == "completed" for row in self._job_results.values())
        failed = sum(
            row.get("status") in {"failed", "conflict", "cancelled"}
            for row in self._job_results.values()
        )
        if finished or failed:
            return f"{finished} converted · {failed} need attention"
        if self._preview is None:
            return f"{len(self._sources)} files ready"
        ready = sum(item.status == "ready" for item in self._preview.items)
        blocked = len(self._preview.items) - ready
        details = ", ".join(
            f"{item.destination.name}: {item.status}" for item in self._preview.items
        )
        return f"Preview: {ready} ready, {blocked} blocked. {details}"

    @Property(bool, notify=changed)
    def canCancel(self) -> bool:
        return any(
            not status.is_terminal and str(status.job_id) in self._jobs_by_conversion
            for status in self._jobs.statuses()
        )

    @Slot(list)
    def add_tracks(self, track_ids: list) -> None:
        known = {source.track_id for source in self._sources}
        added = False
        for raw_id in track_ids:
            track_id = str(raw_id)
            if not track_id or track_id in known:
                continue
            record = self._library.source_record(track_id)
            if record is None or record.status != "readable":
                continue
            self._sources.append(ConversionSource(track_id, record.path, record.revision))
            known.add(track_id)
            added = True
        if added:
            self._preview = None
            self.changed.emit()

    @Slot(list)
    def add_files(self, selected: list) -> None:
        known = {str(source.path.resolve(strict=False)).casefold() for source in self._sources}
        for value in selected:
            text = value.toString() if isinstance(value, QUrl) else str(value)
            path = Path(QUrl(text).toLocalFile() or text).expanduser()
            if not path.is_file() or str(path.resolve(strict=False)).casefold() in known:
                continue
            revision = SourceRevision.observe(path)
            self._sources.append(ConversionSource(str(uuid.uuid4()), path.resolve(), revision))
            known.add(str(path.resolve(strict=False)).casefold())
        self._preview = None
        self.changed.emit()

    @Slot()
    def set_output_folder(self, value: str) -> None:
        selected = QUrl(value).toLocalFile() or value
        folder = Path(selected).expanduser()
        if folder.is_dir():
            self._output = folder.resolve()
            self._preview = None
            self.changed.emit()

    @Slot()
    def open_output_folder(self) -> None:
        if self._output.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output)))

    @Slot()
    def next_format(self) -> None:
        formats = self._service.capabilities().outputs
        if formats:
            self._format_index = (self._format_index + 1) % len(formats)
            self._quality_index = 0
            self._sample_rate_index = 0
            self._channels_index = 0
            self._bit_depth_index = 0
            self._dither = False
            self._preview = None
            self.changed.emit()

    @Slot()
    def next_quality(self) -> None:
        formats = self._service.capabilities().outputs
        if not formats:
            return
        qualities = formats[self._format_index].qualities
        if qualities:
            self._quality_index = (self._quality_index + 1) % len(qualities)
            self._preview = None
            self.changed.emit()

    @Slot()
    def next_sample_rate(self) -> None:
        values = self._current_capability().sample_rates
        self._sample_rate_index = (self._sample_rate_index + 1) % (len(values) + 1)
        self._preview = None
        self.changed.emit()

    @Slot()
    def next_channels(self) -> None:
        values = self._current_capability().channels
        self._channels_index = (self._channels_index + 1) % (len(values) + 1)
        self._preview = None
        self.changed.emit()

    @Slot()
    def next_bit_depth(self) -> None:
        values = self._current_capability().bit_depths
        self._bit_depth_index = (self._bit_depth_index + 1) % (len(values) + 1)
        self._preview = None
        self.changed.emit()

    @Slot()
    def toggle_dither(self) -> None:
        self._dither = not self._dither
        self._preview = None
        self.changed.emit()

    @Slot()
    def toggle_metadata(self) -> None:
        self._copy_metadata = not self._copy_metadata
        self._preview = None
        self.changed.emit()

    @Slot()
    def preview_or_start(self) -> None:
        if self._preview is not None:
            self.start()
            return
        formats = self._service.capabilities().outputs
        if not self._sources or not formats:
            self.changed.emit()
            return
        output = formats[self._format_index]
        quality = output.qualities[self._quality_index % len(output.qualities)]
        settings = self._settings(output, quality)
        self._preview = self._service.preview(
            ConversionRequest(tuple(self._sources), self._output, settings)
        )
        self.changed.emit()

    def start(self) -> None:
        if self._preview is None or not self._preview.executable:
            return
        preview = self._preview
        self._preview = None
        for item in preview.items:

            def task(context: JobContext, item=item) -> None:
                conversion_id = str(uuid.uuid4())
                self._derivations.prepare(
                    conversion_id,
                    item.source,
                    str(item.destination),
                    preview.request.settings,
                    preview.ffmpeg_version,
                )
                try:
                    with self._file_access.acquire_read(
                        _track_id(item.source.track_id), "audio conversion", timeout_seconds=0
                    ):
                        result = self._service.convert_item(
                            preview,
                            item,
                            conversion_id=conversion_id,
                            is_cancelled=lambda: context.is_cancelled,
                            report_progress=context.report_progress,
                        )
                except FileAccessTimeoutError:
                    result = ConversionResult(
                        conversion_id,
                        item.source.track_id,
                        item.source.path,
                        item.destination,
                        "failed",
                        "Stop playback or wait for the source file before converting it.",
                    )
                    self._derivations.record(result, preview.ffmpeg_version)
                    self._job_results[item.source.track_id] = {
                        "status": result.status,
                        "message": result.message,
                    }
                    self.changed.emit()
                    return
                except JobCancelledError:
                    self._derivations.mark_status(conversion_id, "cancelled")
                    raise
                except Exception:
                    self._derivations.mark_status(conversion_id, "failed")
                    raise
                self._derivations.record(result, preview.ffmpeg_version)
                self._job_results[item.source.track_id] = {
                    "status": result.status,
                    "message": result.message,
                    "destination": str(result.destination),
                    "metadataReport": "; ".join(
                        f"{field}: {status}" for field, status in result.metadata_report
                    ),
                }
                self.changed.emit()

            job_id = self._jobs.submit(task, label=f"Convert {item.source.path.name}")
            self._jobs_by_conversion[str(job_id)] = item.source.track_id
        self.changed.emit()

    @Slot(str)
    def cancel(self, job_id: str) -> None:
        self._jobs.cancel(JobId.parse(job_id))

    @Slot()
    def cancel_all(self) -> None:
        for status in self._jobs.statuses():
            if not status.is_terminal and str(status.job_id) in self._jobs_by_conversion:
                self._jobs.cancel(status.job_id)

    @Slot()
    def retry_failed(self) -> None:
        failed = {
            track_id
            for track_id, result in self._job_results.items()
            if result.get("status") in {"failed", "conflict", "cancelled"}
        }
        sources = tuple(source for source in self._sources if source.track_id in failed)
        formats = self._service.capabilities().outputs
        if not sources or not formats:
            return
        output = formats[self._format_index]
        quality = output.qualities[self._quality_index % len(output.qualities)]
        request = ConversionRequest(sources, self._output, self._settings(output, quality))
        self._preview = self._service.preview(request)
        for source in sources:
            self._job_results.pop(source.track_id, None)
        self.changed.emit()

    @Slot(str)
    def remove(self, track_id: str) -> None:
        self._sources = [source for source in self._sources if source.track_id != track_id]
        self._preview = None
        self.changed.emit()

    def _quality_for(self, qualities: tuple[str, ...]) -> str:
        return qualities[self._quality_index % len(qualities)] if qualities else ""

    def _current_capability(self):
        formats = self._service.capabilities().outputs
        return formats[min(self._format_index, len(formats) - 1)]

    def _settings(self, output, quality: str) -> ConversionSettings:
        capability = self._current_capability()
        return ConversionSettings(
            output.format_id,
            quality,
            sample_rate=(
                capability.sample_rates[self._sample_rate_index - 1]
                if self._sample_rate_index
                else None
            ),
            channels=capability.channels[self._channels_index - 1]
            if self._channels_index
            else None,
            bit_depth=capability.bit_depths[self._bit_depth_index - 1]
            if self._bit_depth_index
            else None,
            dither=self._dither,
            copy_metadata=self._copy_metadata,
        )

    def _on_job_submitted(self, _status: object) -> None:
        self.changed.emit()

    def _on_job_updated(self, status: object) -> None:
        job_id = str(getattr(status, "job_id", ""))
        track_id = self._jobs_by_conversion.get(job_id)
        if track_id is not None:
            state = getattr(status, "state", None)
            state_value = getattr(state, "value", "")
            if state_value in {"running", "queued"}:
                previous = self._job_results.get(track_id, {})
                self._job_results[track_id] = {
                    **previous,
                    "status": state_value,
                    "progress": round(float(getattr(status, "progress", 0.0)) * 100),
                }
            elif state_value in {"failed", "cancelled"}:
                error = getattr(status, "error", None)
                self._job_results[track_id] = {
                    "status": getattr(state, "value", "failed"),
                    "message": getattr(error, "message", "Conversion stopped."),
                    "progress": 0,
                }
        self.changed.emit()


def _track_id(value: str):
    from mtee.domain.tracks import TrackId

    return TrackId.parse(value)
