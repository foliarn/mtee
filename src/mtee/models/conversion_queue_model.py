"""Conversion settings, preview and background queue exposed to QML."""

from __future__ import annotations

import uuid
from contextlib import suppress
from dataclasses import replace
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
    capabilitiesReady = Signal(int, object, object)
    previewReady = Signal(int, object, object)
    conversionResultReady = Signal(str, object)
    outputCatalogued = Signal(str, str)
    recoveryReady = Signal(object, object)
    recoveryNotice = Signal(str)

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
        self._dither_applicable = False
        self._copy_metadata = True
        self._output = Path.home() / "Music" / "Converted"
        self._preview = None
        self._capabilities = None
        self._capabilities_state = "not_loaded"
        self._capabilities_error = ""
        self._capabilities_generation = 0
        self._preview_state = "idle"
        self._preview_error = ""
        self._preview_generation = 0
        self._preview_job_id = ""
        self._preview_sources_override: tuple[ConversionSource, ...] | None = None
        self._jobs_by_conversion: dict[str, str] = {}
        self._job_results: dict[str, dict[str, Any]] = {}
        self._recovery_issue_count = 0
        self._recovery_summary = ""
        self._recovered_count = 0
        self._pending_conversions: list[tuple[str, Any, Any]] = []
        self._active_conversions: set[str] = set()
        jobs.jobUpdated.connect(self._on_job_updated)
        jobs.jobSubmitted.connect(self._on_job_submitted)
        self.capabilitiesReady.connect(self._on_capabilities_ready)
        self.previewReady.connect(self._on_preview_ready)
        self.conversionResultReady.connect(self._on_conversion_result_ready)
        self.recoveryReady.connect(self._on_recovery_ready)

        def inspect_recovery(_context: JobContext) -> None:
            try:
                self.recoveryReady.emit(self._derivations.recover_incomplete(), None)
            except Exception as error:
                self.recoveryReady.emit(None, f"{type(error).__name__}: {error}")
                raise

        try:
            self._jobs.submit(
                inspect_recovery, label="Inspect interrupted conversions", visible=False
            )
        except RuntimeError:
            pass

    @Property(list, notify=changed)
    def inputs(self) -> list[dict[str, Any]]:
        rows = []
        for source in self._sources:
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
                    "title": source.path.stem,
                }
            )
        return rows

    @Property(list, notify=changed)
    def formats(self) -> list[dict[str, str]]:
        if self._capabilities_state != "ready" or self._capabilities is None:
            return []
        return [
            {"id": item.format_id, "name": item.label, "quality": self._quality_for(item.qualities)}
            for item in self._capabilities.outputs
        ]

    @Property(str, notify=changed)
    def capabilitiesState(self) -> str:
        return self._capabilities_state

    @Property(str, notify=changed)
    def capabilitiesError(self) -> str:
        return self._capabilities_error

    @Property(str, notify=changed)
    def previewState(self) -> str:
        return self._preview_state

    @Property(str, notify=changed)
    def previewError(self) -> str:
        return self._preview_error

    @Slot()
    def ensure_capabilities(self) -> None:
        if self._capabilities_state in {"loading", "ready"}:
            return
        self._capabilities_state = "loading"
        self._capabilities_error = ""
        self._capabilities_generation += 1
        generation = self._capabilities_generation

        def inspect(context: JobContext) -> None:
            try:
                context.raise_if_cancelled()
                result = self._service.capabilities()
                self.capabilitiesReady.emit(generation, result, None)
            except Exception as error:
                self.capabilitiesReady.emit(generation, None, f"{type(error).__name__}: {error}")
                raise

        self._jobs.submit(inspect, label="Discover conversion formats", visible=False)
        self.changed.emit()

    @Slot(int, object, object)
    def _on_capabilities_ready(self, generation: int, result: object, error: object) -> None:
        if generation != self._capabilities_generation:
            return
        if result is not None and hasattr(result, "outputs"):
            self._capabilities = result
            self._capabilities_state = "ready"
            self._capabilities_error = ""
        else:
            self._capabilities = None
            self._capabilities_state = "failed"
            self._capabilities_error = str(error or "Could not inspect the FFmpeg runtime.")
        self.changed.emit()

    @Property(int, notify=changed)
    def formatIndex(self) -> int:
        return self._format_index

    @Property(str, notify=changed)
    def outputFolder(self) -> str:
        return str(self._output)

    @Property(list, notify=changed)
    def sampleRateOptions(self) -> list[str]:
        capability = self._current_capability()
        if capability is None:
            return []
        rates = capability.sample_rates
        return ["Keep source", *(f"{rate / 1000:g} kHz" for rate in rates)]

    @Property(str, notify=changed)
    def sampleRate(self) -> str:
        capability = self._current_capability()
        if capability is None:
            return ""
        rates = capability.sample_rates
        options = ["Keep source", *(f"{rate / 1000:g} kHz" for rate in rates)]
        return options[min(self._sample_rate_index, len(options) - 1)]

    @Property(list, notify=changed)
    def channelOptions(self) -> list[str]:
        capability = self._current_capability()
        if capability is None:
            return []
        return [
            "Keep source",
            *("Mono" if item == 1 else "Stereo" for item in capability.channels),
        ]

    @Property(str, notify=changed)
    def channels(self) -> str:
        capability = self._current_capability()
        if capability is None:
            return ""
        channels = capability.channels
        options = ["Keep source", *("Mono" if item == 1 else "Stereo" for item in channels)]
        return options[min(self._channels_index, len(options) - 1)]

    @Property(list, notify=changed)
    def bitDepthOptions(self) -> list[str]:
        capability = self._current_capability()
        if capability is None:
            return []
        depths = capability.bit_depths
        return ["Keep source", *(f"{depth}-bit" for depth in depths)]

    @Property(str, notify=changed)
    def bitDepth(self) -> str:
        capability = self._current_capability()
        if capability is None:
            return ""
        depths = capability.bit_depths
        options = ["Keep source", *(f"{depth}-bit" for depth in depths)]
        return options[min(self._bit_depth_index, len(options) - 1)]

    @Property(bool, notify=changed)
    def dither(self) -> bool:
        return self._dither

    @Property(bool, notify=changed)
    def ditherEnabled(self) -> bool:
        return self._dither_applicable

    @Property(bool, notify=changed)
    def copyMetadata(self) -> bool:
        return self._copy_metadata

    @Property(bool, notify=changed)
    def error(self) -> bool:
        return self._recovery_issue_count > 0 or any(
            row.get("status") in {"failed", "conflict", "unsupported"}
            for row in self._job_results.values()
        )

    @Property(bool, notify=changed)
    def hasPreview(self) -> bool:
        return self._preview is not None and self._preview_state == "ready"

    @Property(bool, notify=changed)
    def previewExecutable(self) -> bool:
        return (
            self._preview is not None
            and self._preview_state == "ready"
            and self._preview.executable
        )

    @Property(str, notify=changed)
    def previewSummary(self) -> str:
        if self._recovery_issue_count:
            return self._recovery_summary
        if self._recovered_count:
            return f"Recovered {self._recovered_count} verified conversion result(s) from the operation journal."
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
            f"{item.destination.name}: {item.status}"
            + (
                f" · {item.effective_settings.bit_depth}-bit"
                if item.effective_settings is not None
                and item.effective_settings.bit_depth is not None
                else ""
            )
            for item in self._preview.items
        )
        return f"Preview: {ready} ready, {blocked} blocked. {details}"

    @Slot(object, object)
    def _on_recovery_ready(self, issues: object, error: object) -> None:
        rows = issues if isinstance(issues, list) else []
        unresolved = [row for row in rows if isinstance(row, dict) and row.get("status") == "needs_inspection"]
        self._recovered_count = sum(
            isinstance(row, dict) and row.get("status") == "recovered" for row in rows
        )
        if error is not None:
            self._recovery_issue_count = 1
            self._recovery_summary = "Interrupted conversion history could not be inspected."
        elif unresolved:
            names = [Path(str(row.get("destination_path", ""))).name for row in unresolved[:3]]
            self._recovery_issue_count = len(unresolved)
            self._recovery_summary = (
                f"{len(unresolved)} interrupted conversion(s) need inspection: "
                f"{', '.join(names)}. Existing files were left unchanged."
            )
        else:
            self._recovery_issue_count = 0
            self._recovery_summary = ""
        if self._recovery_issue_count:
            self.recoveryNotice.emit(self._recovery_summary)
        self.changed.emit()

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
            self._preview_sources_override = None
            self._invalidate_preview()
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
        self._invalidate_preview()
        self._preview_sources_override = None
        self.changed.emit()

    @Slot()
    def set_output_folder(self, value: str) -> None:
        selected = QUrl(value).toLocalFile() or value
        folder = Path(selected).expanduser()
        if folder.is_dir():
            self._output = folder.resolve()
            self._invalidate_preview()
            self.changed.emit()

    @Slot()
    def open_output_folder(self) -> None:
        if self._output.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output)))

    @Slot()
    def next_format(self) -> None:
        formats = self._capabilities.outputs if self._capabilities is not None else ()
        if formats:
            self._format_index = (self._format_index + 1) % len(formats)
            self._quality_index = 0
            self._sample_rate_index = 0
            self._channels_index = 0
            self._bit_depth_index = 0
            self._dither = False
            self._dither_applicable = False
            self._invalidate_preview()
            self.changed.emit()

    @Slot()
    def next_quality(self) -> None:
        formats = self._capabilities.outputs if self._capabilities is not None else ()
        if not formats:
            return
        qualities = formats[self._format_index].qualities
        if qualities:
            self._quality_index = (self._quality_index + 1) % len(qualities)
            self._invalidate_preview()
            self.changed.emit()

    @Slot()
    def next_sample_rate(self) -> None:
        capability = self._current_capability()
        if capability is None:
            return
        values = capability.sample_rates
        self._sample_rate_index = (self._sample_rate_index + 1) % (len(values) + 1)
        self._invalidate_preview()
        self.changed.emit()

    @Slot()
    def next_channels(self) -> None:
        capability = self._current_capability()
        if capability is None:
            return
        values = capability.channels
        self._channels_index = (self._channels_index + 1) % (len(values) + 1)
        self._invalidate_preview()
        self.changed.emit()

    @Slot()
    def next_bit_depth(self) -> None:
        capability = self._current_capability()
        if capability is None:
            return
        values = capability.bit_depths
        self._bit_depth_index = (self._bit_depth_index + 1) % (len(values) + 1)
        self._invalidate_preview()
        self.changed.emit()

    @Slot()
    def toggle_dither(self) -> None:
        if not self._dither_applicable:
            return
        self._dither = not self._dither
        self._invalidate_preview()
        self.changed.emit()

    @Slot()
    def toggle_metadata(self) -> None:
        self._copy_metadata = not self._copy_metadata
        self._invalidate_preview()
        self.changed.emit()

    @Slot()
    def preview_or_start(self) -> None:
        if self._preview_state in {"preparing", "starting"}:
            return
        if self._preview is not None and self._preview_state == "ready":
            self.start()
            return
        if self._capabilities_state != "ready" or self._capabilities is None:
            self.ensure_capabilities()
            self._preview_error = "Conversion formats are still loading."
            self.changed.emit()
            return
        formats = self._capabilities.outputs
        if not self._sources or not formats:
            self.changed.emit()
            return
        output = formats[min(self._format_index, len(formats) - 1)]
        quality = output.qualities[self._quality_index % len(output.qualities)]
        settings = self._settings(output, quality)
        sources = self._preview_sources_override or tuple(self._sources)
        if not sources:
            return
        request = ConversionRequest(tuple(sources), self._output, settings)
        self._preview_generation += 1
        generation = self._preview_generation
        self._preview_state = "preparing"
        self._preview_error = ""

        def prepare(context: JobContext) -> None:
            try:
                context.raise_if_cancelled()
                preview = self._service.preview(request)
                context.raise_if_cancelled()
                self.previewReady.emit(generation, preview, None)
            except JobCancelledError:
                raise
            except Exception as error:
                self.previewReady.emit(generation, None, f"{type(error).__name__}: {error}")
                raise

        self._preview_job_id = str(
            self._jobs.submit(prepare, label="Prepare conversion preview", visible=False)
        )
        self.changed.emit()

    @Slot(int, object, object)
    def _on_preview_ready(self, generation: int, preview: object, error: object) -> None:
        if generation != self._preview_generation:
            return
        self._preview_job_id = ""
        if preview is not None and hasattr(preview, "items"):
            self._preview = preview
            self._preview_state = "ready"
            self._preview_error = ""
            for item in preview.items:
                if item.status != "ready":
                    self._job_results[item.source.track_id] = {
                        "status": item.status,
                        "progress": 0,
                        "message": item.message,
                    }
            self._dither_applicable = any(
                item.status == "ready"
                and item.probe is not None
                and item.effective_settings is not None
                and item.effective_settings.format_id in {"wav", "aiff"}
                and item.effective_settings.bit_depth is not None
                and item.probe.bits_per_sample is not None
                and item.effective_settings.bit_depth < item.probe.bits_per_sample
                for item in preview.items
            )
        else:
            self._preview = None
            self._preview_state = "failed"
            self._preview_error = str(error or "Could not prepare the conversion preview.")
        self.changed.emit()

    def start(self) -> None:
        if (
            self._preview is None
            or not self._preview.executable
            or self._preview_state != "ready"
        ):
            return
        preview = self._preview
        self._preview = None
        self._preview_state = "starting"
        self._preview_sources_override = None
        self._pending_conversions = []
        for item in preview.items:
            if item.status != "ready":
                continue
            conversion_id = str(uuid.uuid4())
            self._pending_conversions.append(
                (conversion_id, replace(item, derived_track_id=conversion_id), preview)
            )
        for _conversion_id, item, _preview in self._pending_conversions:
            self._job_results[item.source.track_id] = {
                "status": "queued",
                "progress": 0,
                "message": "Waiting for a conversion slot.",
            }
        self._preview_state = "idle"
        self._launch_pending_conversions()
        self.changed.emit()

    def _launch_pending_conversions(self) -> None:
        while self._pending_conversions and len(self._active_conversions) < 2:
            conversion_id, item, preview = self._pending_conversions.pop(0)

            def task(context: JobContext, item=item, preview=preview, conversion_id=conversion_id) -> None:
                published = False
                context.report_detail(item.destination.name)
                try:
                    settings = item.effective_settings or preview.request.settings
                    temporary = item.destination.with_name(
                        f".{item.destination.stem}.mtee-{conversion_id}.tmp{item.destination.suffix}"
                    )
                    self._derivations.prepare(
                        conversion_id,
                        item.source,
                        str(item.destination),
                        settings,
                        preview.ffmpeg_version,
                        str(temporary),
                        item.derived_track_id,
                    )
                    with self._file_access.acquire_read(
                        _track_id(item.source.track_id), "audio conversion", timeout_seconds=0
                    ):
                        result = self._service.convert_item(
                            preview,
                            item,
                            conversion_id=conversion_id,
                            is_cancelled=lambda: context.is_cancelled,
                            report_progress=context.report_progress,
                            before_publish=lambda source_hash, output_hash, temp_path, output_probe, metadata_report: self._derivations.record_verified_output(
                                conversion_id,
                                source_hash,
                                output_hash,
                                temp_path,
                                output_probe,
                                metadata_report,
                            ),
                        )
                    published = result.status == "completed"
                    self._derivations.record(result, preview.ffmpeg_version)
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
                except JobCancelledError:
                    self._derivations.mark_status(conversion_id, "cancelled")
                    raise
                except Exception as error:
                    if not published:
                        with suppress(Exception):
                            self._derivations.mark_status(conversion_id, "failed")
                    self.conversionResultReady.emit(
                        item.source.track_id,
                        {
                            "status": "completed" if published else "failed",
                            "message": (
                                "Output published and verified, but its lineage journal needs inspection."
                                if published
                                else f"{type(error).__name__}: {error}"
                            ),
                            "destination": str(item.destination),
                        },
                    )
                    raise
                if result.status == "completed":
                    try:
                        catalogued = self._library.register_derived_output(
                            result.destination,
                            self._service.read_metadata(result.destination),
                        )
                    except Exception as error:
                        result = replace(
                            result,
                            message=(
                                "Output verified and published. The library will index it on its next scan: "
                                f"{type(error).__name__}."
                            ),
                        )
                    else:
                        if catalogued is not None:
                            self.outputCatalogued.emit(*catalogued)
                self.conversionResultReady.emit(item.source.track_id, result)
                if result.status != "completed":
                    raise _ConversionOutcomeError(result.status, result.message)

            job_id = JobId.new()
            job_key = str(job_id)
            self._jobs_by_conversion[job_key] = item.source.track_id
            self._active_conversions.add(job_key)
            try:
                self._jobs.submit(
                    task,
                    label=f"Convert {item.source.path.name}",
                    job_id=job_id,
                )
            except RuntimeError as error:
                self._jobs_by_conversion.pop(job_key, None)
                self._active_conversions.discard(job_key)
                self._job_results[item.source.track_id] = {
                    "status": "cancelled",
                    "progress": 0,
                    "message": str(error),
                }
                continue

    @Slot(str, object)
    def _on_conversion_result_ready(self, track_id: str, result: object) -> None:
        if isinstance(result, ConversionResult):
            self._job_results[track_id] = {
                "status": result.status,
                "progress": 100 if result.status == "completed" else 0,
                "message": result.message,
                "destination": str(result.destination),
                "metadataReport": "; ".join(
                    f"{field}: {status}" for field, status in result.metadata_report
                ),
            }
        elif isinstance(result, dict):
            self._job_results[track_id] = dict(result)
        self.changed.emit()

    @Slot(str)
    def cancel(self, job_id: str) -> None:
        self._jobs.cancel(JobId.parse(job_id))

    @Slot()
    def cancel_all(self) -> None:
        for status in self._jobs.statuses():
            if not status.is_terminal and str(status.job_id) in self._jobs_by_conversion:
                self._jobs.cancel(status.job_id)
        for _conversion_id, item, _preview in self._pending_conversions:
            self._job_results[item.source.track_id] = {
                "status": "cancelled",
                "progress": 0,
                "message": "Conversion cancelled before it started.",
            }
        self._pending_conversions.clear()
        self.changed.emit()

    @Slot()
    def retry_failed(self) -> None:
        failed = {
            track_id
            for track_id, result in self._job_results.items()
            if result.get("status") in {"failed", "conflict", "cancelled"}
        }
        sources = tuple(source for source in self._sources if source.track_id in failed)
        formats = self._capabilities.outputs if self._capabilities is not None else ()
        if not sources or not formats:
            self.ensure_capabilities()
            return
        for source in sources:
            self._job_results.pop(source.track_id, None)
        self._invalidate_preview()
        self._preview_sources_override = sources
        self.preview_or_start()
        self.changed.emit()

    @Slot(str)
    def remove(self, track_id: str) -> None:
        self._sources = [source for source in self._sources if source.track_id != track_id]
        self._preview_sources_override = None
        self._invalidate_preview()
        self.changed.emit()

    def _quality_for(self, qualities: tuple[str, ...]) -> str:
        return qualities[self._quality_index % len(qualities)] if qualities else ""

    def _current_capability(self):
        if self._capabilities is None or not self._capabilities.outputs:
            return None
        return self._capabilities.outputs[min(self._format_index, len(self._capabilities.outputs) - 1)]

    def _settings(self, output, quality: str) -> ConversionSettings:
        capability = self._current_capability()
        if capability is None:
            raise RuntimeError("Conversion capabilities are not ready.")
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

    def _invalidate_preview(self) -> None:
        self._preview_generation += 1
        if self._preview_job_id:
            with suppress(LookupError, ValueError):
                self._jobs.cancel(JobId.parse(self._preview_job_id))
        self._preview_job_id = ""
        self._preview = None
        self._preview_state = "idle"
        self._preview_error = ""

    def _on_job_submitted(self, _status: object) -> None:
        self.changed.emit()

    def _on_job_updated(self, status: object) -> None:
        job_id = str(getattr(status, "job_id", ""))
        track_id = self._jobs_by_conversion.get(job_id)
        if track_id is None:
            return
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
            current = self._job_results.get(track_id, {})
            if current.get("status") not in {
                "failed",
                "conflict",
                "unsupported",
                "completed",
                "cancelled",
            }:
                self._job_results[track_id] = {
                    "status": getattr(state, "value", "failed"),
                    "message": getattr(error, "message", "Conversion stopped."),
                    "progress": 0,
                }
        elif state_value == "succeeded":
            current = self._job_results.get(track_id, {})
            if current.get("status") in {"running", "queued"}:
                self._job_results[track_id] = {
                    **current,
                    "status": "completed",
                    "progress": 100,
                }
        if getattr(status, "is_terminal", False):
            self._active_conversions.discard(job_id)
            self._jobs_by_conversion.pop(job_id, None)
            self._launch_pending_conversions()
        self.changed.emit()


def _track_id(value: str):
    from mtee.domain.tracks import TrackId

    return TrackId.parse(value)


class _ConversionOutcomeError(RuntimeError):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message or f"Conversion ended with status {status}.")
        self.code = f"conversion_{status}"
