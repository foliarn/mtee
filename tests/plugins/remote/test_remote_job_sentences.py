"""The sentence each visible job of the plugin ends with (MTEE 0.3.0 notifications).

The core writes one sentence per finished job in the notifications of the header. ``tasks.submit``
gives it the plugin's sentence, built from the job's result; a failed job gets the core's generic
sentence with its readable error, so the plugin does not announce the outcome a second time.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from mtee.plugins.remote.conflicts import settled_sentence  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.connection import (  # pyright: ignore[reportMissingImports]
    _Session,
    connected_sentence,
)
from mtee.plugins.remote.engine import (  # pyright: ignore[reportMissingImports]
    PassResult,
    pass_sentence,
)
from mtee.plugins.remote.first_match import (  # pyright: ignore[reportMissingImports]
    MatchReport,
    SyncSummary,
    matched_sentence,
    sync_set_up_sentence,
)
from mtee.plugins.remote.matcher import MatchResult  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.push import (  # pyright: ignore[reportMissingImports]
    DetectReport,
    QueueReport,
)
from mtee.plugins.remote.tasks import submit  # pyright: ignore[reportMissingImports]
from tests.plugins.remote.helpers import FakeLibrary, make_context

from mtee.domain.jobs import JobId
from mtee.plugins.api import JobContext, PluginContext


class RecordingJobs:
    """Keeps the task and the summary of the one job submitted, to run them by hand."""

    def __init__(self) -> None:
        self.task: Callable[[JobContext], None] | None = None
        self.summary: Callable[[Any], str] | None = None
        self.kwargs: dict[str, Any] = {}

    def submit(self, task: Callable[[JobContext], None], **kwargs: Any) -> JobId:
        self.task = task
        self.summary = kwargs.pop("summary", None)
        self.kwargs = kwargs
        return JobId.new()


@pytest.fixture
def context(tmp_path: Path) -> PluginContext:
    return dataclasses.replace(
        make_context(tmp_path, FakeLibrary([tmp_path / "music"], [])),
        run_on_gui=lambda call: call(),
    )


def _with_jobs(context: PluginContext) -> tuple[PluginContext, RecordingJobs]:
    jobs = RecordingJobs()
    return dataclasses.replace(context, jobs=cast(Any, jobs)), jobs


def test_a_job_that_returns_ends_with_the_sentence_of_its_result(context: PluginContext) -> None:
    running, jobs = _with_jobs(context)
    done: list[tuple[object, object]] = []

    submit(
        running,
        "Counting",
        lambda _job: 3,
        lambda result, error: done.append((result, error)),
        summary=lambda count: f"{count} counted.",
    )

    assert jobs.kwargs == {"label": "Counting", "visible": True}
    assert jobs.summary is not None and jobs.task is not None
    assert jobs.summary(None) == "", "no sentence before the result"
    jobs.task(cast(JobContext, None))
    assert done == [(3, None)]
    assert jobs.summary(None) == "3 counted."


def test_a_failed_job_leaves_the_sentence_to_the_core(context: PluginContext) -> None:
    running, jobs = _with_jobs(context)
    done: list[tuple[object, object]] = []

    def fail(_job: JobContext) -> int:
        raise RuntimeError("The server cannot be reached.")

    submit(running, "Counting", fail, lambda r, e: done.append((r, e)), summary=str)
    assert jobs.task is not None and jobs.summary is not None
    with pytest.raises(RuntimeError):
        jobs.task(cast(JobContext, None))
    assert done[0][0] is None
    assert jobs.summary(None) == "", "the core writes '<label>: failed (...)'"


def test_a_job_without_a_summary_is_submitted_as_before(context: PluginContext) -> None:
    running, jobs = _with_jobs(context)
    submit(running, "Reading", lambda _job: None, lambda r, e: None, visible=False)
    assert jobs.summary is None
    assert jobs.kwargs == {"label": "Reading", "visible": False}


def test_the_pass_sentence_says_what_was_sent_and_what_waits() -> None:
    detected = DetectReport()
    assert pass_sentence(PassResult(detected, QueueReport(sent=1))) == (
        "1 change sent to MTEE Remote."
    )
    assert pass_sentence(PassResult(detected, QueueReport(sent=12, blocked=1, failed=2))) == (
        "12 changes sent to MTEE Remote, 1 blocked, 2 failed."
    )
    assert pass_sentence(PassResult(detected, QueueReport(sent=3, pending=4, stopped=True))) == (
        "3 changes sent to MTEE Remote; the server could not be reached, 4 still wait."
    )
    assert pass_sentence(PassResult(detected, None)) == (
        "Changes of this computer queued for MTEE Remote."
    )


def test_the_connect_sentence_names_the_server_and_the_device() -> None:
    session = _Session(
        url="https://music.example.net",
        username="ana",
        device_id="d1",
        device_name="Studio laptop",
        token="secret",
    )
    assert connected_sentence(session) == "Connected to music.example.net as Studio laptop."
    offline = dataclasses.replace(session, offline="The server cannot be reached.")
    assert connected_sentence(offline) == (
        "Signed in to music.example.net as Studio laptop, but the server is offline now."
    )
    assert "secret" not in connected_sentence(session)


def test_the_first_match_sentences() -> None:
    report = MatchReport(
        result=MatchResult(),
        local_total=2617,
        server_total=2700,
        skipped=0,
        unhashed=0,
        mappings=1,
    )
    assert matched_sentence(report) == (
        "Compared 2,617 tracks of this computer with 2,700 on the server."
    )
    summary = SyncSummary(linked=5, conflicts=2, queued=1, server_items=3, waiting=("c1", "c2"))
    assert sync_set_up_sentence(summary, "computer") == (
        "Sync set up: 5 linked, 1 to upload, 3 server only, 2 with the same audio being settled."
    )
    assert sync_set_up_sentence(summary, "later") == (
        "Sync set up: 5 linked, 1 to upload, 3 server only, 2 tags to decide."
    )


def test_the_settle_sentence_says_where_a_failed_pair_waits() -> None:
    assert (
        settled_sentence("this computer's", (2, 0)) == "Kept this computer's version of 2 tracks."
    )
    assert settled_sentence("the server's", (1, 1)) == (
        "Kept the server's version of 1 track. 1 track could not be settled: "
        "they stay in Conflicts with the reason."
    )
