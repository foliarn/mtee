"""The live column chooser updates QML headers from Qt sequence properties."""

from __future__ import annotations

import wave
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.tracks import SourceRevision
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.player_backend import BackendEventHandler


class _Backend:
    def set_event_handler(self, _handler: BackendEventHandler | None) -> None:
        pass

    def load(self, _path: Path, _session_id: int) -> None:
        pass

    def set_paused(self, _paused: bool) -> None:
        pass

    def seek(self, _position_us: int) -> None:
        pass

    def set_ab_loop(self, _start_us: int | None, _end_us: int | None) -> None:
        pass

    def set_volume(self, _value: int) -> None:
        pass

    def position_us(self) -> int:
        return 0

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


def _find(root: QQuickWindow, name: str) -> QQuickItem | None:
    pending = [root.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 800)


def test_column_menu_updates_a_real_live_header(qapp, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _Backend)
    library_path = tmp_path / "library"
    audio_path = library_path / "one.wav"
    _write_wav(audio_path)
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root_record = library.add_root(library_path)
    generation = library.begin_scan(root_record["id"])
    library.upsert_location(
        root_record["id"],
        "one.wav",
        audio_path,
        SourceRevision.observe(audio_path),
        MetadataSnapshot(album=("Test album",)),
        generation,
    )
    library.finish_scan(root_record["id"], generation, complete=True)
    database.close()

    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    workspace = runtime.workspace
    assert isinstance(workspace, WorkspaceModel)
    assert runtime.jobs.wait_for_done(5_000)
    workspace.openFolder(f"root:{root_record['id']}")
    QCoreApplication.processEvents()
    QTest.qWait(100)
    chooser = _find(root, "chooseColumnsButton")
    assert chooser is not None and chooser.isVisible()
    assert _find(root, "columnHeader_album") is None

    point = chooser.mapToScene(chooser.boundingRect().center()).toPoint()
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, pos=point)
    QCoreApplication.processEvents()
    QTest.qWait(50)
    option = _find(root, "columnOption_album")
    assert option is not None and option.isVisible()
    option_point = option.mapToScene(option.boundingRect().center()).toPoint()
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, pos=option_point)
    QCoreApplication.processEvents()
    QTest.qWait(50)

    try:
        header = _find(root, "columnHeader_album")
        assert header is not None and header.isVisible()
    finally:
        _shutdown(runtime)
        application.quit()
