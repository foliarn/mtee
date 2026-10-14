"""The Analysis settings tab and the right-click actions, in the live QML window."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

import pytest
from PySide6.QtCore import QCoreApplication, QObject, QPointF, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.helpers.analysis_audio import drum_loop, key_progression, write_wav

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions, parse_arguments
from mtee.models.demo_workspace import DemoWorkspace
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.ffmpeg_runtime import FfmpegRuntime, FfmpegRuntimeError

_RATE = 44_100


def _items(root: QQuickItem, name: str) -> list[QQuickItem]:
    found: list[QQuickItem] = []
    pending = [root]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            found.append(item)
        pending.extend(item.childItems())
    return found


def _first(root: QQuickItem, name: str) -> QQuickItem:
    items = _items(root, name)
    assert items, f"no QML item named {name}"
    return items[0]


def _centre(item: QQuickItem):
    return item.mapToScene(item.boundingRect().center()).toPoint()


def _click(window: QQuickWindow, item: QQuickItem, button=Qt.MouseButton.LeftButton) -> None:
    QTest.mouseClick(window, button, Qt.KeyboardModifier.NoModifier, _centre(item))
    QTest.qWait(30)


def test_the_analysis_tab_changes_the_settings(qapp, tmp_path: Path) -> None:
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application, AppOptions(data_dir=tmp_path / "settings", demo=True, scenario="explorer")
    )
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 1500)  # tall enough to show every row without scrolling
    workspace = cast(DemoWorkspace, runtime.workspace)
    settings = cast(QObject, workspace.property("analysisSettings"))
    try:
        workspace.openSettings()
        QTest.qWait(100)
        view = _first(window.contentItem(), "settingsView")
        assert not _items(view, "analysisSettings")[0].isVisible()

        _click(window, _first(view, "settingsTab_analysis"))
        page = _first(view, "analysisSettings")
        assert page.isVisible()

        assert settings.property("notation") == "camelot"
        _click(window, _first(_first(view, "notationSetting"), "choice_classic"))
        assert settings.property("notation") == "classic"

        # Raising the lowest tempo pushes the highest one up to keep a full octave.
        up = _first(_first(view, "bpmMinSetting"), "stepUp")
        for _ in range(9):
            _click(window, up)
        assert settings.property("bpmMin") == 115
        assert settings.property("bpmMax") == 230
        assert _first(_first(view, "bpmMaxSetting"), "stepValue").property("text") == "230"

        _click(window, _first(_first(view, "bpmDecimalsSetting"), "choice_1"))
        assert settings.property("bpmDecimals") == 1
        _click(window, _first(_first(view, "parallelSetting"), "stepUp"))
        assert settings.property("parallelJobs") == 2

        assert settings.property("writeTags") is False
        toggle = _first(view, "writeTagsSetting")
        switch = toggle.mapToScene(QPointF(toggle.width() - 20, toggle.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, switch)
        assert settings.property("writeTags") is True

        _click(window, _first(view, "settingsTab_general"))
        assert not page.isVisible()
    finally:
        _shutdown(runtime)


def _require_ffmpeg() -> None:
    try:
        FfmpegRuntime().executable("ffmpeg")
    except FfmpegRuntimeError:
        pytest.skip("The bundled FFmpeg runtime is unavailable.")


def _wait_for(window: QQuickWindow, predicate, seconds: float = 30.0) -> None:
    """Pump events without holding the interpreter lock, so worker threads can run."""
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    assert predicate()


def _live_library(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    data_dir = tmp_path / "data"
    music = tmp_path / "music"
    write_wav(
        music / "Sets" / "one.wav",
        0.5 * key_progression(9, True, 30, rate=_RATE) + 0.6 * drum_loop(128.0, 30, rate=_RATE),
        _RATE,
    )
    write_wav(
        music / "Sets" / "Deep" / "two.wav",
        0.5 * key_progression(0, False, 30, rate=_RATE) + 0.6 * drum_loop(140.0, 30, rate=_RATE),
        _RATE,
    )
    write_wav(music / "Other" / "three.wav", drum_loop(120.0, 30, rate=_RATE), _RATE)
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    root = LibraryRepository(database).add_root(music)
    database.close()
    return data_dir, music, root


def test_right_clicking_a_folder_analyzes_everything_inside_it(qapp, tmp_path: Path) -> None:
    _require_ffmpeg()
    data_dir, music, root = _live_library(tmp_path)

    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(data_dir)]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        workspace = cast(WorkspaceModel, runtime.workspace)
        workspace.setActivity("explorer")
        workspace.setSidebarVisible(True)
        root_id = str(root["id"])
        library = cast(Any, workspace)._library
        _wait_for(window, lambda: len(library.track_ids_in_tree(root_id, "")) == 3)

        _wait_for(window, lambda: any(_row_id(row) == f"root:{root_id}" for row in _rows(window)))
        row = next(row for row in _rows(window) if _row_id(row) == f"root:{root_id}")
        _click(window, row, Qt.MouseButton.RightButton)
        analyze = _visible_action(window, "analyzeAction")
        assert analyze.property("text") == "Analyze folder"
        _click(window, analyze)

        assert runtime.jobs.wait_for_done(60_000)
        analysis = cast(Any, workspace)._analysis_model
        analysis.flush_now()
        QTest.qWait(300)

        by_name = {
            name: workspace.track(str(owner))
            for name, owner in _tracks_by_name(music, root_id, workspace).items()
        }
        assert by_name["one.wav"]["bpm"] == pytest.approx(128.0, abs=0.05)
        assert by_name["one.wav"]["key"] == "8A"  # A minor on the Camelot wheel
        assert by_name["two.wav"]["bpm"] == pytest.approx(140.0, abs=0.05)  # in a sub-folder
        assert by_name["two.wav"]["key"] == "8B"  # C major
        assert by_name["three.wav"]["bpmText"] != ""  # the root includes every folder

        settings = cast(Any, workspace.property("analysisSettings"))
        settings.setNotation("classic")
        assert workspace.track(by_name["one.wav"]["id"])["key"] == "Am"
        settings.setBpmDecimals(0)
        assert workspace.track(by_name["one.wav"]["id"])["bpmText"] == "128"

        # Analyzing again does nothing until the user asks to re-analyze.
        workspace.analyzeFolder(f"root:{root_id}", False)
        assert runtime.jobs.wait_for_done(20_000)
        QTest.qWait(200)
        assert "Nothing to analyze" in cast(str, workspace.message)
    finally:
        _shutdown(runtime)


def test_right_clicking_a_track_analyzes_it_and_re_analyze_forces_it(qapp, tmp_path: Path) -> None:
    _require_ffmpeg()
    data_dir, music, root = _live_library(tmp_path)

    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(data_dir)]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        workspace = cast(WorkspaceModel, runtime.workspace)
        root_id = str(root["id"])
        library = cast(Any, workspace)._library
        _wait_for(window, lambda: len(library.track_ids_in_tree(root_id, "")) == 3)
        workspace.openFolder(f"folder:{root_id}/Sets")
        _wait_for(window, lambda: bool(_items(window.contentItem(), "trackRow_1")))
        QTest.qWait(400)  # the rows are rebuilt once when the scan settles
        rows = _items(window.contentItem(), "trackRow_1")
        _click(window, rows[0], Qt.MouseButton.RightButton)
        _click(window, _visible_action(window, "analyzeAction"))
        assert runtime.jobs.wait_for_done(60_000)

        analysis = cast(Any, workspace)._analysis_model
        analysis.flush_now()
        QTest.qWait(300)
        repository = cast(Any, analysis)._service._repository
        one = library.path_owner(music / "Sets" / "one.wav")
        others = [
            library.path_owner(music / "Sets" / "Deep" / "two.wav"),
            library.path_owner(music / "Other" / "three.wav"),
        ]
        assert repository.get(one).bpm == pytest.approx(128.0, abs=0.05)
        assert all(repository.get(other) is None for other in others)  # only the clicked track

        # "Analyze" again is a no-op: the track already has its result.
        _click(window, _items(window.contentItem(), "trackRow_1")[0], Qt.MouseButton.RightButton)
        _click(window, _visible_action(window, "analyzeAction"))
        assert runtime.jobs.wait_for_done(20_000)
        QTest.qWait(200)
        assert "Nothing to analyze" in cast(str, workspace.message)
        jobs = [s for s in runtime.jobs.statuses() if s.label == "Analyze 1 track"]
        assert len(jobs) == 2 and all(job.state.value == "succeeded" for job in jobs)
    finally:
        _shutdown(runtime)


def _rows(window: QQuickWindow) -> list[QQuickItem]:
    return _items(window.contentItem(), "explorerRow")


def _row_id(row: QQuickItem) -> str:
    return str(cast(dict, row.property("modelData")).get("id", ""))


def _visible_action(window: QQuickWindow, name: str) -> QQuickItem:
    """Return the open menu entry called ``name``, as a user would see and click it."""
    visible = [item for item in _items(window.contentItem(), name) if item.isVisible()]
    assert len(visible) == 1, f"expected one open menu entry {name}, found {len(visible)}"
    return visible[0]


def _tracks_by_name(music: Path, root_id: str, workspace: WorkspaceModel) -> dict[str, str]:
    library = cast(Any, workspace)._library
    return {path.name: library.path_owner(path) for path in sorted(music.rglob("*.wav"))}
