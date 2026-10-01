"""Folder watcher: one settled signal per folder, a bounded set of paths."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QEvent

from mtee.services.folder_watch import MAX_WATCHED, FolderWatchService


def _dispose(service: FolderWatchService, qapp) -> None:
    service.close()
    service.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_several_writes_give_one_settled_signal(qapp, qtbot, tmp_path: Path) -> None:
    service = FolderWatchService(settle_ms=150)
    service.set_watched([str(tmp_path)])
    received: list[str] = []
    service.folderChanged.connect(received.append)

    for index in range(3):
        (tmp_path / f"file{index}.txt").write_text("x", encoding="utf-8")

    qtbot.waitUntil(lambda: len(received) >= 1, timeout=5_000)
    qtbot.wait(400)
    assert len(received) == 1
    _dispose(service, qapp)


def test_set_watched_drops_stale_paths_and_caps_the_set(qapp, tmp_path: Path) -> None:
    service = FolderWatchService()
    folders = []
    for index in range(MAX_WATCHED + 5):
        folder = tmp_path / f"f{index}"
        folder.mkdir()
        folders.append(str(folder))

    service.set_watched(folders)
    assert len(service.watched()) == MAX_WATCHED

    service.set_watched(folders[:1])
    assert service.watched() == [QDir.cleanPath(folders[0])]
    service.close()
    assert service.watched() == []
    _dispose(service, qapp)
