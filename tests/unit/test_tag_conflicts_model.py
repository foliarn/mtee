from __future__ import annotations

import time

from PySide6.QtCore import QCoreApplication, Qt

from mtee.domain.tag_conflicts import TagConflict, TagConflictEntry
from mtee.models.tag_conflicts_model import TagConflictRole, TagConflictsModel
from mtee.services.jobs import JobService


def _conflict(track: str = "t1", name: str = "one.flac", value: str = "8A") -> TagConflict:
    return TagConflict(
        track,
        name,
        (
            TagConflictEntry("key", ("KEY", "INITIALKEY"), value),
            TagConflictEntry("bpm", ("BPM", "TEMPO"), "126"),
        ),
    )


def _wait(predicate, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert predicate()


def test_a_conflict_is_listed_with_readable_roles(qapp) -> None:
    model = TagConflictsModel()
    notices: list[str] = []
    model.noticeRaised.connect(notices.append)

    model.add(_conflict())

    assert model.count == 1
    index = model.index(0, 0)
    assert model.data(index, TagConflictRole.FILE_NAME) == "one.flac"
    assert model.data(index, TagConflictRole.STATE) == "pending"
    summary = model.data(index, TagConflictRole.SUMMARY)
    assert summary == "Key: KEY, INITIALKEY → 8A\nBPM: BPM, TEMPO → 126"
    assert notices == [
        "1 track with tags stored under several names. Open Tasks to replace the old values."
    ]
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "one.flac"


def test_a_newer_conflict_for_the_same_track_replaces_the_older_one(qapp) -> None:
    model = TagConflictsModel()
    model.add(_conflict("t1", value="8A"))
    model.add(_conflict("t2", name="two.flac"))
    model.add(_conflict("t1", value="9A"))

    assert model.count == 2
    assert model.data(model.index(1, 0), TagConflictRole.SUMMARY).startswith(
        "Key: KEY, INITIALKEY → 9A"
    )
    assert model.data(model.index(0, 0), TagConflictRole.FILE_NAME) == "two.flac"


def test_nothing_is_recorded_without_a_field_to_write(qapp) -> None:
    model = TagConflictsModel()
    model.add(TagConflict("t1", "one.flac", ()))
    model.add("not a conflict")
    assert model.count == 0


def test_dismissing_forgets_the_conflict_without_resolving_it(qapp) -> None:
    calls: list[str] = []
    jobs = JobService(qapp, max_thread_count=1)
    model = TagConflictsModel(jobs, lambda conflict: calls.append(conflict.track_id) or "")
    model.add(_conflict("t1"))
    model.add(_conflict("t2"))

    model.dismiss("t1")
    model.dismissAll()

    assert model.count == 0
    assert calls == []
    jobs.begin_shutdown()
    jobs.wait_for_done(2_000)


def test_a_resolved_conflict_disappears_and_announces_its_track(qapp) -> None:
    written: list[str] = []
    jobs = JobService(qapp, max_thread_count=2)
    model = TagConflictsModel(jobs, lambda conflict: written.append(conflict.track_id) or "")
    resolved: list[list[str]] = []
    model.resolved.connect(resolved.append)
    model.add(_conflict("t1"))
    model.add(_conflict("t2", name="two.flac"))

    model.resolveAll()

    _wait(lambda: model.count == 0)
    assert sorted(written) == ["t1", "t2"]
    assert sorted(item[0] for item in resolved) == ["t1", "t2"]
    jobs.begin_shutdown()
    jobs.wait_for_done(2_000)


def test_a_failed_replacement_stays_listed_with_its_reason_and_can_be_retried(qapp) -> None:
    attempts = {"count": 0}

    def resolver(_conflict: TagConflict) -> str:
        attempts["count"] += 1
        return (
            "Stop playback or wait for the file to become available."
            if attempts["count"] == 1
            else ""
        )

    jobs = JobService(qapp, max_thread_count=1)
    model = TagConflictsModel(jobs, resolver)
    model.add(_conflict("t1"))

    model.resolve("t1")
    _wait(lambda: model.data(model.index(0, 0), TagConflictRole.STATE) == "error")
    assert "Stop playback" in model.data(model.index(0, 0), TagConflictRole.ERROR_MESSAGE)
    assert model.count == 1

    model.resolve("t1")
    _wait(lambda: model.count == 0)
    assert attempts["count"] == 2
    jobs.begin_shutdown()
    jobs.wait_for_done(2_000)


def test_a_resolver_that_raises_is_reported_as_a_failure(qapp) -> None:
    def resolver(_conflict: TagConflict) -> str:
        raise OSError("disk unavailable")

    jobs = JobService(qapp, max_thread_count=1)
    model = TagConflictsModel(jobs, resolver)
    model.add(_conflict("t1"))

    model.resolve("t1")

    _wait(lambda: model.data(model.index(0, 0), TagConflictRole.STATE) == "error")
    assert "disk unavailable" in model.data(model.index(0, 0), TagConflictRole.ERROR_MESSAGE)
    jobs.begin_shutdown()
    jobs.wait_for_done(2_000)
