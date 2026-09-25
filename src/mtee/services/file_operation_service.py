"""Previewed, no-overwrite renames, moves, and verified copies."""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from mtee.domain.file_operations import (
    FileOperationPreview,
    FileOperationResult,
    FileOperationTarget,
    now_utc,
)
from mtee.domain.tracks import SourceRevision, sha256_of_file
from mtee.persistence.file_operation_repository import (
    FileOperationJournalConflictError,
    FileOperationRepository,
)
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError
from mtee.services.metadata_reader import MetadataReader
from mtee.services.platform.windows_file_ops import (
    FileOperationAdapter,
    FileOperationCancelledError,
    FileOperationNativeError,
    FileOperationRecoveryError,
    WindowsFileOps,
)

__all__ = ["FileOperationService"]

_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class FileOperationService:
    """Implement reversible moves without overwriting library or external data."""

    def __init__(
        self,
        library: LibraryRepository,
        history: FileOperationRepository,
        file_access: FileAccessCoordinator,
        *,
        platform_ops: FileOperationAdapter | None = None,
        reader: MetadataReader | None = None,
    ) -> None:
        self._library = library
        self._history = history
        self._file_access = file_access
        self._platform = platform_ops or WindowsFileOps()
        self._reader = reader or MetadataReader()

    def preview(
        self, kind: str, track_ids: list[str] | tuple[str, ...], destination_or_name: str
    ) -> FileOperationPreview:
        preview_id = str(uuid.uuid4())
        if kind not in {"rename", "move", "copy", "trash"}:
            return FileOperationPreview(
                preview_id,
                kind,
                destination_or_name,
                (),
                now_utc(),
            )
        targets = tuple(
            self._preview_target(kind, track_id, destination_or_name) for track_id in track_ids
        )
        return FileOperationPreview(
            preview_id,
            kind,
            destination_or_name,
            targets,
            now_utc(),
        )

    def execute_target(
        self,
        kind: str,
        target: FileOperationTarget,
        *,
        undo_of: str = "",
        is_cancelled: Callable[[], bool] | None = None,
        report_progress: Callable[[int, int], None] | None = None,
    ) -> FileOperationResult:
        if target.status != "ready":
            return FileOperationResult(
                target.track_id,
                "",
                target.status,
                target.message,
                target.source,
                target.destination,
            )
        action = {
            "copy": "copying",
            "move": "moving",
            "undo_move": "moving",
            "rename": "renaming",
        }.get(kind, "changing")
        try:
            with self._file_access.acquire(
                _track_id(target.track_id), f"file {kind}", timeout_seconds=0
            ):
                if kind == "copy":
                    return self._execute_copy_locked(
                        target,
                        is_cancelled=is_cancelled or (lambda: False),
                        report_progress=report_progress or (lambda _copied, _total: None),
                    )
                return self._execute_locked(
                    kind,
                    target,
                    undo_of=undo_of,
                    is_cancelled=is_cancelled or (lambda: False),
                    report_progress=report_progress or (lambda _copied, _total: None),
                )
        except FileAccessTimeoutError:
            return FileOperationResult(
                target.track_id,
                "",
                "busy",
                f"The file is in use. Stop playback or wait before {action} it.",
                target.source,
                target.destination,
            )

    def execute_preview(self, preview: FileOperationPreview) -> list[FileOperationResult]:
        if preview.kind == "trash":
            return [
                FileOperationResult(
                    target.track_id,
                    "",
                    "unsupported",
                    "Move to trash is disabled until strict Windows recycling is verified.",
                    target.source,
                    target.destination,
                )
                for target in preview.targets
            ]
        return [self.execute_target(preview.kind, target) for target in preview.targets]

    def undo_move(self, operation_id: str) -> FileOperationResult:
        operation = self._history.get(operation_id)
        if (
            operation is None
            or operation["status"] != "completed"
            or operation["undo_of"] is not None
        ):
            return FileOperationResult("", "", "failed", "This move is no longer undoable.")
        track_id = str(operation["track_id"])
        source = self._library.source_record(track_id)
        if source is None:
            return FileOperationResult(
                track_id, "", "conflict", "The track is no longer in the library."
            )
        expected_result = SourceRevision(
            size_bytes=int(operation["result_size_bytes"]),
            mtime_ns=int(operation["result_mtime_ns"]),
            file_id=operation["result_file_id"],
            generation=int(operation["result_generation"]),
        )
        destination = Path(str(operation["source_path"]))
        if (
            source.path.resolve(strict=False) != Path(str(operation["destination_path"]))
            or source.revision.generation != expected_result.generation
            or not source.revision.matches(expected_result)
        ):
            return FileOperationResult(
                track_id,
                "",
                "conflict",
                "The moved file changed after this operation; Undo will not overwrite it.",
                source.path,
                destination,
            )
        if _hash_or_empty(source.path) != str(operation["source_sha256"]):
            return FileOperationResult(
                track_id,
                "",
                "conflict",
                "The moved file content changed; Undo will not overwrite it.",
                source.path,
                destination,
            )
        if destination.exists() or destination.is_symlink():
            return FileOperationResult(
                track_id,
                "",
                "conflict",
                "The original path is occupied; Undo will not overwrite it.",
                source.path,
                destination,
            )
        target = self._preflight_destination(
            track_id,
            source.path,
            destination,
            source.revision,
        )
        return self.execute_target("undo_move", target, undo_of=operation_id)

    def incomplete_operations(self) -> list[dict[str, Any]]:
        results = []
        for operation in self._history.incomplete():
            source = Path(str(operation["source_path"]))
            destination = Path(str(operation["destination_path"]))
            recovery_value = operation.get("recovery_path")
            recovery_path = Path(str(recovery_value)) if recovery_value else None
            expected = SourceRevision(
                int(operation["expected_size_bytes"]),
                int(operation["expected_mtime_ns"]),
                operation["expected_file_id"],
                int(operation["expected_generation"]),
            )
            source_state = _journal_path_state(source, str(operation["source_sha256"]), expected)
            destination_revision = SourceRevision(
                expected.size_bytes, expected.mtime_ns, None, expected.generation
            )
            destination_state = _journal_path_state(
                destination,
                str(operation["source_sha256"]),
                destination_revision,
                check_revision=False,
            )
            recovery_state = (
                _journal_path_state(
                    recovery_path,
                    str(operation["source_sha256"]),
                    destination_revision,
                    check_revision=False,
                )
                if recovery_path
                else "missing"
            )
            source_matches = source_state == "matches"
            destination_matches = destination_state == "matches"
            recovery_matches = recovery_state == "matches"
            if source_matches and destination_matches:
                situation = "both_copies_present"
            elif recovery_matches:
                situation = "temporary_present"
            elif recovery_path is not None and recovery_state != "missing":
                situation = "temporary_changed"
            elif source_matches:
                situation = "source_present"
            elif destination_matches:
                situation = "destination_present"
            else:
                situation = "inspect_paths"
            results.append(
                {
                    **operation,
                    "source_state": source_state,
                    "destination_state": destination_state,
                    "recovery_state": recovery_state,
                    "recovery_situation": situation,
                }
            )
        for operation in self._history.incomplete_copies():
            source = Path(str(operation["source_path"]))
            destination = Path(str(operation["destination_path"]))
            temporary = Path(str(operation["temporary_path"]))
            expected_size = int(operation["expected_size_bytes"])
            expected_hash = str(operation["source_sha256"])
            source_state = _hash_path_state(source, expected_hash, expected_size)
            destination_state = _hash_path_state(destination, expected_hash, expected_size)
            temporary_state = _hash_path_state(temporary, expected_hash, expected_size)
            situation = (
                "verified_copy_published"
                if destination_state == "matches"
                else "verified_temporary_copy"
                if temporary_state == "matches"
                else "source_present"
                if source_state == "matches"
                else "inspect_paths"
            )
            results.append(
                {
                    **operation,
                    "kind": "copy",
                    "track_id": str(operation["source_track_id"]),
                    "recovery_path": str(temporary),
                    "source_state": source_state,
                    "destination_state": destination_state,
                    "recovery_state": temporary_state,
                    "recovery_situation": situation,
                }
            )
        return results

    def complete_recovery_to_destination(self, operation_id: str) -> FileOperationResult:
        """Finalize only a destination-only move whose bytes and old UUID still match."""
        operation = self._history.get(operation_id)
        if (
            operation is None
            or operation["status"] != "needs_recovery"
            or operation["undo_of"] is not None
        ):
            return FileOperationResult(
                "", operation_id, "conflict", "This file operation cannot be recovered here."
            )

        track_id = str(operation["track_id"])
        source = Path(str(operation["source_path"]))
        destination = Path(str(operation["destination_path"]))
        record = self._library.source_record(track_id)
        if record is None:
            return FileOperationResult(
                track_id, operation_id, "conflict", "The track is no longer in the library."
            )
        expected = SourceRevision(
            int(operation["expected_size_bytes"]),
            int(operation["expected_mtime_ns"]),
            operation["expected_file_id"],
            int(operation["expected_generation"]),
        )
        try:
            destination_registered = bool(self._library.registered_roots_for(destination))
        except OSError:
            destination_registered = False
        if (
            record.path.resolve(strict=False) != source.resolve(strict=False)
            or not record.revision.matches(expected)
            or source.exists()
            or source.is_symlink()
            or destination.is_symlink()
            or not destination.is_file()
            or not destination_registered
        ):
            return FileOperationResult(
                track_id,
                operation_id,
                "conflict",
                "The source, library record, or destination changed; inspect both paths manually.",
                source,
                destination,
            )

        expected_destination = SourceRevision(
            int(operation["expected_size_bytes"]),
            int(operation["expected_mtime_ns"]),
            None,
            int(operation["expected_generation"]),
        )
        try:
            state = _journal_path_state(
                destination,
                str(operation["source_sha256"]),
                expected_destination,
                check_revision=False,
            )
            if state != "matches":
                return FileOperationResult(
                    track_id,
                    operation_id,
                    "conflict",
                    f"The destination is {state}; no library reference was changed.",
                    source,
                    destination,
                )
            before_read = SourceRevision.observe(destination, generation=expected.generation + 1)
            metadata = self._reader.read(destination)
            after_read = SourceRevision.observe(destination, generation=expected.generation + 1)
            digest = sha256_of_file(destination)
            result_revision = SourceRevision.observe(
                destination, generation=expected.generation + 1
            )
        except OSError as error:
            return FileOperationResult(
                track_id,
                operation_id,
                "conflict",
                f"The destination could not be reverified: {error}",
                source,
                destination,
            )
        if (
            metadata.status != "readable"
            or not before_read.matches(after_read)
            or not after_read.matches(result_revision)
            or digest != str(operation["source_sha256"])
        ):
            return FileOperationResult(
                track_id,
                operation_id,
                "conflict",
                "The verified destination changed during recovery; "
                "no library reference was changed.",
                source,
                destination,
            )
        try:
            self._history.complete_recovery_from_destination(
                operation_id=operation_id,
                track_id=track_id,
                expected_revision=expected,
                destination=destination,
                result_revision=result_revision,
                metadata=metadata,
            )
        except (FileOperationJournalConflictError, OSError, ValueError) as error:
            return FileOperationResult(
                track_id,
                operation_id,
                "recovery",
                "The verified copy remains available, but its library reference "
                f"was not updated: {error}",
                source,
                destination,
            )
        return FileOperationResult(
            track_id,
            operation_id,
            "completed",
            "The verified destination is now linked to the original track.",
            source,
            destination,
            result_revision,
        )

    def latest_undoable_operation_id(self) -> str:
        operation = self._history.latest_undoable()
        return str(operation["operation_id"]) if operation is not None else ""

    def _preview_target(
        self, kind: str, track_id: str, destination_or_name: str
    ) -> FileOperationTarget:
        source = self._library.source_record(track_id)
        if source is None:
            return _blocked(track_id, "", "", "This track is no longer in the library.")
        if kind == "trash":
            return _blocked(
                track_id,
                source.path,
                source.path,
                "Move to trash is disabled until strict Windows recycling is verified.",
            )
        if source.status != "readable" or source.path.is_symlink() or not source.path.is_file():
            action = {"copy": "copied", "move": "moved", "rename": "renamed"}.get(kind, "changed")
            return _blocked(
                track_id, source.path, source.path, f"Only readable regular files can be {action}."
            )
        if kind == "rename":
            destination, name_error = _renamed_path(source.path, destination_or_name)
            if name_error:
                return _blocked(track_id, source.path, source.path, name_error)
        else:
            if not destination_or_name.strip():
                return _blocked(
                    track_id,
                    source.path,
                    source.path,
                    "Choose a destination folder before moving this file.",
                )
            directory = _local_path(destination_or_name)
            if not directory.is_dir():
                return _blocked(
                    track_id,
                    source.path,
                    directory / source.path.name,
                    "Choose an existing destination folder.",
                )
            destination = directory / source.path.name
        return self._preflight_destination(track_id, source.path, destination, source.revision)

    def _preflight_destination(
        self,
        track_id: str,
        source_path: Path,
        destination: Path,
        revision: SourceRevision,
    ) -> FileOperationTarget:
        try:
            source = source_path.resolve(strict=True)
            parent = destination.parent.resolve(strict=True)
            final = parent / destination.name
            observed = SourceRevision.observe(source, generation=revision.generation)
        except OSError as error:
            return _blocked(
                track_id, source_path, destination, f"Could not inspect the paths: {error}"
            )
        if not revision.matches(observed) or revision.generation != observed.generation:
            return _blocked(
                track_id, source, final, "The source changed; refresh the library before moving it."
            )
        same_normalized_path = os.path.normcase(os.path.abspath(source)) == os.path.normcase(
            os.path.abspath(final)
        )
        if same_normalized_path and str(final) == str(source):
            return _blocked(
                track_id, source, final, "The source and destination are the same path."
            )
        case_only = same_normalized_path and str(final) != str(source)
        if not case_only and (final.exists() or final.is_symlink()):
            return _blocked(track_id, source, final, "The destination already exists.")
        owner = self._library.path_owner(final)
        if owner is not None and owner != track_id:
            return _blocked(
                track_id, source, final, "Another library track already uses this path."
            )
        if not self._library.registered_roots_for(final):
            return _blocked(
                track_id,
                source,
                final,
                "The destination must stay inside a registered library root.",
            )
        try:
            os.stat(source)
            os.stat(parent)
        except OSError as error:
            return _blocked(
                track_id, source, final, f"Could not verify the destination volume: {error}"
            )
        if len(str(final)) >= 248:
            return _blocked(
                track_id,
                source,
                final,
                "This path is too long for the verified Windows move adapter.",
            )
        return FileOperationTarget(track_id, source, final, revision)

    def _execute_copy_locked(
        self,
        target: FileOperationTarget,
        *,
        is_cancelled: Callable[[], bool],
        report_progress: Callable[[int, int], None],
    ) -> FileOperationResult:
        if is_cancelled():
            return _result(target, "cancelled", "The copy was cancelled before it started.")
        source_record = self._library.source_record(target.track_id)
        if source_record is None:
            return _result(target, "conflict", "The track is no longer in the library.")
        if source_record.path.resolve(strict=False) != target.source.resolve(
            strict=False
        ) or not source_record.revision.matches(target.revision):
            return _result(target, "conflict", "The track moved or changed after the preview.")
        refreshed = self._preflight_destination(
            target.track_id, source_record.path, target.destination, source_record.revision
        )
        if refreshed.status != "ready":
            return _result(target, refreshed.status, refreshed.message)
        try:
            source_hash = sha256_of_file(source_record.path)
            if not source_record.revision.matches(
                SourceRevision.observe(
                    source_record.path, generation=source_record.revision.generation
                )
            ):
                return _result(target, "conflict", "The source changed during verification.")
        except OSError as error:
            return _result(target, "conflict", f"Could not verify the source: {error}")

        operation_id = str(uuid.uuid4())
        temporary = refreshed.destination.with_name(f".mtee-copy-{operation_id}.tmp")
        journal_created = False
        try:
            self._history.create_copy(
                operation_id=operation_id,
                target=refreshed,
                temporary=temporary,
                source_sha256=source_hash,
            )
            journal_created = True
            copy_method = getattr(self._platform, "copy_no_replace", None)
            if copy_method is None:
                raise FileOperationNativeError(
                    "This platform adapter does not support verified copy."
                )
            copy_method(
                refreshed.source,
                temporary,
                refreshed.destination,
                expected_revision=source_record.revision,
                expected_sha256=source_hash,
                is_cancelled=is_cancelled,
                report_progress=report_progress,
            )
            if sha256_of_file(refreshed.destination) != source_hash:
                raise FileOperationRecoveryError(
                    "The destination bytes differ from the source.", None, phase="published"
                )
            metadata = self._reader.read(refreshed.destination)
            if metadata.status != "readable":
                raise ValueError("The copied file cannot be read at its new path.")
            result_revision = SourceRevision.observe(refreshed.destination)
            copied_track_id = self._history.complete_copy(
                operation_id=operation_id,
                destination=refreshed.destination,
                result_revision=result_revision,
                metadata=metadata,
            )
            return FileOperationResult(
                target.track_id,
                operation_id,
                "completed",
                f"Created a separate library track ({copied_track_id}).",
                refreshed.source,
                refreshed.destination,
                result_revision,
            )
        except FileOperationCancelledError as error:
            if journal_created:
                self._history.set_copy_status(operation_id, "failed", error=str(error))
            return FileOperationResult(
                target.track_id,
                operation_id,
                "cancelled",
                str(error),
                target.source,
                target.destination,
            )
        except (FileOperationRecoveryError, FileOperationNativeError) as error:
            needs_recovery = temporary.exists() or refreshed.destination.exists()
            if journal_created:
                self._history.set_copy_status(
                    operation_id,
                    "needs_recovery" if needs_recovery else "failed",
                    error=str(error),
                )
            return FileOperationResult(
                target.track_id,
                operation_id,
                "recovery" if journal_created and needs_recovery else "failed",
                f"The source was retained; inspect the copy paths: {error}",
                refreshed.source,
                refreshed.destination,
            )
        except Exception as error:
            needs_recovery = temporary.exists() or refreshed.destination.exists()
            if journal_created:
                self._history.set_copy_status(
                    operation_id,
                    "needs_recovery" if needs_recovery else "failed",
                    error=str(error),
                )
            return FileOperationResult(
                target.track_id,
                operation_id,
                "recovery" if journal_created and needs_recovery else "failed",
                f"The source was retained; inspect the copy paths: {error}",
                refreshed.source,
                refreshed.destination,
            )

    def _execute_locked(
        self,
        kind: str,
        target: FileOperationTarget,
        *,
        undo_of: str = "",
        is_cancelled: Callable[[], bool],
        report_progress: Callable[[int, int], None],
    ) -> FileOperationResult:
        if is_cancelled():
            return _result(target, "cancelled", "The move was cancelled before it started.")
        source_record = self._library.source_record(target.track_id)
        if source_record is None:
            return _result(target, "conflict", "The track is no longer in the library.")
        if (
            source_record.path.resolve(strict=False) != target.source.resolve(strict=False)
            or source_record.revision.generation != target.revision.generation
            or not source_record.revision.matches(target.revision)
        ):
            return _result(target, "conflict", "The track moved or changed after the preview.")
        refreshed = self._preflight_destination(
            target.track_id,
            source_record.path,
            target.destination,
            source_record.revision,
        )
        if refreshed.status != "ready":
            return _result(target, refreshed.status, refreshed.message)

        try:
            source_hash = sha256_of_file(source_record.path)
            source_after_hash = SourceRevision.observe(
                source_record.path,
                generation=source_record.revision.generation,
            )
        except OSError as error:
            return _result(
                target,
                "conflict",
                f"Could not verify the source before moving it: {error}",
            )
        if not source_record.revision.matches(source_after_hash):
            return _result(
                target,
                "conflict",
                "The source changed while it was being checked; nothing was moved.",
            )

        operation_id = str(uuid.uuid4())
        temporary = refreshed.destination.parent / f".mtee-move-{operation_id}.tmp"
        cross_volume = not self._same_volume(refreshed.source, refreshed.destination.parent)
        try:
            self._history.create(
                operation_id=operation_id,
                kind=kind,
                target=refreshed,
                source_sha256=source_hash,
                undo_of=undo_of,
            )
            if cross_volume:
                self._history.update_phase(operation_id, "copying", recovery_path=temporary)
                self._platform.move_cross_volume(
                    refreshed.source,
                    temporary,
                    refreshed.destination,
                    expected_revision=source_record.revision,
                    expected_sha256=source_hash,
                    is_cancelled=is_cancelled,
                    report_progress=report_progress,
                    phase_changed=lambda phase, recovery_path: self._history.update_phase(
                        operation_id, phase, recovery_path=recovery_path
                    ),
                )
            else:
                self._platform.move_no_replace(refreshed.source, refreshed.destination)
                self._history.update_phase(operation_id, "source_removed")
            if _hash_or_empty(refreshed.destination) != source_hash:
                self._history.set_status(
                    operation_id,
                    "needs_recovery",
                    error="The destination bytes differ from the source captured before the move.",
                )
                return FileOperationResult(
                    target.track_id,
                    operation_id,
                    "recovery",
                    "The moved file needs recovery. Both operation paths have been retained.",
                    refreshed.source,
                    refreshed.destination,
                )
            metadata = self._reader.read(refreshed.destination)
            if metadata.status != "readable":
                raise ValueError("The moved file cannot be read at its new path.")
            result_revision = SourceRevision.observe(
                refreshed.destination,
                generation=source_record.revision.generation + 1,
            )
            if result_revision.size_bytes != source_record.revision.size_bytes or (
                not cross_volume and not source_record.revision.matches(result_revision)
            ):
                self._history.set_status(
                    operation_id,
                    "needs_recovery",
                    error=(
                        "The moved file revision differs from the source revision "
                        "captured before the move."
                    ),
                )
                return FileOperationResult(
                    target.track_id,
                    operation_id,
                    "recovery",
                    (
                        "The destination content is intact, but its file identity changed; "
                        "inspect the operation."
                    ),
                    refreshed.source,
                    refreshed.destination,
                    result_revision,
                )
            self._history.complete(
                operation_id=operation_id,
                track_id=target.track_id,
                expected_revision=source_record.revision,
                destination=refreshed.destination,
                result_revision=result_revision,
                metadata=metadata,
                undo_of=undo_of,
            )
            return FileOperationResult(
                target.track_id,
                operation_id,
                "completed",
                source=refreshed.source,
                destination=refreshed.destination,
                revision=result_revision,
            )
        except FileOperationRecoveryError as error:
            with suppress(Exception):
                self._history.set_status(
                    operation_id,
                    "needs_recovery",
                    error=str(error),
                    recovery_path=error.recovery_path,
                    phase=error.phase,
                )
            return FileOperationResult(
                target.track_id,
                operation_id,
                "recovery",
                (
                    f"The move stopped during {error.phase}. Inspect the source and destination"
                    + (f"; temporary copy: {error.recovery_path}." if error.recovery_path else ".")
                ),
                refreshed.source,
                refreshed.destination,
            )
        except FileOperationCancelledError as error:
            with suppress(Exception):
                self._history.set_status(
                    operation_id,
                    "failed",
                    error=str(error),
                    phase="cancelled",
                )
            return FileOperationResult(
                target.track_id,
                operation_id,
                "cancelled",
                str(error),
                refreshed.source,
                refreshed.destination,
            )
        except FileOperationNativeError as error:
            with suppress(Exception):
                self._history.set_status(
                    operation_id,
                    "failed",
                    error=str(error),
                    phase="failed",
                    recovery_path=temporary if temporary.exists() else None,
                )
            return FileOperationResult(
                target.track_id,
                operation_id,
                "failed",
                str(error),
                refreshed.source,
                refreshed.destination,
            )
        except FileOperationJournalConflictError as error:
            with suppress(Exception):
                self._history.set_status(operation_id, "needs_recovery", error=str(error))
            return FileOperationResult(
                target.track_id,
                operation_id,
                "recovery",
                f"The file moved but its library record needs recovery: {error}",
                refreshed.source,
                refreshed.destination,
            )
        except Exception as error:
            destination_present = _hash_or_empty(refreshed.destination) == source_hash
            source_present = _hash_or_empty(refreshed.source) == source_hash
            temporary_present = temporary.exists() or temporary.is_symlink()
            status = (
                "needs_recovery"
                if destination_present or not source_present or temporary_present
                else "failed"
            )
            with suppress(Exception):
                self._history.set_status(
                    operation_id,
                    status,
                    error=f"{type(error).__name__}: {error}",
                    phase=(
                        "destination_published"
                        if destination_present
                        else "copying"
                        if temporary_present
                        else "failed"
                    ),
                    recovery_path=temporary if temporary_present else None,
                )
            return FileOperationResult(
                target.track_id,
                operation_id,
                "recovery" if status == "needs_recovery" else "failed",
                f"{type(error).__name__}: {error}",
                refreshed.source,
                refreshed.destination,
            )

    @staticmethod
    def _same_volume(source: Path, destination_folder: Path) -> bool:
        return os.stat(source).st_dev == os.stat(destination_folder).st_dev


def _renamed_path(source: Path, requested: str) -> tuple[Path, str]:
    name = requested
    if not name.strip() or name in {".", ".."}:
        return source, "Enter a valid file name."
    if name.endswith((".", " ")) or _INVALID_NAME.search(name):
        return source, "Windows does not allow this file name."
    suffix = source.suffix
    requested_suffix = Path(name).suffix
    if requested_suffix and requested_suffix.casefold() != suffix.casefold():
        return source, "The audio file extension cannot be changed by renaming."
    stem = name[: -len(requested_suffix)] if requested_suffix else name
    if stem.endswith((".", " ")):
        return source, "Windows does not allow this file name."
    if stem.rstrip(" .").upper() in _RESERVED_NAMES:
        return source, "Windows reserves this file name."
    return source.with_name(f"{stem}{suffix}"), ""


def _local_path(value: str) -> Path:
    parsed = urlparse(value)
    if parsed.scheme.casefold() != "file":
        return Path(value).expanduser().resolve(strict=False)
    path = unquote(parsed.path)
    if os.name == "nt" and re.match(r"^/[A-Za-z]:", path):
        path = path[1:]
    if parsed.netloc:
        path = f"//{parsed.netloc}{path}"
    return Path(path).expanduser().resolve(strict=False)


def _blocked(
    track_id: str, source: Path | str, destination: Path | str, message: str
) -> FileOperationTarget:
    return FileOperationTarget(
        track_id,
        Path(source) if source else Path(),
        Path(destination) if destination else Path(),
        SourceRevision(0, 0),
        "blocked",
        message,
    )


def _result(target: FileOperationTarget, status: str, message: str) -> FileOperationResult:
    return FileOperationResult(
        target.track_id, "", status, message, target.source, target.destination
    )


def _hash_or_empty(path: Path) -> str:
    try:
        return sha256_of_file(path) if path.is_file() and not path.is_symlink() else ""
    except OSError:
        return ""


def _hash_path_state(path: Path, expected_sha256: str, expected_size: int) -> str:
    if path.is_symlink() or not path.is_file():
        return "missing"
    try:
        if path.stat().st_size != expected_size or sha256_of_file(path) != expected_sha256:
            return "changed"
    except OSError:
        return "unreadable"
    return "matches"


def _journal_path_state(
    path: Path,
    expected_sha256: str,
    expected_revision: SourceRevision,
    *,
    check_revision: bool = True,
) -> str:
    if path.is_symlink() or not path.is_file():
        return "missing"
    try:
        if sha256_of_file(path) != expected_sha256:
            return "changed"
        observed = SourceRevision.observe(path, generation=expected_revision.generation)
    except OSError:
        return "unreadable"
    if check_revision:
        return "matches" if expected_revision.matches(observed) else "changed"
    return "matches" if expected_revision.size_bytes == observed.size_bytes else "changed"


def _track_id(track_id: str):
    from mtee.domain.tracks import TrackId

    return TrackId.parse(track_id)
