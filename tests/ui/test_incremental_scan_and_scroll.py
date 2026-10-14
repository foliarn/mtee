"""Startup rescans reuse unchanged metadata and preserve a live row position."""

from __future__ import annotations

import wave
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.app import _build_runtime, _shutdown
from mtee.cli import parse_arguments
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.player_backend import BackendEventHandler


class _QuietBackend:
    def __init__(self) -> None:
        self.handler: BackendEventHandler | None = None

    def set_event_handler(self, handler: BackendEventHandler | None) -> None:
        self.handler = handler

    def load(self, _path: Path, _session_id: int) -> None:
        return

    def set_paused(self, _paused: bool) -> None:
        return

    def seek(self, _position_us: int) -> None:
        return

    def set_volume(self, _value: int) -> None:
        return

    def set_gain_db(self, _value: float) -> None:
        return

    def position_us(self) -> int:
        return 0

    def stop(self) -> None:
        return

    def close(self) -> None:
        return


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 8)


def _find(root: QQuickWindow, name: str) -> QQuickItem | None:
    pending = [root.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def test_rescan_reuses_unchanged_metadata_and_keeps_track_84_in_view(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    audio_root = tmp_path / "library copy"
    for index in range(140):
        _write_wav(audio_root / f"track-{index:03d}.wav")

    data_dir = tmp_path / "isolated app data"
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    root_record = LibraryRepository(database).add_root(audio_root)
    database.close()

    backend = _QuietBackend()
    monkeypatch.setattr("mtee.app.MpvBackend", lambda: backend)
    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(data_dir)]))
    assert runtime is not None
    window = runtime.engine.rootObjects()[0]
    assert isinstance(window, QQuickWindow)
    window.resize(1440, 900)
    workspace = runtime.workspace
    assert isinstance(workspace, WorkspaceModel)

    try:
        assert runtime.jobs.wait_for_done(10_000)
        workspace.openFolder(f"folder:{root_record['id']}/")
        QCoreApplication.processEvents()
        list_view = _find(window, "trackRowsList")
        assert list_view is not None
        list_view.setProperty("contentY", 83 * 56)
        QCoreApplication.processEvents()
        position_before_play = float(list_view.property("contentY"))
        target = _find(window, "trackRow_84")
        assert target is not None and target.isVisible()
        expected_id = workspace.tabTracks("folder", f"{root_record['id']}/", "index", True)[83][
            "id"
        ]

        QTest.mouseDClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos=target.mapToScene(target.boundingRect().center()).toPoint(),
        )
        QCoreApplication.processEvents()
        assert workspace.playingId == expected_id
        assert workspace.activeFolder == f"folder:{root_record['id']}/"
        assert float(list_view.property("contentY")) == position_before_play

        model = workspace.trackModelForTab(
            f"folder:{root_record['id']}/", "folder", f"{root_record['id']}/", "index", True
        )
        resets: list[bool] = []
        tree_resets: list[bool] = []
        model.modelReset.connect(lambda: resets.append(True))
        workspace._folder_model.modelReset.connect(lambda: tree_resets.append(True))
        reads: list[Path] = []
        original_read = workspace._reader.read

        def count_read(path: Path):
            reads.append(path)
            return original_read(path)

        monkeypatch.setattr(workspace._reader, "read", count_read)
        workspace.resumeRoots()
        assert runtime.jobs.wait_for_done(10_000)
        QCoreApplication.processEvents()

        assert not reads
        assert not resets
        assert not tree_resets
        assert float(list_view.property("contentY")) == position_before_play
        assert workspace.activeFolder == f"folder:{root_record['id']}/"

        changed_path = audio_root / "track-083.wav"
        with changed_path.open("ab") as handle:
            handle.write(b"revised source")
        new_path = audio_root / "track-140.wav"
        _write_wav(new_path)
        (audio_root / "track-000.wav").unlink()
        workspace.resumeRoots()
        assert runtime.jobs.wait_for_done(10_000)
        QCoreApplication.processEvents()

        assert sorted(reads) == sorted([changed_path, new_path])
        assert not resets
        assert not tree_resets
        rows_after_change = workspace.tabTracks("folder", f"{root_record['id']}/", "index", True)
        assert len(rows_after_change) == 140
        assert rows_after_change[82]["id"] == expected_id
        row_after_change = _find(window, "trackRow_83")
        assert row_after_change is not None and row_after_change.isVisible()
        list_top = list_view.mapToScene(list_view.boundingRect().topLeft()).y()
        row_top = row_after_change.mapToScene(row_after_change.boundingRect().topLeft()).y()
        assert abs(row_top - list_top) < 4
        assert workspace.activeFolder == f"folder:{root_record['id']}/"
    finally:
        _shutdown(runtime)
