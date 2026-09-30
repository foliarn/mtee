"""Conflict-aware metadata writes on verified neighboring copies."""

from __future__ import annotations

import os
import shutil
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.metadata_edit import EDITABLE_METADATA_FIELDS, MetadataEditResult, MetadataPatch
from mtee.domain.tracks import SourceRevision, sha256_of_file
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.metadata_history_repository import (
    MetadataHistoryRepository,
    RepositoryRevisionConflictError,
)
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError
from mtee.services.file_replacement import FileReplacement
from mtee.services.metadata_adapters import Id3WaveAdapter
from mtee.services.metadata_adapters.base import MetadataAdapter
from mtee.services.metadata_adapters.mp4 import MP4MetadataAdapter
from mtee.services.metadata_adapters.vorbis import VorbisCommentAdapter
from mtee.services.metadata_reader import MetadataReader

__all__ = ["MetadataEditService"]

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


class MetadataEditService:
    """Edit metadata only through a format adapter with preservation checks."""

    def __init__(
        self,
        library: LibraryRepository,
        history: MetadataHistoryRepository,
        file_access: FileAccessCoordinator,
        *,
        reader: MetadataReader | None = None,
        replacement: FileReplacement | None = None,
        adapters: tuple[MetadataAdapter, ...] | None = None,
    ) -> None:
        self._library = library
        self._history = history
        self._file_access = file_access
        self._reader = reader or MetadataReader()
        self._replacement = replacement or FileReplacement()
        self._adapters = adapters or (
            Id3WaveAdapter(),
            VorbisCommentAdapter(),
            MP4MetadataAdapter(),
        )

    def capabilities(self, track_id: str) -> dict[str, tuple[bool, str]]:
        source = self._library.source_record(track_id)
        if source is None:
            return self._unsupported("This track is no longer in the library.")
        if self._history.has_incomplete_for_track(track_id):
            return self._unsupported(
                "A previous save needs recovery. Inspect its recovery files before editing."
            )
        adapter = self._adapter_for(source.path)
        if adapter is None:
            reason = self._unsupported_format_reason(source.path)
            return self._unsupported(reason)
        return adapter.capabilities(source.path)

    def tag_conflicts(self, track_id: str, fields: Any) -> dict[str, tuple[str, ...]]:
        """Return the fields of ``track_id`` stored under several tag names or values.

        Such a field cannot be edited in place; writing it with
        ``replace_aliases`` deletes the old names and values first. Formats without
        that ambiguity report nothing.
        """
        source = self._library.source_record(track_id)
        if source is None:
            return {}
        adapter = self._adapter_for(source.path)
        finder = getattr(adapter, "alias_conflicts", None)
        if finder is None:
            return {}
        return finder(source.path, tuple(fields))

    def inspect(self, track_id: str):
        """Read tags and edit capabilities for the current catalog revision."""
        source = self._library.source_record(track_id)
        if source is None:
            raise FileNotFoundError("This track is no longer in the library.")
        before = SourceRevision.observe(source.path, generation=source.revision.generation)
        if not source.revision.matches(before):
            raise ValueError("The source changed. Rescan it before editing its tags.")
        snapshot = self._reader.read(source.path)
        adapter = self._adapter_for(source.path)
        if snapshot.status != "readable":
            capabilities = self._unsupported("This audio file could not be inspected safely.")
        elif adapter is None:
            capabilities = self._unsupported(self._unsupported_format_reason(source.path))
        else:
            capabilities = adapter.capabilities(source.path)
        after = SourceRevision.observe(source.path, generation=source.revision.generation)
        if not before.matches(after):
            raise ValueError("The source changed while its tags were being inspected.")
        return source.revision, snapshot, capabilities

    def save(
        self,
        track_id: str,
        expected_revision: SourceRevision,
        patch: MetadataPatch,
        draft_id: str,
    ) -> MetadataEditResult:
        try:
            with self._file_access.acquire(
                _parse_track_id(track_id), "metadata edit", timeout_seconds=0
            ):
                return self._save_locked(track_id, expected_revision, patch, draft_id)
        except FileAccessTimeoutError:
            return MetadataEditResult(
                track_id, "busy", "Stop playback or wait for the file to become available."
            )

    def undo(self, operation_id: str, draft_id: str) -> MetadataEditResult:
        operation = self._history.get(operation_id)
        if operation is None or operation["status"] != "completed" or operation["undo_of"]:
            return MetadataEditResult("", "failed", "This save is no longer available to undo.")
        track_id = str(operation["track_id"])
        source = self._library.source_record(track_id)
        if source is None:
            return MetadataEditResult(
                track_id, "conflict", "The track is no longer in the library."
            )
        patch_values = {key: value for key, value in operation["before"].items()}
        patch = MetadataPatch.from_mapping(patch_values)
        try:
            with self._file_access.acquire(
                _parse_track_id(track_id), "metadata undo", timeout_seconds=0
            ):
                current = self._reader.read(source.path)
                for field, expected in operation["after"].items():
                    current_values = _field_values(current, field)
                    expected_values = () if expected is None else (expected,)
                    if current_values != expected_values:
                        return MetadataEditResult(
                            track_id,
                            "conflict",
                            "The file changed after this save; Undo will not overwrite it.",
                            operation_id,
                        )
                return self._save_locked(
                    track_id,
                    source.revision,
                    patch,
                    draft_id,
                    undo_of=operation_id,
                )
        except FileAccessTimeoutError:
            return MetadataEditResult(
                track_id, "busy", "Stop playback or wait for the file to become available."
            )

    def incomplete_operations(self) -> list[dict[str, Any]]:
        """Return durable edits that require inspection after interruption."""
        results = []
        for operation in self._history.incomplete():
            path = Path(str(operation["source_path"]))
            temporary = Path(str(operation["temporary_path"]))
            backup = Path(str(operation["backup_path"]))
            current_hash = _hash_if_file(path)
            if current_hash and current_hash == operation.get("new_sha256"):
                situation = "replacement_present"
            elif path.is_file() and backup.is_file():
                situation = "source_and_backup_present"
            elif path.is_file() and temporary.is_file():
                situation = "temporary_not_published"
            else:
                situation = "inspect_paths"
            results.append({**operation, "recovery_situation": situation})
        return results

    def _save_locked(
        self,
        track_id: str,
        expected_revision: SourceRevision,
        patch: MetadataPatch,
        draft_id: str,
        *,
        undo_of: str = "",
    ) -> MetadataEditResult:
        source = self._library.source_record(track_id)
        if source is None:
            return MetadataEditResult(track_id, "failed", "The track is no longer in the library.")
        if source.status != "readable":
            return MetadataEditResult(
                track_id, "unsupported", "Unreadable sources cannot be edited."
            )
        if self._history.has_incomplete_for_track(track_id):
            return MetadataEditResult(
                track_id,
                "recovery",
                "A previous save needs recovery. Inspect its recovery files before editing.",
            )
        if (
            source.revision.generation != expected_revision.generation
            or not source.revision.matches(expected_revision)
        ):
            return MetadataEditResult(
                track_id, "conflict", "The source changed; reload its metadata before saving."
            )
        try:
            adapter = self._adapter_for(source.path)
            if adapter is None:
                return MetadataEditResult(
                    track_id, "unsupported", self._unsupported_format_reason(source.path)
                )
            capabilities = adapter.capabilities(source.path, replace_aliases=patch.replace_aliases)
            unsupported = [
                (field, capabilities.get(field, (False, "Unknown metadata field."))[1])
                for field, _value in patch.changes
                if not capabilities.get(field, (False, "Unknown metadata field."))[0]
            ]
            if unsupported:
                return MetadataEditResult(track_id, "unsupported", unsupported[0][1])
            audio_before, reason = adapter.inspect(source.path)
            if reason or audio_before is None:
                return MetadataEditResult(track_id, "unsupported", reason or "Unsupported audio.")
        except Exception as error:
            return MetadataEditResult(track_id, "unsupported", str(error))

        operation_id = str(uuid.uuid4())
        source_path = source.path
        temporary_path = source_path.with_name(
            f".{source_path.name}.mtee-edit-{operation_id}.tmp{source_path.suffix}"
        )
        backup_path = source_path.with_name(f".{source_path.name}.mtee-edit-{operation_id}.bak")
        source_digest = ""
        new_digest = ""
        replacement_published = False
        before_snapshot = self._reader.read(source_path)
        before_values = {
            field: _single_value(before_snapshot, field) for field, _value in patch.changes
        }
        after_values: dict[str, str | None] = {}
        for field, value in patch.changes:
            if value is None:
                after_values[field] = None
            elif field == "track_number":
                existing = before_values[field]
                after_values[field] = _keep_track_total(value, existing)
            else:
                after_values[field] = value

        try:
            observed = SourceRevision.observe(source_path, generation=source.revision.generation)
            if not source.revision.matches(observed):
                return MetadataEditResult(
                    track_id, "conflict", "The source changed since its last library scan."
                )
            source_digest = sha256_of_file(source_path)
            self._history.create(
                operation_id=operation_id,
                draft_id=draft_id,
                track_id=track_id,
                source_path=source_path,
                revision=source.revision,
                source_sha256=source_digest,
                temporary_path=temporary_path,
                backup_path=backup_path,
                before=before_values,
                after=after_values,
                undo_of=undo_of,
            )
            self._copy_new_file(source_path, temporary_path)
            prepared_audio, preserved = adapter.prepare(temporary_path, patch)
            adapter.save(prepared_audio, temporary_path)
            adapter.verify(temporary_path, preserved, patch)
            after_snapshot = self._reader.read(temporary_path)
            if after_snapshot.status != "readable":
                raise ValueError("The edited copy could not be read back as audio.")
            after_values = {
                field: _single_value(after_snapshot, field) for field, _value in patch.changes
            }
            new_digest = sha256_of_file(temporary_path)
            latest = SourceRevision.observe(source_path, generation=source.revision.generation)
            if not source.revision.matches(latest) or sha256_of_file(source_path) != source_digest:
                self._history.set_status(
                    operation_id, "conflict", error="The source changed before replacement."
                )
                return MetadataEditResult(
                    track_id,
                    "conflict",
                    "The source changed while the edit was prepared; no replacement was made.",
                    operation_id,
                )
            self._history.set_status(
                operation_id,
                "publishing",
                new_sha256=new_digest,
                after=after_values,
            )
            self._replacement.publish(temporary_path, source_path, backup_path)
            replacement_published = True
            new_revision = SourceRevision.observe(
                source_path, generation=source.revision.generation + 1
            )
            final_digest = sha256_of_file(source_path)
            if final_digest != new_digest:
                raise ValueError("The published audio bytes do not match the verified temporary.")
            final_snapshot = self._reader.read(source_path)
            if final_snapshot.status != "readable":
                raise ValueError("The published audio file cannot be read back.")
            self._history.set_status(operation_id, "published", new_sha256=new_digest)
            self._history.complete(
                operation_id=operation_id,
                track_id=track_id,
                path=source_path,
                expected_revision=source.revision,
                new_revision=new_revision,
                snapshot=final_snapshot,
                new_sha256=new_digest,
                undo_of=undo_of,
            )
            with suppress(OSError):
                backup_path.unlink()
            return MetadataEditResult(
                track_id,
                "saved",
                operation_id=operation_id,
                revision=new_revision,
                snapshot=final_snapshot,
                before=tuple(before_values.items()),
                after=tuple(after_values.items()),
            )
        except RepositoryRevisionConflictError as error:
            with suppress(Exception):
                self._history.set_status(operation_id, "needs_recovery", error=str(error))
            return MetadataEditResult(track_id, "recovery", str(error), operation_id)
        except Exception as error:
            published_bytes_observed = _hash_matches(source_path, new_digest)
            backup_matches_source = _hash_matches(backup_path, source_digest)
            replacement_published = (
                replacement_published or published_bytes_observed or backup_matches_source
            )
            status = "needs_recovery" if replacement_published else "failed"
            with suppress(Exception):
                self._history.set_status(
                    operation_id, status, error=f"{type(error).__name__}: {error}"
                )
            if not replacement_published:
                with suppress(OSError):
                    temporary_path.unlink()
            return MetadataEditResult(
                track_id,
                "recovery" if replacement_published else "failed",
                f"{type(error).__name__}: {error}",
                operation_id,
            )

    @staticmethod
    def _copy_new_file(source: Path, temporary: Path) -> None:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with source.open("rb") as input_file, os.fdopen(descriptor, "wb") as output_file:
                descriptor = -1
                shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
                output_file.flush()
                os.fsync(output_file.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _adapter_for(self, path: Path) -> MetadataAdapter | None:
        return next((adapter for adapter in self._adapters if adapter.supports_path(path)), None)

    @staticmethod
    def _unsupported_format_reason(path: Path) -> str:
        if path.suffix.casefold() in {".aac", ".adts"}:
            return (
                "AAC/ADTS metadata editing is unavailable because a safe tag round-trip "
                "has not been verified."
            )
        return "Metadata writing has not been verified for this audio format."

    @staticmethod
    def _unsupported(reason: str) -> dict[str, tuple[bool, str]]:
        return {field: (False, reason) for field in EDITABLE_METADATA_FIELDS}


def _parse_track_id(value: str) -> Any:
    from mtee.domain.tracks import TrackId

    return TrackId.parse(value)


def _field_values(snapshot: MetadataSnapshot, field: str) -> tuple[str, ...]:
    return getattr(snapshot, _FIELD_ATTRIBUTES[field])


def _single_value(snapshot: MetadataSnapshot, field: str) -> str | None:
    values = _field_values(snapshot, field)
    return values[0] if len(values) == 1 else None


def _keep_track_total(value: str, previous: str | None) -> str:
    if "/" in value or previous is None or "/" not in previous:
        return value
    return f"{value}/{previous.split('/', maxsplit=1)[1]}"


def _hash_matches(path: Path, expected: str) -> bool:
    if not expected:
        return False
    try:
        return _hash_if_file(path) == expected
    except OSError:
        return False


def _hash_if_file(path: Path) -> str:
    try:
        return sha256_of_file(path) if path.is_file() else ""
    except OSError:
        return ""
