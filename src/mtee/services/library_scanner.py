"""Cancellable, bounded-batch traversal of user-selected audio folders."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from mtee.domain.tracks import SourceRevision

__all__ = [
    "AUDIO_SUFFIXES",
    "LibraryScanner",
    "ScanBatch",
    "ScanEntry",
    "ScanIssue",
]

AUDIO_SUFFIXES = frozenset(
    {
        ".aif",
        ".aiff",
        ".ape",
        ".flac",
        ".m4a",
        ".m4b",
        ".mp3",
        ".mpc",
        ".oga",
        ".ogg",
        ".opus",
        ".wav",
        ".wv",
    }
)
_MTEE_CONVERSION_TEMP = re.compile(
    r"^.+\.mtee-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.tmp\.[^.]+$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ScanEntry:
    path: Path
    relative_path: str
    revision: SourceRevision


@dataclass(frozen=True, slots=True)
class ScanIssue:
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ScanBatch:
    entries: tuple[ScanEntry, ...] = ()
    folders: tuple[str, ...] = ()
    issues: tuple[ScanIssue, ...] = ()
    complete: bool = False
    cancelled: bool = False


class LibraryScanner:
    """Enumerate known audio candidates without following directory links."""

    def __init__(self, batch_size: int = 128) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._batch_size = batch_size

    def scan(
        self, root: Path | str, *, is_cancelled: Callable[[], bool] = lambda: False
    ) -> Iterator[ScanBatch]:
        root_path = Path(root).expanduser()
        if root_path.is_symlink():
            yield ScanBatch(issues=(ScanIssue(str(root_path), "A folder link cannot be scanned."),))
            return
        try:
            root_path = root_path.resolve(strict=True)
            if not root_path.is_dir():
                raise NotADirectoryError(str(root_path))
        except OSError as error:
            yield ScanBatch(issues=(ScanIssue(str(root_path), _message(error)),))
            return

        pending = [root_path]
        entries: list[ScanEntry] = []
        folders: list[str] = []
        issues: list[ScanIssue] = []
        complete = True
        while pending:
            if is_cancelled():
                complete = False
                yield ScanBatch(
                    entries=tuple(entries),
                    folders=tuple(folders),
                    issues=tuple(issues),
                    cancelled=True,
                )
                return
            directory = pending.pop()
            try:
                with os.scandir(directory) as iterator:
                    children = sorted(iterator, key=lambda item: (item.name.casefold(), item.name))
            except OSError as error:
                complete = False
                issues.append(ScanIssue(str(directory), _message(error)))
                continue
            subdirectories: list[Path] = []
            for child in children:
                if is_cancelled():
                    complete = False
                    yield ScanBatch(
                        entries=tuple(entries),
                        folders=tuple(folders),
                        issues=tuple(issues),
                        cancelled=True,
                    )
                    return
                try:
                    if child.is_symlink():
                        continue
                    if child.is_dir(follow_symlinks=False):
                        folder_path = Path(child.path)
                        subdirectories.append(folder_path)
                        folders.append(folder_path.relative_to(root_path).as_posix())
                        if len(entries) + len(folders) >= self._batch_size:
                            yield ScanBatch(entries=tuple(entries), folders=tuple(folders))
                            entries.clear()
                            folders.clear()
                        continue
                    if (
                        not child.is_file(follow_symlinks=False)
                        or _MTEE_CONVERSION_TEMP.fullmatch(child.name) is not None
                        or Path(child.name).suffix.casefold() not in AUDIO_SUFFIXES
                    ):
                        continue
                    path = Path(child.path)
                    try:
                        revision = SourceRevision.observe(path)
                    except OSError as error:
                        complete = False
                        issues.append(ScanIssue(str(path), _message(error)))
                        continue
                    relative = path.relative_to(root_path).as_posix()
                    entries.append(ScanEntry(path, relative, revision))
                    if len(entries) + len(folders) >= self._batch_size:
                        yield ScanBatch(entries=tuple(entries), folders=tuple(folders))
                        entries.clear()
                        folders.clear()
                except OSError as error:
                    complete = False
                    issues.append(ScanIssue(child.path, _message(error)))
            pending.extend(reversed(subdirectories))
        yield ScanBatch(
            entries=tuple(entries), folders=tuple(folders), issues=tuple(issues), complete=complete
        )


def _message(error: OSError) -> str:
    return error.strerror or str(error) or type(error).__name__
