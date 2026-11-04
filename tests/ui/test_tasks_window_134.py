"""The Tasks window (plan 134.5): the session tasks on the left, one task's record on the right."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QCoreApplication
from PySide6.QtQuick import QQuickItem, QQuickWindow
from tests.ui.test_analysis_ui import _first, _items, _wait_for

from mtee.app import _build_runtime, _shutdown
from mtee.cli import parse_arguments
from mtee.services.jobs import JobContext


def _settle(seconds: float = 0.3) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)


def _quick(context: JobContext) -> None:
    context.report_items(2, 2, "")


def _partly_failed(context: JobContext) -> None:
    context.report_failure("song.flac", "Unreadable tags")
    context.report_items(2, 2, "")


def _visible_texts(item: QQuickItem) -> list[str]:
    found: list[str] = []
    pending = [item]
    while pending:
        current = pending.pop()
        text = current.property("text")
        if isinstance(text, str) and current.isVisible():
            found.append(text)
        pending.extend(current.childItems())
    return found


def test_the_tasks_window_lists_the_tasks_and_shows_the_record_of_the_one_selected(
    qapp, tmp_path: Path
) -> None:
    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(tmp_path / "data")]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        jobs_model = cast(Any, runtime.engine.rootContext().contextProperty("jobsModel"))
        workspace = cast(Any, runtime.workspace)
        runtime.jobs.submit(_quick, label="Analyze collection")
        failing = runtime.jobs.submit(_partly_failed, label="Move files")
        _wait_for(window, lambda: jobs_model.finishedCount == 2)

        workspace.openTasks()
        _wait_for(window, lambda: len(_items(window.contentItem(), "taskRow")) == 2)
        # The window lists the two tasks, newest first, and selects the first one by default.
        tasks = jobs_model.taskList()
        assert [task["label"] for task in tasks] == ["Move files", "Analyze collection"]
        assert "Analyze collection" in _visible_texts(window.contentItem())

        # Details of a notification selects its task on the right.
        workspace.openTasks(str(failing))
        _settle()
        assert str(failing) == tasks[0]["jobId"]
        assert _first(window.contentItem(), "taskTitle").property("text") == "Move files"
        failures = _first(window.contentItem(), "taskFailures")
        assert failures.isVisible()
        texts = _visible_texts(window.contentItem())
        assert "Items that failed (1)" in texts
        assert "Unreadable tags" in texts
        # The name is not a file path, so there is no Show in folder button.
        assert not [
            item for item in _items(window.contentItem(), "taskShowInFolder") if item.isVisible()
        ]

        # Selecting the other task shows its record instead.
        other = next(task for task in tasks if task["label"] == "Analyze collection")
        workspace.openTasks(str(other["jobId"]))
        _settle()
        assert _first(window.contentItem(), "taskTitle").property("text") == "Analyze collection"
        assert not _first(window.contentItem(), "taskFailures").isVisible()
    finally:
        _shutdown(runtime)
