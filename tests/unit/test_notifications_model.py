"""Session notifications: one row per visible job that ended, unread count, clear, dismiss."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any, cast

import pytest
from PySide6.QtCore import QByteArray

from mtee.domain.job_summaries import analysis_summary
from mtee.domain.jobs import JobState
from mtee.models.notifications_model import NotificationsModel
from mtee.services.jobs import JobContext, JobService


@pytest.fixture
def service(qapp) -> Iterator[JobService]:
    created = JobService(max_thread_count=2)
    yield created
    created.shutdown(2_000)


def _finish_visible_job(qtbot, service: JobService, label: str, summary=None) -> str:
    def task(context: JobContext) -> None:
        context.report_items(3, 3, "x")

    job_id = service.submit(task, label=label, summary=summary)
    qtbot.waitUntil(lambda: bool(service.status(job_id).summary))
    return str(job_id)


def test_a_finished_visible_job_adds_one_notification(qtbot, service: JobService) -> None:
    model = NotificationsModel(service)
    job_id = _finish_visible_job(qtbot, service, "Analyze collection", analysis_summary())

    qtbot.waitUntil(lambda: model.rowCount() == 1)
    latest = _latest(model)
    assert latest["jobId"] == job_id
    assert latest["title"] == "Analyze collection"
    assert latest["text"] == "3 songs analysed, 0 errors"
    assert latest["tone"] == "neutral"
    assert latest["read"] is False
    assert model.unreadCount == 1


def test_a_hidden_job_never_notifies(qtbot, service: JobService) -> None:
    model = NotificationsModel(service)
    hidden = service.submit(lambda _context: None, label="Routine check", visible=False)
    qtbot.waitUntil(lambda: service.status(hidden).is_terminal)
    # A visible job that ends after the hidden one marks the point where the hidden one was seen.
    _finish_visible_job(qtbot, service, "Move files to Jazz")

    qtbot.waitUntil(lambda: model.rowCount() == 1)
    assert _latest(model)["title"] == "Move files to Jazz"


def test_a_failed_job_is_a_warning_and_a_partial_failure_too(qtbot, service: JobService) -> None:
    model = NotificationsModel(service)

    def task(context: JobContext) -> None:
        raise RuntimeError("disk is full")

    job_id = service.submit(task, label="Save metadata")
    qtbot.waitUntil(lambda: bool(service.status(job_id).summary))

    qtbot.waitUntil(lambda: model.rowCount() == 1)
    assert _latest(model)["tone"] == "warning"
    assert service.status(job_id).state is JobState.FAILED


def test_each_job_adds_its_notification_once(qtbot, service: JobService) -> None:
    model = NotificationsModel(service)
    _finish_visible_job(qtbot, service, "Save metadata")
    qtbot.waitUntil(lambda: model.rowCount() == 1)
    qtbot.wait(50)

    assert model.rowCount() == 1


def test_mark_all_read_and_clear(qtbot, service: JobService) -> None:
    model = NotificationsModel(service)
    _finish_visible_job(qtbot, service, "Save metadata")
    _finish_visible_job(qtbot, service, "Move files to Jazz")
    qtbot.waitUntil(lambda: model.rowCount() == 2)
    assert model.unreadCount == 2

    model.markAllRead()
    assert model.unreadCount == 0

    model.clear()
    assert model.rowCount() == 0
    assert model.unreadCount == 0
    assert _latest(model) == {}


def test_dismiss_removes_one_notification(qtbot, service: JobService) -> None:
    model = NotificationsModel(service)
    _finish_visible_job(qtbot, service, "Save metadata")
    _finish_visible_job(qtbot, service, "Move files to Jazz")
    qtbot.waitUntil(lambda: model.rowCount() == 2)
    older = model.index(1, 0)
    older_id = model.data(older, _role(model, "id"))

    model.dismiss(older_id)

    assert model.rowCount() == 1
    assert _latest(model)["title"] == "Move files to Jazz"


def test_open_details_marks_read_and_asks_for_the_job(qtbot, service: JobService) -> None:
    opened: list[str] = []
    model = NotificationsModel(service, open_tasks=opened.append)
    job_id = _finish_visible_job(qtbot, service, "Save metadata")
    qtbot.waitUntil(lambda: model.rowCount() == 1)

    model.openDetails(_latest(model)["id"])

    assert opened == [job_id]
    assert model.unreadCount == 0


def test_demo_rows_are_fixed_and_have_no_job(qtbot, service: JobService) -> None:
    model = NotificationsModel(service)
    model.seed_demo()

    assert model.rowCount() == 3
    assert model.unreadCount == 3
    assert _latest(model)["jobId"] == ""


def test_the_summary_is_written_before_the_notification(qtbot, service: JobService) -> None:
    model = NotificationsModel(service)
    main = threading.current_thread()
    threads: list[bool] = []

    def summary(status) -> str:
        threads.append(threading.current_thread() is main)
        return "Done"

    _finish_visible_job(qtbot, service, "Scan", summary)
    qtbot.waitUntil(lambda: model.rowCount() == 1)

    assert _latest(model)["text"] == "Done"
    assert threads == [True]


def _latest(model: NotificationsModel) -> dict[str, Any]:
    return cast(dict[str, Any], model.latest)


def _role(model: NotificationsModel, name: str) -> int:
    for role, value in model.roleNames().items():
        if value == QByteArray(name.encode()):
            return int(role)
    raise AssertionError(name)
