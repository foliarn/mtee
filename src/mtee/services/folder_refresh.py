"""Bring the library up to date with one folder, without a full rescan."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mtee.domain.tracks import SourceRevision
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.library_scanner import LibraryScanner
from mtee.services.metadata_reader import MetadataReader

__all__ = ["STABILITY_DELAY_SECONDS", "FolderRefreshResult", "refresh_folder"]

STABILITY_DELAY_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class FolderRefreshResult:
    """What a refresh changed: the parents to reload and whether files were still growing."""

    folders: tuple[str, ...] = ()
    unstable: bool = False
    issues: tuple[str, ...] = ()


def refresh_folder(
    library: LibraryRepository,
    scanner: LibraryScanner,
    reader: MetadataReader,
    root_id: str,
    root_path: Path | str,
    relative: str,
    *,
    wait: Callable[[float], None],
) -> FolderRefreshResult:
    """Diff the direct children of ``relative`` against the library and apply the changes.

    Files that appeared or changed are read again after ``STABILITY_DELAY_SECONDS``; one
    whose size or date still moves is being copied and is left for the next pass. The scan
    generation is never changed: a full rescan that starts meanwhile wins, and the guarded
    writes of the library repository then do nothing.
    """
    generation = library.current_generation(root_id)
    listing = scanner.list_directory(root_path, relative)
    issues = tuple(issue.message for issue in listing.issues)
    if not listing.complete:
        return FolderRefreshResult(issues=issues)

    unchanged = library.unchanged_paths(
        root_id, [(entry.relative_path, entry.revision) for entry in listing.entries]
    )
    fresh = [entry for entry in listing.entries if entry.relative_path not in unchanged]
    settled = set()
    if fresh:
        wait(STABILITY_DELAY_SECONDS)
        for entry in fresh:
            try:
                again = SourceRevision.observe(entry.path)
            except OSError:
                continue
            if entry.revision.matches(again):
                settled.add(entry.relative_path)
    unstable = len(settled) < len(fresh)

    records: list[tuple[str, Path, Any, Any]] = []
    for entry in listing.entries:
        if entry.relative_path in unchanged:
            records.append((entry.relative_path, entry.path, entry.revision, None))
        elif entry.relative_path in settled:
            try:
                snapshot = reader.read(entry.path)
            except OSError as error:
                issues += (f"{entry.relative_path}: {error}",)
                continue
            records.append((entry.relative_path, entry.path, entry.revision, snapshot))
    identities = library.upsert_locations(root_id, records, generation)

    changed: set[str] = set()
    for record, identity in zip(records, identities, strict=True):
        if identity and record[0] not in unchanged:
            changed.add(relative)
    if library.upsert_folders(root_id, listing.folders, generation):
        changed.add(relative)
    changed.update(
        library.reconcile_folder(
            root_id,
            relative,
            present_files=[entry.relative_path for entry in listing.entries],
            present_folders=listing.folders,
            generation=generation,
        )
    )
    return FolderRefreshResult(tuple(sorted(changed)), unstable, issues)
