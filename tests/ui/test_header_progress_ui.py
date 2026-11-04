"""The header progress strip (plan 134.3) and the notifications bell with its balloon (134.4)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QCoreApplication, QObject
from PySide6.QtQuick import QQuickItem, QQuickWindow
from tests.ui.test_analysis_ui import _click, _first, _items, _wait_for

from mtee.app import _build_runtime, _shutdown
from mtee.cli import parse_arguments
from mtee.services.jobs import JobContext


def _settle(seconds: float = 0.2) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)


def _blocking(gate: threading.Event, total: int):
    """A job that reports one item out of ``total`` and then waits until ``gate`` is set."""

    def task(context: JobContext) -> None:
        context.report_items(1, total, "first element")
        while not gate.is_set():
            context.sleep(0.02)

    return task


def _quick(context: JobContext) -> None:
    context.report_items(2, 2, "")


def _texts(item: QQuickItem) -> list[str]:
    found: list[str] = []
    pending = [item]
    while pending:
        current = pending.pop()
        text = current.property("text")
        if isinstance(text, str) and current.isVisible():
            found.append(text)
        pending.extend(current.childItems())
    return found


def test_the_strip_shows_the_running_job_its_count_and_the_others(qapp, tmp_path: Path) -> None:
    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(tmp_path / "data")]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    first_gate = threading.Event()
    second_gate = threading.Event()
    try:
        strip = _first(window.contentItem(), "taskProgress")
        assert not strip.isVisible()  # no job, no strip

        runtime.jobs.submit(_blocking(first_gate, 3), label="Analyze collection")
        _wait_for(window, lambda: strip.isVisible())
        label = _first(strip, "taskProgressLabel")
        count = _first(strip, "taskProgressCount")
        assert label.property("text") == "Analyze collection"
        _wait_for(window, lambda: count.property("text") == "1 / 3")

        runtime.jobs.submit(_blocking(second_gate, 5), label="Move files to Jazz")
        more = _first(strip, "taskProgressMore")
        _wait_for(window, lambda: more.isVisible())
        assert more.property("text") == "+1"
        # The most recently started job names the strip.
        assert label.property("text") == "Move files to Jazz"

        # The click lists both running jobs, each with its Cancel button.
        _click(window, _first(strip, "taskProgressButton"))
        _settle()
        popover = strip.findChild(QObject, "taskPopover")
        assert popover is not None and bool(popover.property("opened"))
        rows = _items(window.contentItem(), "taskRow")
        labels = {str(row.property("label")) for row in rows if row.isVisible()}
        assert {"Analyze collection", "Move files to Jazz"} <= labels
        newest = next(
            row for row in rows if row.isVisible() and row.property("label") == "Move files to Jazz"
        )
        _click(window, _first(newest, "taskCancel"))

        # Cancel the newest job: the strip falls back to the other one.
        _wait_for(window, lambda: label.property("text") == "Analyze collection")
        _wait_for(window, lambda: not more.isVisible())
    finally:
        first_gate.set()
        second_gate.set()
        _shutdown(runtime)


def test_a_finished_job_rings_the_bell_and_the_balloon_opens_its_details(
    qapp, tmp_path: Path
) -> None:
    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(tmp_path / "data")]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        bell = _first(window.contentItem(), "notificationBell")
        balloon = _first(window.contentItem(), "notificationBalloon")
        assert not balloon.isVisible()

        runtime.jobs.submit(_quick, label="Analyze collection")
        _wait_for(window, lambda: balloon.isVisible())
        assert "Analyze collection: done" in _texts(balloon) or any(
            "Analyze collection" in text for text in _texts(balloon)
        )
        # The bell badge counts the new notification.
        assert [text for text in _texts(bell) if text == "1"]

        # The bell lists it under Notifications; opening it marks it read.
        _click(window, _first(window.contentItem(), "notificationButton"))
        _settle()
        rows = [
            item for item in _items(window.contentItem(), "notificationRow") if item.isVisible()
        ]
        assert len(rows) == 1
        assert [text for text in _texts(bell) if text == "1"] == []

        # Details opens the Tasks window on that job.
        _click(window, _first(window.contentItem(), "notificationDetails"))
        _settle()
        workspace = runtime.workspace
        assert str(cast(Any, workspace).activeTabId).startswith("tasks:")
    finally:
        _shutdown(runtime)
