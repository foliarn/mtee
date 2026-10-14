"""Apply confirmed artist credits to the files: tags when asked, then the file name.

Every confirmed track is handled on its own, in phases that are written to the journal
before the file is touched: tags (only when the user ticked the box), name reservation,
rename without overwriting, then one SQLite transaction that moves the location and ends
the item. A phase that is finished is never repeated on resume, a file that is busy or
changed stays visible with its cause, and no phase replaces a file it does not own.

The lock of a track has one owner at a time: the tag writer takes it for its own write,
and this service takes it, separately, around the rename.
"""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from mtee.domain.artists import build_stem, safe_file_name
from mtee.domain.jobs import JobCancelledError
from mtee.domain.metadata_edit import MetadataEditResult, MetadataPatch
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository, normalize_path
from mtee.plugins.artist_manager.repository import ArtistRepository, revision_from_json
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError

__all__ = ["ApplySummary", "ArtistFileService", "TagWriter"]

_ACTIVE = ("queued", "running", "failed", "cancelled")


class TagWriter(Protocol):
    """The part of the metadata edit service used to write and undo the tags."""

    def save(
        self,
        track_id: str,
        expected_revision: SourceRevision,
        patch: MetadataPatch,
        draft_id: str,
    ) -> MetadataEditResult: ...

    def undo(self, operation_id: str, draft_id: str) -> MetadataEditResult: ...


@dataclass(slots=True)
class ApplySummary:
    """What happened to the items of one application."""

    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    warnings: int = 0


class _ItemError(Exception):
    """An item stopped with a cause the user can read; it stays queued for a retry."""


class ArtistFileService:
    def __init__(
        self,
        database: Database,
        library: LibraryRepository,
        repository: ArtistRepository,
        tag_writer: TagWriter | None,
        file_access: FileAccessCoordinator,
    ) -> None:
        self._database = database
        self._library = library
        self._repository = repository
        self._tags = tag_writer
        self._access = file_access
        self._reservation_lock = threading.Lock()
        self._reserved: set[str] = set()

    # ------------------------------------------------------------------ preview

    def preview_name(self, track_id: str, names: list[str], title: str) -> dict[str, Any]:
        """Return the file name a credit would give, without reserving anything."""
        record = self._library.source_record(track_id)
        if record is None or not names or not title.strip():
            return {"name": "", "shortened": False, "collision": False}
        name, shortened = safe_file_name(
            build_stem(names, title),
            record.path.suffix,
            directory_length=len(str(record.path.parent)),
        )
        candidate = record.path.parent / name
        collision = (
            candidate.name != record.path.name
            and normalize_path(candidate) != normalize_path(record.path)
            and (candidate.exists() or self._library.path_owner(candidate) is not None)
        )
        return {"name": name, "shortened": shortened, "collision": collision}

    # -------------------------------------------------------------- application

    def apply_operation(
        self,
        operation_id: str,
        *,
        is_cancelled: Callable[[], bool] = lambda: False,
        report_items: Callable[[int, int, str], None] = lambda _done, _total, _name: None,
        report_failure: Callable[[str, str], None] = lambda _name, _message: None,
        on_item_done: Callable[[str], None] = lambda _track_id: None,
    ) -> ApplySummary:
        """Apply the unfinished items of an operation, one track at a time."""
        operation = self._repository.operation(operation_id)
        if operation is None:
            return ApplySummary()
        items = self._repository.operation_items(operation_id, _ACTIVE)
        total = len(items)
        summary = ApplySummary()
        self._repository.set_operation_status(operation_id, "running")
        for index, item in enumerate(items):
            track_id = str(item["track_id"])
            name = self._display_name(track_id)
            if is_cancelled():
                for rest in items[index:]:
                    self._mark_cancelled(operation_id, str(rest["track_id"]), str(rest["mode"]))
                    summary.cancelled += 1
                    on_item_done(str(rest["track_id"]))
                break
            report_items(index, total, name)
            try:
                warning = self._apply_item(operation, item, is_cancelled)
            except JobCancelledError:
                self._mark_cancelled(operation_id, track_id, str(item["mode"]))
                summary.cancelled += 1
                on_item_done(track_id)
                continue
            except _ItemError as failure:
                self._fail(operation_id, track_id, str(item["mode"]), str(failure))
                report_failure(name, str(failure))
                summary.failed += 1
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                self._fail(operation_id, track_id, str(item["mode"]), message)
                report_failure(name, message)
                summary.failed += 1
            else:
                summary.succeeded += 1
                if warning:
                    summary.warnings += 1
            on_item_done(track_id)
            report_items(index + 1, total, name)
        remaining = self._repository.operation_items(operation_id, _ACTIVE)
        if not remaining:
            self._repository.set_operation_status(operation_id, "completed")
        elif summary.cancelled and not summary.failed:
            self._repository.set_operation_status(operation_id, "cancelled")
        else:
            self._repository.set_operation_status(operation_id, "partial")
        with self._reservation_lock:
            self._reserved.clear()
        return summary

    def _display_name(self, track_id: str) -> str:
        record = self._library.source_record(track_id)
        return record.path.name if record is not None else track_id

    def _mark_cancelled(self, operation_id: str, track_id: str, mode: str) -> None:
        self._repository.update_item(operation_id, track_id, status="cancelled")
        if mode == "full":
            self._repository.set_apply_state(track_id, "cancelled")

    def _fail(self, operation_id: str, track_id: str, mode: str, message: str) -> None:
        self._repository.update_item(operation_id, track_id, status="failed", error=message)
        if mode == "full":
            self._repository.set_apply_state(track_id, "failed", error=message)

    def _apply_item(
        self, operation: dict[str, Any], item: dict[str, Any], is_cancelled: Callable[[], bool]
    ) -> str:
        """Run the phases of one item; returns a warning text, ``""`` when none."""
        operation_id = str(operation["operation_id"])
        track_id = str(item["track_id"])
        mode = str(item["mode"])
        write_tags = bool(operation["write_tags"])
        confirmed = self._repository.confirmed_state(track_id)
        if mode == "full":
            if (
                confirmed is None
                or confirmed["reviewState"] != "confirmed"
                or not confirmed["credits"]
            ):
                self._repository.update_item(
                    operation_id,
                    track_id,
                    status="cancelled",
                    error="The decision changed after this operation was prepared.",
                )
                return ""
            names = [credit["name"] for credit in confirmed["credits"]]
            title = str(confirmed["title"])
        else:
            names, title = [], ""
        record = self._library.source_record(track_id)
        if record is None:
            raise _ItemError("The track is no longer in the library.")
        self._repository.update_item(operation_id, track_id, status="running", error="")
        if mode == "full":
            self._repository.set_apply_state(track_id, "running")
        if not item["revision_before_json"]:
            self._repository.update_item(
                operation_id,
                track_id,
                revision_before_json=_revision_text(record.revision),
                path_before=str(record.path),
            )
            item = {**item, "path_before": str(record.path)}
        warning = ""
        if write_tags and item["tags_phase"] == "pending":
            warning = self._write_tags(operation_id, track_id, item, names, title, mode)
            if is_cancelled():
                raise JobCancelledError("cancelled")
        elif not write_tags and item["tags_phase"] == "pending":
            self._repository.update_item(operation_id, track_id, tags_phase="skipped")
        if mode == "tags_only":
            self._repository.update_item(
                operation_id, track_id, status="succeeded", warning=warning
            )
            return warning
        self._rename(operation_id, track_id, item, names, title, warning)
        return warning

    def _write_tags(
        self,
        operation_id: str,
        track_id: str,
        item: dict[str, Any],
        names: list[str],
        title: str,
        mode: str,
    ) -> str:
        if self._tags is None:
            self._repository.update_item(operation_id, track_id, tags_phase="unsupported")
            return "Writing tags is not available."
        record = self._library.source_record(track_id)
        if record is None:
            raise _ItemError("The track is no longer in the library.")
        self._check_disk(record.path, record.revision)
        patch = (
            MetadataPatch.from_credit(None, None)
            if mode == "tags_only"
            else MetadataPatch.from_credit(names, title)
            if names
            else MetadataPatch.from_credit(None, None)
        )
        result = self._tags.save(track_id, record.revision, patch, str(uuid.uuid4()))
        if result.status == "saved":
            self._repository.update_item(
                operation_id, track_id, tags_phase="done", tag_operation_id=result.operation_id
            )
            return ""
        if result.status == "unsupported":
            self._repository.update_item(operation_id, track_id, tags_phase="unsupported")
            return f"Tags not written: {result.message or 'this format is not supported.'}"
        if result.status == "busy":
            raise _ItemError(result.message or "The file is busy. Stop playback and retry.")
        raise _ItemError(result.message or f"The tags could not be written ({result.status}).")

    @staticmethod
    def _check_disk(path: Path, expected: SourceRevision) -> None:
        try:
            observed = SourceRevision.observe(path)
        except OSError as error:
            raise _ItemError(f"The file is not available: {error}") from error
        if not expected.matches(observed):
            raise _ItemError("The file changed since its last scan. Scan the folder and retry.")

    def _rename(
        self,
        operation_id: str,
        track_id: str,
        item: dict[str, Any],
        names: list[str],
        title: str,
        warning: str,
    ) -> None:
        record = self._library.source_record(track_id)
        if record is None:
            raise _ItemError("The track is no longer in the library.")
        current = record.path
        target_text = str(item["path_target"])
        if not target_text:
            target = self._choose_target(record.path, track_id, names, title)
            self._repository.update_item(
                operation_id, track_id, path_target=str(target), path_before=str(current)
            )
        else:
            target = Path(target_text)
        before_text = str(item["path_before"]) or str(current)
        if current == target:
            self._finish(operation_id, track_id, record, target, "noop", warning, move=False)
            return
        source_exists = current.exists()
        target_exists = target.exists()
        if (
            Path(before_text) == current
            and source_exists
            and target_exists
            and not _same_file(current, target)
        ):
            # The reserved name was taken since the reservation: choose another one.
            target = self._choose_target(current, track_id, names, title, force_new=True)
            self._repository.update_item(operation_id, track_id, path_target=str(target))
            target_exists = False
        if source_exists and not (target_exists and not _same_file(current, target)):
            try:
                with self._access.acquire(
                    TrackId.parse(track_id), "artist rename", timeout_seconds=0
                ):
                    self._check_disk(current, record.revision)
                    os.rename(current, target)
            except FileAccessTimeoutError as error:
                raise _ItemError(
                    "The file is playing or in use. Stop playback and retry."
                ) from error
            except OSError as error:
                raise _ItemError(f"The file could not be renamed: {error}") from error
            self._repository.update_item(operation_id, track_id, rename_phase="done")
        elif not source_exists and target_exists:
            # A previous run renamed the file but stopped before the database update.
            observed = SourceRevision.observe(target)
            if not record.revision.matches(observed):
                raise _ItemError(
                    "A different file already has the reserved name. Nothing was changed."
                )
        else:
            raise _ItemError("Neither the file nor its reserved name could be found.")
        self._finish(operation_id, track_id, record, target, "done", warning, move=True)

    def _finish(
        self,
        operation_id: str,
        track_id: str,
        record: Any,
        target: Path,
        phase: str,
        warning: str,
        *,
        move: bool,
    ) -> None:
        with self._database.transaction() as connection:
            if move:
                new_revision = SourceRevision.observe(
                    target, generation=record.revision.generation + 1
                )
                LibraryRepository.move_location_in_transaction(
                    connection,
                    track_id=track_id,
                    expected_revision=record.revision,
                    destination=target,
                    new_revision=new_revision,
                    metadata=record.snapshot,
                )
            else:
                new_revision = record.revision
            connection.execute(
                "UPDATE artist_operation_items SET rename_phase=? WHERE operation_id=? "
                "AND track_id=?",
                (phase, operation_id, track_id),
            )
            ArtistRepository.finish_item(
                connection,
                operation_id,
                track_id,
                path_final=str(target),
                revision_after=new_revision,
                note=warning,
            )

    def _choose_target(
        self,
        current: Path,
        track_id: str,
        names: list[str],
        title: str,
        *,
        force_new: bool = False,
    ) -> Path:
        directory = current.parent
        extension = current.suffix
        name, _shortened = safe_file_name(
            build_stem(names, title), extension, directory_length=len(str(directory))
        )
        base = Path(name).stem
        own_key = normalize_path(current)
        number = 1
        with self._reservation_lock:
            while True:
                candidate = directory / (name if number == 1 else f"{base} ({number}){extension}")
                key = normalize_path(candidate)
                if candidate.name == current.name and not force_new:
                    return current
                if key == own_key:
                    return candidate
                owner = self._library.path_owner(candidate)
                if (
                    not candidate.exists()
                    and owner in (None, track_id)
                    and key not in self._reserved
                ):
                    self._reserved.add(key)
                    return candidate
                number += 1

    # --------------------------------------------------------------------- undo

    def undo_operation(self, operation_id: str) -> dict[str, Any]:
        """Undo a confirmation item by item; a changed file is reported, never overwritten."""
        done: list[str] = []
        conflicts: list[str] = []
        items = [
            item
            for item in self._repository.operation_items(operation_id)
            if item["status"] == "succeeded"
        ]
        for item in reversed(items):
            track_id = str(item["track_id"])
            problem = self._undo_item(item)
            if problem:
                conflicts.append(f"{self._display_name(track_id)}: {problem}")
                continue
            before = _json_dict(item["before_json"])
            self._repository.restore_decision(track_id, before)
            self._repository.update_item(operation_id, track_id, status="undone")
            done.append(track_id)
        remaining = self._repository.operation_items(operation_id, ("succeeded",))
        if not remaining:
            self._repository.set_operation_status(operation_id, "undone")
        return {"undone": done, "conflicts": conflicts}

    def _undo_item(self, item: dict[str, Any]) -> str:
        track_id = str(item["track_id"])
        record = self._library.source_record(track_id)
        if record is None:
            return "the track is no longer in the library."
        final = Path(str(item["path_final"] or record.path))
        if final != record.path:
            return "the file was moved since."
        expected = revision_from_json(str(item["revision_after_json"]))
        if expected is not None:
            try:
                observed = SourceRevision.observe(record.path)
            except OSError as error:
                return f"the file is not available ({error})."
            if not expected.matches(observed):
                return "the file changed since."
        if item["tags_phase"] == "done" and item["tag_operation_id"] and self._tags is not None:
            result = self._tags.undo(str(item["tag_operation_id"]), str(uuid.uuid4()))
            if result.status != "saved":
                return result.message or "its tags could not be restored."
        before = Path(str(item["path_before"]))
        if item["path_before"] and before != record.path:
            if before.exists():
                return "the former file name is taken."
            record = self._library.source_record(track_id)
            if record is None:
                return "the track is no longer in the library."
            try:
                with self._access.acquire(
                    TrackId.parse(track_id), "artist rename undo", timeout_seconds=0
                ):
                    self._check_disk(record.path, record.revision)
                    os.rename(record.path, before)
            except FileAccessTimeoutError:
                return "the file is in use."
            except (OSError, _ItemError) as error:
                return f"the file could not be renamed back ({error})."
            with self._database.transaction() as connection:
                LibraryRepository.move_location_in_transaction(
                    connection,
                    track_id=track_id,
                    expected_revision=record.revision,
                    destination=before,
                    new_revision=SourceRevision.observe(
                        before, generation=record.revision.generation + 1
                    ),
                    metadata=record.snapshot,
                )
        return ""

    def resume_ids(self) -> list[str]:
        """Return the operations that still have unfinished items."""
        seen: dict[str, None] = {}
        for entry in self._repository.pending_applications():
            seen.setdefault(str(entry["operation_id"]), None)
        return list(seen)


def _same_file(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _revision_text(revision: SourceRevision) -> str:
    import json

    return json.dumps(
        {
            "size_bytes": revision.size_bytes,
            "mtime_ns": revision.mtime_ns,
            "file_id": revision.file_id,
            "generation": revision.generation,
        }
    )


def _json_dict(text: str) -> dict[str, Any]:
    import json

    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
