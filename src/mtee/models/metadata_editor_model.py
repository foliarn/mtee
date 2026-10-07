"""Async metadata drafts, field capabilities, retries, and verified Undo."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.domain.analysis import AnalysisSettings, TrackAnalysis, format_bpm
from mtee.domain.artists import dedupe_names, normalize_key, split_credit
from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.metadata_edit import (
    EDITABLE_METADATA_FIELDS,
    MetadataEditResult,
    MetadataPatch,
    serialize_artists,
)
from mtee.domain.musical_key import format_key
from mtee.domain.tag_values import validate_field
from mtee.domain.tracks import SourceRevision
from mtee.models.player_model import PlayerModel
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.library_repository import LibraryRepository, TrackSource
from mtee.services.jobs import JobCancelledError, JobContext, JobId, JobService, UnknownJobError
from mtee.services.metadata_writer import MetadataEditService

__all__ = ["MetadataEditorModel"]

_FIELD_LABELS = {
    "title": "Title",
    "artist": "Artist",
    "album": "Album",
    "genre": "Genre",
    "date": "Date",
    "comment": "Comment",
    "track_number": "Track number",
    "bpm": "BPM",
    "key": "Key",
}
_FIELD_ATTRIBUTES = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "genre": "genre",
    "date": "date",
    "comment": "comment",
    "track_number": "track_number",
    "bpm": "bpm",
    "key": "key",
}


@dataclass(frozen=True, slots=True)
class _EditTarget:
    track_id: str
    revision: SourceRevision


@dataclass(frozen=True, slots=True)
class _EditBatch:
    batch_id: str
    draft_id: str
    field: str
    value: str | None
    targets: tuple[_EditTarget, ...]
    draft_selection: tuple[str, ...]
    # A batch saved from the staged changes writes several fields in one pass:
    # ``changes`` holds the plain fields, ``artist_names`` the credit of each track.
    changes: tuple[tuple[str, str | None], ...] = ()
    artist_names: tuple[tuple[str, tuple[str, ...]], ...] = ()
    staged: tuple[tuple[str, Any], ...] = ()

    @property
    def is_staged(self) -> bool:
        return self.field == "*"


class ArtistTags(Protocol):
    """The part of the artist catalog the tag editor talks to."""

    def protected_names(self) -> list[str]: ...

    def suggestions(self, query: str, limit: int = 8) -> list[dict[str, object]]: ...

    def sync_tags(self, track_id: str, names: Sequence[str], title: str | None = None) -> bool: ...


class MetadataEditorModel(QObject):
    """Capture selected UUIDs on focus and persist edits in background jobs."""

    changed = Signal()
    sourceChanged = Signal()
    batchFinished = Signal(str, object)
    recoveryChecked = Signal(object)
    inspectionFinished = Signal(int, object)
    stagingChanged = Signal()
    artistsChanged = Signal()
    artistsSynced = Signal()
    noticeRaised = Signal(str)
    valuesLoaded = Signal(object)
    valuesChanged = Signal()

    def __init__(
        self,
        library: LibraryRepository,
        writer: MetadataEditService,
        jobs: JobService,
        selected_ids: Callable[[], list[str]],
        player: PlayerModel | None = None,
        parent: QObject | None = None,
        *,
        analysis: AnalysisRepository | None = None,
        analysis_settings: Callable[[], AnalysisSettings] | None = None,
        artists: ArtistTags | None = None,
    ) -> None:
        super().__init__(parent)
        self._artists = artists
        self._staged: dict[tuple[str, ...], dict[str, Any]] = {}
        self._last_selection: tuple[str, ...] = ()
        self._value_cache: dict[str, list[str]] = {}
        self._values_requested = False
        self._library = library
        self._writer = writer
        self._analysis = analysis
        self._analysis_settings = analysis_settings
        self._jobs = jobs
        self._selected_ids = selected_ids
        self._player = player
        self._edit_targets: dict[str, tuple[_EditTarget, ...]] = {}
        self._drafts: dict[tuple[str, tuple[str, ...]], str | None] = {}
        self._pending: list[_EditBatch] = []
        self._active: _EditBatch | None = None
        self._save_state = "idle"
        self._save_message = ""
        self._retry_batch: _EditBatch | None = None
        self._undo_operations: list[str] = []
        self._undo_batch_operations: dict[str, tuple[str, ...]] = {}
        self._successful_revisions: dict[str, SourceRevision] = {}
        self._waiting_for_release = ""
        self._recovery_operations: list[dict[str, Any]] = []
        self._inspection_cache: dict[
            tuple[str, int], tuple[MetadataSnapshot, dict[str, tuple[bool, str]]]
        ] = {}
        self._inspection_request = 0
        self._inspection_job_id: JobId | None = None
        self._inspection_targets: tuple[tuple[str, int], ...] = ()
        self.batchFinished.connect(self._on_batch_finished)
        self.recoveryChecked.connect(self._on_recovery_checked)
        self.inspectionFinished.connect(self._on_inspection_finished)
        self.valuesLoaded.connect(self._on_values_loaded)
        self._jobs.submit(self._inspect_recovery, label="Inspect metadata recovery", visible=False)
        if player is not None:
            player.trackAccessReleased.connect(self._on_track_access_released)

    @Property(str, notify=changed)
    def saveState(self) -> str:
        return self._save_state

    @Property(str, notify=changed)
    def saveMessage(self) -> str:
        return self._save_message

    @Property(bool, notify=changed)
    def canStopPlaybackAndSave(self) -> bool:
        if self._player is None or self._retry_batch is None:
            return False
        playing_id = self._player.playing_id_value()
        return any(target.track_id == playing_id for target in self._retry_batch.targets)

    @Property(bool, notify=changed)
    def canUndo(self) -> bool:
        return bool(self._undo_operations) and self._active is None

    @Property(list, notify=changed)
    def recoveryOperations(self) -> list[dict[str, Any]]:
        return list(self._recovery_operations)

    @Property(list, notify=changed)
    def infoFields(self) -> list[dict[str, Any]]:
        selected = tuple(self._selected_ids())
        sources = [self._library.source_record(track_id) for track_id in selected]
        sources = [source for source in sources if source is not None]
        return self._fields_for_sources(sources, selected)

    @Slot(str, result=list)
    def fieldsForTrack(self, track_id: str) -> list[dict[str, Any]]:
        source = self._library.source_record(track_id)
        if source is None:
            return []
        return self._fields_for_sources([source], (track_id,))

    @Slot()
    @Slot(str)
    def prepareTrackInspection(self, track_id: str = "") -> None:
        """Prepare the selected tags and edit capabilities away from the UI thread."""
        track_ids = [track_id] if track_id else list(self._selected_ids())
        self._inspection_request += 1
        request_id = self._inspection_request
        self._cancel_inspection_job()
        sources = [
            source
            for identity in dict.fromkeys(str(value) for value in track_ids)
            if (source := self._library.source_record(identity)) is not None
        ]
        targets = tuple((source.track_id, source.revision.generation) for source in sources)
        self._inspection_targets = targets
        missing = [
            source
            for source in sources
            if (source.track_id, source.revision.generation) not in self._inspection_cache
        ]
        if not missing:
            self.changed.emit()
            return

        def inspect(context: JobContext) -> None:
            results = []
            for source in missing:
                context.raise_if_cancelled()
                try:
                    revision, snapshot, capabilities = self._writer.inspect(source.track_id)
                    results.append((source.track_id, revision, snapshot, capabilities, ""))
                except JobCancelledError:
                    raise
                except Exception as error:
                    results.append((source.track_id, None, None, None, str(error)))
            self.inspectionFinished.emit(request_id, results)

        self._inspection_job_id = self._jobs.submit(
            inspect, label="Prepare metadata view", visible=False
        )
        self.changed.emit()

    @Slot()
    def cancelPendingInspection(self) -> None:
        """Discard and cancel a tag inspection when its panel is closed."""
        self._inspection_request += 1
        self._inspection_targets = ()
        self._cancel_inspection_job()

    def _cancel_inspection_job(self) -> None:
        if self._inspection_job_id is None:
            return
        with suppress(UnknownJobError, ValueError):
            self._jobs.cancel(self._inspection_job_id)
        self._inspection_job_id = None

    @Slot(int, object)
    def _on_inspection_finished(self, request_id: int, values: object) -> None:
        if request_id != self._inspection_request or not isinstance(values, list):
            return
        self._inspection_job_id = None
        self._inspection_targets = ()
        for track_id, revision, snapshot, capabilities, error in values:
            current = self._library.source_record(track_id)
            if current is None:
                continue
            if revision is not None and current.revision != revision:
                continue
            resolved_snapshot = (
                snapshot if isinstance(snapshot, MetadataSnapshot) else current.snapshot
            )
            resolved_capabilities = (
                capabilities
                if isinstance(capabilities, dict)
                else {
                    field: (False, f"Could not inspect tags: {error}")
                    for field in EDITABLE_METADATA_FIELDS
                }
            )
            self._inspection_cache[(track_id, current.revision.generation)] = (
                resolved_snapshot,
                resolved_capabilities,
            )
        self.changed.emit()

    def _cached_inspection(
        self, source: TrackSource
    ) -> tuple[MetadataSnapshot, dict[str, tuple[bool, str]]] | None:
        """Return the inspection of a track, or the last older one while a new one is prepared.

        A save changes the revision; what a file can accept does not change with it, so the
        fields stay editable instead of waiting for another inspection.
        """
        exact = self._inspection_cache.get((source.track_id, source.revision.generation))
        if exact is not None:
            return exact
        older = [
            generation
            for track_id, generation in self._inspection_cache
            if track_id == source.track_id and generation < source.revision.generation
        ]
        if not older:
            return None
        snapshot, capabilities = self._inspection_cache[(source.track_id, max(older))]
        return source.snapshot if source.snapshot is not None else snapshot, capabilities

    def _fields_for_sources(
        self, sources: list[TrackSource], selected: tuple[str, ...]
    ) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        inspected = [self._cached_inspection(source) for source in sources]
        capabilities_by_source = [
            result[1]
            if result is not None
            else {
                field: (False, "Tags are being prepared before editing is enabled.")
                for field in EDITABLE_METADATA_FIELDS
            }
            for result in inspected
        ]
        snapshots = [
            result[0] if result is not None else source.snapshot
            for source, result in zip(sources, inspected, strict=True)
        ]
        calculated = (
            self._analysis.get_many(source.track_id for source in sources)
            if self._analysis is not None
            else {}
        )
        for field in EDITABLE_METADATA_FIELDS:
            values = [
                self._displayed_values(field, source.track_id, snapshot, calculated)
                for source, snapshot in zip(sources, snapshots, strict=True)
            ]
            normalized = [" / ".join(value) for value in values]
            unique = set(normalized)
            value = normalized[0] if normalized else ""
            mixed = len(unique) > 1
            if mixed:
                value = ""
            draft_key = (field, selected)
            if draft_key in self._drafts:
                value = self._drafts[draft_key] or ""
            original = value
            staged = self._staged.get(selected, {}).get(field)
            if staged is not None and field != "artist":
                value = staged["text"]
            editable, reason = self._capability(field, sources, capabilities_by_source)
            fields.append(
                {
                    "key": field,
                    "label": _FIELD_LABELS[field],
                    "value": value,
                    "original": original,
                    "mixed": mixed and draft_key not in self._drafts and staged is None,
                    "editable": editable,
                    "reason": reason,
                    "dirty": staged is not None,
                    "error": staged["error"] if staged is not None and field != "artist" else "",
                }
            )
        return fields

    def _displayed_values(
        self,
        field: str,
        track_id: str,
        snapshot: MetadataSnapshot,
        calculated: dict[str, TrackAnalysis],
    ) -> tuple[str, ...]:
        """Return what the inspector shows: the calculated tempo/key unless the user edited it."""
        tag_values = tuple(getattr(snapshot, _FIELD_ATTRIBUTES[field]))
        if field not in {"bpm", "key"} or self._analysis_settings is None:
            return tag_values
        settings = self._analysis_settings()
        analysis = calculated.get(track_id)
        if field == "bpm":
            if analysis is not None and analysis.bpm is not None and not analysis.bpm_user_edited:
                return (format_bpm(analysis.bpm, settings.bpm_decimals),)
            return tag_values
        if analysis is not None and analysis.key is not None and not analysis.key_user_edited:
            return (analysis.key.text(settings.notation),)
        return tuple(format_key(value, settings.notation) for value in tag_values)

    def refresh_selection(self) -> None:
        """Refresh the displayed values; drafts remain bound to their captured UUIDs."""
        selection = self._selection()
        if selection != self._last_selection:
            if self._last_selection in self._staged:
                self.noticeRaised.emit(
                    "Unsaved tag changes were kept. Select the same tracks again to save them."
                )
            self._last_selection = selection
            self.stagingChanged.emit()
            self.artistsChanged.emit()
        self.changed.emit()

    # ---------------------------------------------------------------- staged changes

    def _selection(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(str(value) for value in self._selected_ids()))

    def _notation(self) -> str:
        if self._analysis_settings is None:
            return "camelot"
        return self._analysis_settings().notation

    def _protected(self) -> list[str]:
        if self._artists is None:
            return []
        try:
            return self._artists.protected_names()
        except Exception:
            return []

    def _selected_sources(self, selection: tuple[str, ...]) -> list[TrackSource]:
        sources = [self._library.source_record(track_id) for track_id in selection]
        return [source for source in sources if source is not None]

    def _snapshot_of(self, source: TrackSource) -> MetadataSnapshot:
        inspected = self._cached_inspection(source)
        return inspected[0] if inspected is not None else source.snapshot

    def _original_text(self, field: str, selection: tuple[str, ...]) -> tuple[str, bool]:
        """Return the shown value of a field and whether the selection disagrees on it."""
        sources = self._selected_sources(selection)
        calculated = (
            self._analysis.get_many(source.track_id for source in sources)
            if self._analysis is not None
            else {}
        )
        texts = {
            " / ".join(
                self._displayed_values(
                    field, source.track_id, self._snapshot_of(source), calculated
                )
            )
            for source in sources
        }
        if len(texts) > 1:
            return "", True
        return (next(iter(texts)) if texts else ""), False

    @Property(list, notify=stagingChanged)
    def dirtyFields(self) -> list[str]:
        staged = self._staged.get(self._selection(), {})
        return [field for field in EDITABLE_METADATA_FIELDS if field in staged]

    @Property(int, notify=stagingChanged)
    def changeCount(self) -> int:
        return len(self.dirtyFields)

    @Property(bool, notify=stagingChanged)
    def hasChanges(self) -> bool:
        return self.changeCount > 0

    @Property("QVariantMap", notify=stagingChanged)
    def fieldErrors(self) -> dict[str, str]:
        staged = self._staged.get(self._selection(), {})
        return {
            field: str(entry["error"])
            for field, entry in staged.items()
            if field != "artist" and entry["error"]
        }

    @Property(bool, notify=stagingChanged)
    def canSave(self) -> bool:
        return self.hasChanges and not self.fieldErrors

    @Slot(str, str)
    def stageField(self, field: str, text: str) -> None:
        """Keep what the user typed in a field; nothing is written until ``saveChanges``."""
        if field not in EDITABLE_METADATA_FIELDS or field == "artist":
            return
        selection = self._selection()
        if not selection:
            return
        original, mixed = self._original_text(field, selection)
        value, error = validate_field(field, text, self._notation())
        staged = self._staged.setdefault(selection, {})
        unchanged = (mixed and not text) or (not error and not mixed and value == original)
        if unchanged:
            staged.pop(field, None)
        else:
            staged[field] = {"text": text, "value": value, "error": error}
        if not staged:
            self._staged.pop(selection, None)
        self.stagingChanged.emit()

    @Slot(str)
    def revertField(self, field: str) -> None:
        selection = self._selection()
        staged = self._staged.get(selection)
        if staged is None or field not in staged:
            return
        del staged[field]
        if not staged:
            self._staged.pop(selection, None)
        self.stagingChanged.emit()
        self.artistsChanged.emit()
        self.changed.emit()

    @Slot()
    def revertAll(self) -> None:
        if self._staged.pop(self._selection(), None) is not None:
            self.stagingChanged.emit()
            self.artistsChanged.emit()
            self.changed.emit()

    # ---------------------------------------------------------------- artist credits

    def _base_artists(self, source: TrackSource, protected: list[str]) -> list[str]:
        values = self._snapshot_of(source).artist
        return dedupe_names(name for value in values for name in split_credit(value, protected))

    def _artist_ops(self, selection: tuple[str, ...]) -> dict[str, list[str]]:
        entry = self._staged.get(selection, {}).get("artist")
        if entry is None:
            return {"add": [], "remove": []}
        return {"add": list(entry["add"]), "remove": list(entry["remove"])}

    def _names_for(
        self, source: TrackSource, ops: dict[str, list[str]], protected: list[str]
    ) -> list[str]:
        removed = {normalize_key(name) for name in ops["remove"]}
        kept = [
            name
            for name in self._base_artists(source, protected)
            if normalize_key(name) not in removed
        ]
        return dedupe_names([*kept, *ops["add"]])

    @Property(list, notify=artistsChanged)
    def artistChips(self) -> list[dict[str, Any]]:
        """The artists of the selection after the staged edits, with how many tracks name each."""
        selection = self._selection()
        sources = self._selected_sources(selection)
        protected = self._protected()
        ops = self._artist_ops(selection)
        added = {normalize_key(name) for name in ops["add"]}
        chips: dict[str, dict[str, Any]] = {}
        for source in sources:
            for name in self._names_for(source, ops, protected):
                chip = chips.setdefault(
                    normalize_key(name),
                    {"name": name, "count": 0, "total": len(sources), "added": False},
                )
                chip["count"] += 1
                chip["added"] = normalize_key(name) in added
        return list(chips.values())

    def _set_artist_ops(self, selection: tuple[str, ...], ops: dict[str, list[str]]) -> None:
        staged = self._staged.setdefault(selection, {})
        if ops["add"] or ops["remove"]:
            staged["artist"] = {**ops, "error": "", "text": ""}
        else:
            staged.pop("artist", None)
        if not staged:
            self._staged.pop(selection, None)
        self.artistsChanged.emit()
        self.stagingChanged.emit()

    @Slot(str)
    def stageArtistAdd(self, name: str) -> None:
        selection = self._selection()
        cleaned = " ".join(str(name).split())
        if not cleaned or not selection:
            return
        key = normalize_key(cleaned)
        ops = self._artist_ops(selection)
        if key in {normalize_key(item) for item in ops["remove"]}:
            ops["remove"] = [item for item in ops["remove"] if normalize_key(item) != key]
        else:
            protected = self._protected()
            sources = self._selected_sources(selection)
            everywhere = all(
                key in {normalize_key(item) for item in self._base_artists(source, protected)}
                for source in sources
            )
            if not everywhere and key not in {normalize_key(item) for item in ops["add"]}:
                ops["add"].append(cleaned)
        self._set_artist_ops(selection, ops)

    @Slot(str)
    def stageArtistRemove(self, name: str) -> None:
        selection = self._selection()
        key = normalize_key(name)
        if not key or not selection:
            return
        ops = self._artist_ops(selection)
        if key in {normalize_key(item) for item in ops["add"]}:
            ops["add"] = [item for item in ops["add"] if normalize_key(item) != key]
        elif key not in {normalize_key(item) for item in ops["remove"]}:
            ops["remove"].append(" ".join(str(name).split()))
        self._set_artist_ops(selection, ops)

    @Slot(str, result=list)
    def artistSuggestions(self, query: str) -> list[dict[str, Any]]:
        if self._artists is None or not query.strip():
            return []
        try:
            found = self._artists.suggestions(query, 8)
        except Exception:
            return []
        shown = {normalize_key(chip["name"]) for chip in self.artistChips}
        return [item for item in found if normalize_key(str(item["name"])) not in shown]

    @Slot(str, result=list)
    def splitPreview(self, text: str) -> list[str]:
        """The names a typed credit would give; one name when it is a known artist."""
        return split_credit(text, self._protected())

    # --------------------------------------------------------- album and genre values

    @Slot(str, str, result=list)
    def valueSuggestions(self, field: str, query: str) -> list[str]:
        """Values already used in the library for ``field``, filtered by ``query``."""
        if field not in {"album", "genre"} or not query.strip():
            return []
        if not self._values_requested:
            self._values_requested = True

            def load(_context: JobContext) -> None:
                self.valuesLoaded.emit(
                    {name: self._library.tag_values(name) for name in ("album", "genre")}
                )

            with suppress(RuntimeError):
                self._jobs.submit(load, label="Load tag values", visible=False)
        needle = query.strip().casefold()
        return [
            value
            for value in self._value_cache.get(field, [])
            if needle in value.casefold() and value.casefold() != needle
        ][:6]

    @Slot(object)
    def _on_values_loaded(self, values: object) -> None:
        if isinstance(values, dict):
            self._value_cache = {str(key): list(items) for key, items in values.items()}
            self.valuesChanged.emit()

    def _inspect_recovery(self, context: JobContext) -> None:
        try:
            context.raise_if_cancelled()
            operations = self._writer.incomplete_operations()
            summaries = [
                {
                    "operationId": str(operation.get("operation_id", "")),
                    "trackId": str(operation.get("track_id", "")),
                    "fileName": Path(str(operation.get("source_path", ""))).name,
                    "situation": str(operation.get("recovery_situation", "inspect_paths")),
                    "error": str(operation.get("error", "")),
                }
                for operation in operations
            ]
        except Exception as error:
            summaries = [
                {
                    "operationId": "",
                    "fileName": "",
                    "situation": "inspection_failed",
                    "error": f"{type(error).__name__}: {error}",
                }
            ]
        self.recoveryChecked.emit(summaries)

    @Slot(object)
    def _on_recovery_checked(self, operations: object) -> None:
        if isinstance(operations, list):
            self._recovery_operations = [item for item in operations if isinstance(item, dict)]
        self.changed.emit()

    @Slot(str)
    def begin_field_edit(self, field: str) -> None:
        if field not in EDITABLE_METADATA_FIELDS:
            return
        self._capture_targets(field, f"selection:{field}", self._selected_ids())

    @Slot(str, str)
    def beginTrackFieldEdit(self, track_id: str, field: str) -> None:
        if field not in EDITABLE_METADATA_FIELDS:
            return
        self._capture_targets(field, f"track:{track_id}:{field}", [track_id])

    def _capture_targets(self, field: str, context_key: str, track_ids: list[str]) -> None:
        targets: list[_EditTarget] = []
        for track_id in track_ids:
            source = self._library.source_record(track_id)
            if source is not None:
                targets.append(_EditTarget(track_id, source.revision))
        self._edit_targets[context_key] = tuple(targets)

    @Slot(str, str, bool)
    def commit_field(self, field: str, value: str, remove: bool = False) -> None:
        self._commit_field(field, value, remove, f"selection:{field}")

    @Slot(str, str, str, bool)
    def commitTrackField(self, track_id: str, field: str, value: str, remove: bool = False) -> None:
        self._commit_field(field, value, remove, f"track:{track_id}:{field}")

    def _commit_field(self, field: str, value: str, remove: bool, context_key: str) -> None:
        if field not in EDITABLE_METADATA_FIELDS:
            return
        targets = self._edit_targets.pop(context_key, ())
        if not targets:
            track_ids = (
                self._selected_ids()
                if context_key.startswith("selection:")
                else [context_key.split(":", maxsplit=2)[1]]
            )
            self._capture_targets(field, context_key, track_ids)
            targets = self._edit_targets.pop(context_key, ())
        if not targets:
            return
        committed_value = None if remove else value
        selected = tuple(target.track_id for target in targets)
        self._drafts[(field, selected)] = committed_value
        batch = _EditBatch(
            batch_id=str(uuid.uuid4()),
            draft_id=str(uuid.uuid4()),
            field=field,
            value=committed_value,
            targets=targets,
            draft_selection=selected,
        )
        self._retry_batch = None
        self._pending.append(batch)
        if self._active is None:
            self._start_next()
        else:
            self._save_state = "saving"
            self._save_message = ""
            self.changed.emit()

    @Slot()
    def saveChanges(self) -> None:
        """Write every staged change of the selection, one file rewrite per track."""
        selection = self._selection()
        staged = self._staged.get(selection)
        if not staged or not self.canSave:
            return
        self._capture_targets("*", "selection:*", list(selection))
        targets = self._edit_targets.pop("selection:*", ())
        if not targets:
            return
        protected = self._protected()
        sources = {source.track_id: source for source in self._selected_sources(selection)}
        artist_names: tuple[tuple[str, tuple[str, ...]], ...] = ()
        if "artist" in staged:
            ops = self._artist_ops(selection)
            artist_names = tuple(
                (target.track_id, tuple(self._names_for(sources[target.track_id], ops, protected)))
                for target in targets
                if target.track_id in sources
            )
        changes = tuple(
            (field, entry["value"] or None) for field, entry in staged.items() if field != "artist"
        )
        batch = _EditBatch(
            batch_id=str(uuid.uuid4()),
            draft_id=str(uuid.uuid4()),
            field="*",
            value=None,
            targets=targets,
            draft_selection=selection,
            changes=changes,
            artist_names=artist_names,
            staged=tuple((field, copy.deepcopy(entry)) for field, entry in staged.items()),
        )
        self._retry_batch = None
        self._pending.append(batch)
        if self._active is None:
            self._start_next()
        else:
            self._save_state = "saving"
            self._save_message = ""
            self.changed.emit()

    @Slot()
    def finish_save(self) -> None:
        if self._save_state == "saved":
            self._save_state = "idle"
            self._save_message = ""
            self.changed.emit()

    @Slot()
    def retry_save(self) -> None:
        if self._retry_batch is None or self._active is not None:
            return
        self._pending.insert(0, self._retry_batch)
        self._retry_batch = None
        self._start_next()

    @Slot()
    def retrySave(self) -> None:
        self.retry_save()

    @Slot()
    def stop_playback_and_save(self) -> None:
        if self._player is None or self._retry_batch is None:
            return
        playing_id = self._player.playing_id_value()
        if not playing_id or not any(
            target.track_id == playing_id for target in self._retry_batch.targets
        ):
            self.retry_save()
            return
        self._waiting_for_release = playing_id
        self._save_message = "Stopping playback before saving…"
        self.changed.emit()
        if not self._player.stopAndRelease(playing_id):
            self._waiting_for_release = ""
            self.retry_save()

    @Slot()
    def stopPlaybackAndSave(self) -> None:
        self.stop_playback_and_save()

    @Slot(str)
    def _on_track_access_released(self, track_id: str) -> None:
        if track_id == self._waiting_for_release:
            self._waiting_for_release = ""
            self.retry_save()

    @Slot()
    def undo_save(self) -> None:
        if not self._undo_operations or self._active is not None:
            self._save_state = "error"
            self._save_message = "There is no verified save available to undo."
            self.changed.emit()
            return
        operation_ids = tuple(self._undo_operations)
        batch_id = str(uuid.uuid4())
        draft_id = str(uuid.uuid4())
        self._save_state = "saving"
        self._save_message = "Undoing the last verified save…"
        self.changed.emit()

        def run(context: JobContext) -> None:
            results: list[MetadataEditResult] = []
            for index, operation_id in enumerate(operation_ids):
                try:
                    context.raise_if_cancelled()
                    undone = self._writer.undo(operation_id, draft_id)
                    results.append(undone)
                    if undone.status == "saved" and undone.snapshot is not None:
                        self._sync_artists(
                            undone,
                            dedupe_names(
                                name
                                for value in undone.snapshot.artist
                                for name in split_credit(value, self._protected())
                            ),
                        )
                    context.report_progress((index + 1) / len(operation_ids))
                    context.report_items(index + 1, len(operation_ids), "Undo")
                except Exception as error:
                    results.append(
                        MetadataEditResult(
                            "",
                            "failed",
                            f"Undo stopped: {type(error).__name__}: {error}",
                            operation_id,
                        )
                    )
                    results.extend(
                        MetadataEditResult(
                            "", "failed", "Undo stopped before this file was processed.", rest
                        )
                        for rest in operation_ids[index + 1 :]
                    )
                    break
            self.batchFinished.emit(batch_id, results)

        self._active = _EditBatch(batch_id, draft_id, "", None, (), ())
        self._undo_batch_operations[batch_id] = operation_ids
        self._jobs.submit(run, label="Undo metadata edit")

    @Slot()
    def undoSave(self) -> None:
        self.undo_save()

    def _start_next(self) -> None:
        if self._active is not None or not self._pending:
            return
        batch = self._pending.pop(0)
        targets: list[_EditTarget] = []
        for target in batch.targets:
            recent_revision = self._successful_revisions.get(target.track_id)
            source = self._library.source_record(target.track_id)
            if (
                recent_revision is not None
                and source is not None
                and source.revision.generation == recent_revision.generation
                and source.revision.matches(recent_revision)
            ):
                target = _EditTarget(target.track_id, recent_revision)
            targets.append(target)
        batch = replace(batch, targets=tuple(targets))
        self._active = batch
        self._save_state = "saving"
        self._save_message = "Saving…"
        self.changed.emit()

        def run(context: JobContext) -> None:
            results: list[MetadataEditResult] = []
            total = max(1, len(batch.targets))
            for index, target in enumerate(batch.targets):
                try:
                    context.raise_if_cancelled()
                    if batch.is_staged:
                        fields = dict(batch.changes)
                        names = dict(batch.artist_names).get(target.track_id)
                        if names is not None:
                            fields["artist"] = serialize_artists(names) or None
                        patch = MetadataPatch.from_mapping(
                            fields, replace_aliases="artist" in fields
                        )
                        edited = set(fields)
                    else:
                        patch = MetadataPatch.one(batch.field, batch.value)
                        names = None
                        edited = {batch.field}
                    saved = self._writer.save(
                        target.track_id,
                        target.revision,
                        patch,
                        batch.draft_id,
                    )
                    results.append(saved)
                    if saved.status == "saved" and self._analysis is not None:
                        for field in sorted(edited & {"bpm", "key"}):
                            # An edit made by the user protects that value from analysis.
                            self._analysis.mark_user_edited([target.track_id], field)
                    if saved.status == "saved" and names is not None:
                        self._sync_artists(saved, names)
                    context.report_progress((index + 1) / total)
                    context.report_items(
                        index + 1, len(batch.targets), "tags" if batch.is_staged else batch.field
                    )
                    if saved.status != "saved":
                        context.report_failure(target.track_id, saved.message or saved.status)
                except Exception as error:
                    results.append(
                        MetadataEditResult(
                            target.track_id,
                            "failed",
                            f"Save stopped: {type(error).__name__}: {error}",
                        )
                    )
                    results.extend(
                        MetadataEditResult(
                            remaining.track_id,
                            "failed",
                            "Save stopped before this file was processed.",
                        )
                        for remaining in batch.targets[index + 1 :]
                    )
                    break
            self.batchFinished.emit(batch.batch_id, results)

        self._jobs.submit(run, label="Save metadata")

    @Slot(str, object)
    def _on_batch_finished(self, batch_id: str, raw_results: object) -> None:
        batch = self._active
        if batch is None or batch.batch_id != batch_id:
            return
        results = list(raw_results) if isinstance(raw_results, list) else []
        self._active = None
        successful = [item for item in results if item.status == "saved"]
        failed = [item for item in results if item.status != "saved"]
        if not batch.field:
            operation_ids = self._undo_batch_operations.pop(batch.batch_id, ())
            self._undo_operations = [
                operation_id
                for operation_id, result in zip(operation_ids, results, strict=False)
                if result.status != "saved"
            ]
            self._retry_batch = None
            self._save_state = "saved" if not failed else "error"
            self._save_message = (
                "Undo completed." if not failed else "; ".join(item.message for item in failed)
            )
            self._seed_inspections(successful)
            if successful:
                self.sourceChanged.emit()
            self.changed.emit()
            if self._pending:
                self._start_next()
            return
        self._undo_operations = [item.operation_id for item in successful if item.operation_id]
        for result in successful:
            if result.revision is not None:
                self._successful_revisions[result.track_id] = result.revision
        self._seed_inspections(successful)
        if batch.is_staged and not failed:
            self._clear_staged(batch)

        draft_key = (batch.field, batch.draft_selection)
        newer_same_draft = any(
            queued.field == batch.field and queued.draft_selection == batch.draft_selection
            for queued in self._pending
        )
        if not failed and not newer_same_draft and self._drafts.get(draft_key) == batch.value:
            self._drafts.pop(draft_key, None)

        if failed:
            self._save_state = "busy" if all(item.status == "busy" for item in failed) else "error"
            details = "; ".join(dict.fromkeys(item.message for item in failed if item.message))
            self._save_message = (
                f"Saved {len(successful)} of {len(results)} tracks. {details}"
                if successful
                else details or "Could not save the metadata."
            )
            self._retry_batch = replace(
                batch,
                batch_id=str(uuid.uuid4()),
                targets=tuple(
                    target
                    for target, result in zip(batch.targets, results, strict=False)
                    if result.status != "saved"
                ),
            )
        else:
            self._save_state = "saved"
            self._save_message = (
                f"Saved changes to {len(successful)} track(s)." if len(successful) > 1 else "Saved."
            )
            self._retry_batch = None
        if successful:
            self.sourceChanged.emit()
        self.changed.emit()
        if self._pending:
            self._start_next()

    def _sync_artists(self, saved: MetadataEditResult, names: Sequence[str]) -> None:
        """Make the credit just written the confirmed credit of the track in the catalog."""
        if self._artists is None:
            return
        title = None
        if saved.snapshot is not None and saved.snapshot.title:
            title = saved.snapshot.title[0]
        try:
            self._artists.sync_tags(saved.track_id, list(names), title)
        except Exception as error:
            self.noticeRaised.emit(f"The artists catalog could not be updated: {error}")
            return
        self.artistsSynced.emit()

    def _seed_inspections(self, saved: list[MetadataEditResult]) -> None:
        """Carry what a file accepts over to its new revision, so editing never waits."""
        for result in saved:
            if result.revision is None or result.snapshot is None:
                continue
            older = [
                generation
                for track_id, generation in self._inspection_cache
                if track_id == result.track_id and generation < result.revision.generation
            ]
            if older:
                capabilities = self._inspection_cache[(result.track_id, max(older))][1]
                self._inspection_cache[(result.track_id, result.revision.generation)] = (
                    result.snapshot,
                    capabilities,
                )

    def _clear_staged(self, batch: _EditBatch) -> None:
        """Drop the staged fields that were just saved, unless they were edited since."""
        current = self._staged.get(batch.draft_selection)
        if current is None:
            return
        for field, entry in batch.staged:
            if current.get(field) == entry:
                del current[field]
        if not current:
            self._staged.pop(batch.draft_selection, None)
        self.stagingChanged.emit()
        self.artistsChanged.emit()

    @staticmethod
    def _capability(
        field: str,
        sources: list[TrackSource],
        capabilities_by_source: list[dict[str, tuple[bool, str]]],
    ) -> tuple[bool, str]:
        if not sources:
            return False, "Select a track to edit its tags."
        if any(source.status != "readable" for source in sources):
            return False, "Unreadable audio files are read-only."
        reasons: list[str] = []
        for source, capabilities in zip(sources, capabilities_by_source, strict=True):
            if source.status != "readable":
                reasons.append("Unreadable audio files are read-only.")
                continue
            editable, reason = capabilities.get(
                field, (False, "Writing is not verified for this field.")
            )
            if editable:
                return True, ""
            reasons.append(reason)
        return False, next(
            (reason for reason in reasons if reason), "No selected file is editable."
        )
