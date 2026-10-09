"""Shared setup for track list UI tests: a folder of tiny WAV tracks in a running app."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QMetaObject, QObject, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from tests.ui.test_player_views import _find

from mtee.app import _Runtime
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.library_repository import LibraryRepository

# PySide6 takes a str method name at runtime; its stubs only list bytes.
_invoke_method: Any = QMetaObject.invokeMethod


def add_folder_tracks(runtime: _Runtime, audio: Path, count: int) -> tuple[str, list[str]]:
    """Write ``count`` short WAV files into ``audio`` and index them under one root."""
    audio.mkdir(parents=True, exist_ok=True)
    library = LibraryRepository(runtime.database)
    root_id = str(library.add_root(audio)["id"])
    track_ids: list[str] = []
    for index in range(count):
        path = audio / f"track-{index:03d}.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 800)
        track_ids.append(
            str(
                library.upsert_location(
                    root_id,
                    path.name,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(
                        title=(f"Title {index:03d}",),
                        artist=("Example",),
                        technical=TechnicalInfo(duration_us=3_000_000),
                    ),
                    0,
                )
            )
        )
    return root_id, track_ids


def open_folder(runtime: _Runtime, root_id: str) -> WorkspaceModel:
    """Open the root folder of the library in the active list tab."""
    assert runtime.jobs.wait_for_done(10_000)
    workspace = cast(WorkspaceModel, runtime.workspace)
    workspace.openFolder(f"folder:{root_id}/")
    return workspace


def row_item(window: QQuickWindow, number: int) -> QQuickItem | None:
    return _find(window, f"trackRow_{number}")


def invoke_slot(target: QObject, method: str, *arguments: Any) -> bool:
    """Call a QML function of the list directly, without going through pointer events."""
    return bool(_invoke_method(target, method, Qt.ConnectionType.DirectConnection, *arguments))
