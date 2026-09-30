"""Selecting a track must not make the inspector raise QML errors."""

from __future__ import annotations

import time
import wave
from pathlib import Path

from PySide6.QtCore import QCoreApplication, qInstallMessageHandler

from mtee.app import _build_runtime, _shutdown
from mtee.cli import parse_arguments
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository


def _pump(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)


def test_the_inspector_reads_no_recovery_message_when_there_is_none(qapp, tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    with wave.open(str(music / "a.wav"), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 8_000)
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    root = LibraryRepository(database).add_root(music)
    database.close()

    messages: list[str] = []
    previous = qInstallMessageHandler(lambda _mode, _context, text: messages.append(text))
    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(tmp_path / "data")]))
    assert runtime is not None
    try:
        workspace = runtime.workspace
        assert isinstance(workspace, WorkspaceModel)
        library = workspace._library
        deadline = time.monotonic() + 15
        while not library.track_ids_in_tree(root["id"], "") and time.monotonic() < deadline:
            _pump(0.1)
        track_id = library.track_ids_in_tree(root["id"], "")[0]
        workspace.openFolder(f"root:{root['id']}")
        _pump(0.5)

        workspace.selectTrack(track_id)
        workspace.showRightPanel("info")
        _pump(1.0)
    finally:
        _shutdown(runtime)
        qInstallMessageHandler(previous)

    assert [text for text in messages if "InfoPanel" in text] == []
