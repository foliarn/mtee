"""Shared helpers of the Artists view UI tests (plan 112).

The library holds the Artist tag of each file, and the splitting rules are the core ones:
"Chase" is a solo artist, so "Chase & Status" is cut; "Camo & Krooked" is not cut.

Each UI test file runs one runtime at a time. Several runtimes in one process leave worker
threads that read a closed database, which aborts the process on this machine.
"""

from __future__ import annotations

import time
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QCoreApplication
from PySide6.QtQuick import QQuickWindow
from tests.ui.test_player_views import _find, _UiPlayerBackend

from mtee.app import _build_runtime, _shutdown
from mtee.cli import AppOptions
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository

# title, Artist tag values, album, track number
TRACKS = (
    ("one", ("Chase & Status",), "Brand New", "2"),
    ("two", ("Chase",), "Alpha", "3"),
    ("three", ("Camo & Krooked",), "Alpha", "1"),
    ("four", ("Chase",), "Alpha", "1/9"),
)


def write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 24000)


def seed(base: Path) -> tuple[Path, dict[str, str]]:
    """Write the synthetic library under ``base``; return the data dir and the track ids."""
    audio = base / "audio"
    audio.mkdir(parents=True)
    data_dir = base / "data"
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root_record = library.add_root(audio)
    track_ids: dict[str, str] = {}
    for index, (title, artists, album, number) in enumerate(TRACKS):
        path = audio / f"{index}.wav"
        write_wav(path)
        track_ids[title] = library.upsert_location(
            root_record["id"],
            path.name,
            path,
            SourceRevision.observe(path),
            MetadataSnapshot(
                title=(title,),
                artist=artists,
                album=(album,),
                track_number=(number,),
                technical=TechnicalInfo(duration_us=3_000_000),
            ),
            0,
        )
    database.close()
    return data_dir, {"root": str(root_record["id"]), **track_ids}


def wait_until(predicate: Callable[[], bool], timeout_ms: int = 10_000) -> bool:
    """Pump the events until ``predicate`` holds; the sleeps let the job threads run."""
    deadline = time.monotonic() + timeout_ms / 1000
    while not predicate():
        if time.monotonic() > deadline:
            return False
        QCoreApplication.processEvents()
        time.sleep(0.01)
    return True


def start(qapp: Any, monkeypatch: Any, data_dir: Path) -> Any:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    monkeypatch.setattr("mtee.plugins.registry.PLUGIN_UI_ENABLED", False)
    runtime = _build_runtime(qapp, AppOptions(data_dir=data_dir))
    assert runtime is not None
    return runtime


def ready(runtime: Any) -> tuple[WorkspaceModel, QQuickWindow]:
    """Wait for the first artist index; return the workspace and the window, sized wide."""
    workspace = cast(WorkspaceModel, runtime.workspace)
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    assert runtime.jobs.wait_for_done(10_000)
    assert wait_until(lambda: cast(int, workspace.artistRevision) > 0)
    return workspace, root


def settle(milliseconds: int) -> None:
    """Pump the events for a while, so that work already queued by the window runs."""
    deadline = time.monotonic() + milliseconds / 1000
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def stop(runtime: Any) -> None:
    """Let the background work finish, then shut the runtime down.

    Covers are decoded by the image provider in Qt threads, which read the database: the
    database must not close while one of them runs. Jobs that finish later would report into
    deleted objects. The waits are short, since the library read here is three small files.
    """
    runtime.jobs.wait_for_done(10_000)
    settle(300)
    for window in runtime.engine.rootObjects():
        window.close()
    settle(100)
    _shutdown(runtime)


def text(root: QQuickWindow, name: str) -> str:
    item = _find(root, name)
    value = item.property("text") if item is not None else None
    return value if isinstance(value, str) else ""


def active_tab(workspace: WorkspaceModel) -> str:
    typed = cast(Any, workspace)
    return str(typed.groups[typed.activeGroup]["active"])


def artist_tabs(workspace: WorkspaceModel) -> list[str]:
    typed = cast(Any, workspace)
    return [
        tab["id"]
        for group in typed.groups
        for tab in group["tabs"]
        if tab["id"].startswith("artist:")
    ]
