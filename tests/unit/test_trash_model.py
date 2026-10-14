"""Characterization of TrashModel: confirmation, recycling, refusals, retry and history.

The Windows Shell is never reached: the model receives a fake service at its boundary, which
"recycles" by deleting a file inside ``tmp_path``. The library, the journal and the file access
coordinator are real, on a temporary SQLite database.
"""

from __future__ import annotations

import gc
import sqlite3
import threading
import time
import wave
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import pytest
import shiboken6
from PySide6.QtCore import QObject, Signal

from mtee.domain.jobs import JobState
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.models.trash_model import TrashModel, _TrashBatchError
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.trash_repository import TrashRepository
from mtee.services.file_access import FileAccessCoordinator, FileLease
from mtee.services.jobs import JobService
from mtee.services.trash_service import TrashServiceError

_DEADLINE_SECONDS = 15.0


class _FakeTrashService:
    """Stands in for the Shell: records calls and removes the file like a recycle would."""

    def __init__(self) -> None:
        self.calls: list[Path] = []
        self.errors: dict[str, Exception] = {}
        self.entered = threading.Event()
        self.gate: threading.Event | None = None
        self.before_return: Callable[[Path], None] | None = None

    def recycle(self, path: Path | str) -> str:
        source = Path(path)
        self.calls.append(source)
        self.entered.set()
        if self.gate is not None:
            assert self.gate.wait(_DEADLINE_SECONDS), "the test never released the fake Shell"
        error = self.errors.get(source.name)
        if error is not None:
            raise error
        source.unlink()
        if self.before_return is not None:
            self.before_return(source)
        return f"C:\\$Recycle.Bin\\S-1-5-21\\$R{len(self.calls):04d}{source.suffix}"


class _FakePlayer(QObject):
    trackAccessReleased = Signal(str)  # noqa: N815
    playbackChanged = Signal()  # noqa: N815

    def __init__(self) -> None:
        super().__init__()
        self.playing_id = ""
        self.stop_calls: list[str] = []
        self.stop_result = True
        self.on_stop: Callable[[], None] | None = None

    def playing_id_value(self) -> str:
        return self.playing_id

    def stopAndRelease(self, track_id: str = "") -> bool:  # noqa: N802
        self.stop_calls.append(track_id)
        if self.on_stop is not None:
            self.on_stop()
        return self.stop_result


class _HookedAccess(FileAccessCoordinator):
    """Runs a hook each time the exclusive access is requested, before delegating."""

    def __init__(self) -> None:
        super().__init__()
        self.on_acquire: Callable[[], None] | None = None

    @contextmanager
    def acquire(
        self, track_id: TrackId, purpose: str, *, timeout_seconds: float | None = None
    ) -> Iterator[FileLease]:
        if self.on_acquire is not None:
            self.on_acquire()
        with super().acquire(track_id, purpose, timeout_seconds=timeout_seconds) as lease:
            yield lease


class _Env:
    def __init__(self, qapp: Any, base: Path) -> None:
        self.qapp = qapp
        self.music = base / "music"
        (self.music / "sub").mkdir(parents=True)
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.root_id = self.library.add_root(self.music)["id"]
        self.access = _HookedAccess()
        self.journal = TrashRepository(self.database)
        self.jobs = JobService(max_thread_count=2)
        self.service = _FakeTrashService()
        self.models: list[TrashModel] = []

    def add_track(self, relative: str) -> str:
        path = self.music / relative
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 800)
        generation = self.library.begin_scan(self.root_id)
        self.library.upsert_locations(
            self.root_id,
            [
                (
                    relative,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(title=(path.stem,), technical=TechnicalInfo(duration_us=100)),
                )
            ],
            generation,
        )
        owner = self.library.path_owner(path)
        assert owner is not None
        return owner

    def make_model(self, player: _FakePlayer | None = None) -> TrashModel:
        model = TrashModel(
            self.library,
            self.jobs,
            cast(Any, self.service),
            self.access,
            self.journal,
            player=cast(Any, player),
        )
        self.models.append(model)
        self.settle()
        return model

    def settle(self) -> None:
        """Let finished jobs deliver their queued signals to the model."""
        assert self.jobs.wait_for_done(int(_DEADLINE_SECONDS * 1000))
        self.qapp.processEvents()

    def wait(self, condition: Callable[[], bool]) -> None:
        deadline = time.monotonic() + _DEADLINE_SECONDS
        while not condition():
            assert time.monotonic() < deadline, "the model did not reach the expected state"
            self.qapp.processEvents()
            time.sleep(0.005)

    def prepare(self, model: TrashModel, ids: list[str]) -> None:
        model.request_recycle(ids)
        self.wait(lambda: model.state != "preparing")

    def run_to_result(self, model: TrashModel, ids: list[str]) -> None:
        self.prepare(model, ids)
        assert model.state == "confirm"
        model.confirm()
        self.wait(lambda: model.state == "result")
        self.settle()

    def journal_rows(self) -> list[tuple[str, str, str, str]]:
        rows = self.database.connection().execute(
            "SELECT track_id,status,result_message,recycle_item_identity "
            "FROM trash_operations ORDER BY rowid"
        )
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    def present(self, track_id: str) -> list[int]:
        rows = self.database.connection().execute(
            "SELECT present FROM root_tracks WHERE track_id=?", (track_id,)
        )
        return [int(r[0]) for r in rows]

    def job_status(self, label: str):
        matching = [s for s in self.jobs.statuses() if s.label == label]
        assert len(matching) == 1
        return matching[0]


@pytest.fixture
def env(qapp, tmp_path: Path) -> Iterator[_Env]:
    created = _Env(qapp, tmp_path)
    yield created
    created.jobs.shutdown()
    created.settle()
    created.database.close()
    # Destroy the Qt objects now, in order, instead of letting the garbage collector do it
    # in the middle of a later test.
    for model in created.models:
        shiboken6.delete(model)
    created.models.clear()
    shiboken6.delete(created.jobs)
    gc.collect()


def _results(model: TrashModel) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], model.results)


def _statuses(model: TrashModel) -> list[str]:
    return [item["status"] for item in _results(model)]


# --- initial state -------------------------------------------------------------------------


def test_a_new_model_is_idle_with_nothing_selected(env: _Env) -> None:
    model = env.make_model()
    assert model.state == "idle"
    assert model.message == ""
    assert model.selectedCount == 0
    assert _results(model) == []
    assert not model.canConfirm
    assert not model.canStopPlaybackAndContinue
    assert not model.hasBusyFiles
    assert not model.canCancel
    assert env.journal_rows() == []


def test_confirm_retry_stop_and_cancel_do_nothing_while_idle(env: _Env) -> None:
    model = env.make_model()
    changes: list[int] = []
    model.changed.connect(lambda: changes.append(1))
    model.confirm()
    model.retry_busy()
    model.stop_playback_and_continue()
    model.cancel()
    env.settle()
    assert model.state == "idle"
    assert changes == []
    assert env.service.calls == []


def test_the_model_stays_idle_when_the_history_check_cannot_be_submitted(env: _Env) -> None:
    env.jobs.begin_shutdown()
    model = env.make_model()
    assert model.state == "idle"


# --- preparation ---------------------------------------------------------------------------


def test_request_recycle_ignores_empty_and_blank_ids(env: _Env) -> None:
    model = env.make_model()
    model.request_recycle([])
    model.request_recycle(["", ""])
    assert model.state == "idle"
    assert model.selectedCount == 0


def test_request_recycle_prepares_unique_ids_then_asks_for_confirmation(env: _Env) -> None:
    track = env.add_track("sub/a.wav")
    model = env.make_model()
    dialogs: list[int] = []
    model.dialogRequested.connect(lambda: dialogs.append(1))

    model.request_recycle([track, track])

    assert model.state == "preparing"
    assert model.message == "Preparing 1 file(s) for confirmation…"
    assert model.selectedCount == 1
    assert model.canCancel
    assert not model.canConfirm

    env.wait(lambda: model.state != "preparing")
    assert model.state == "confirm"
    assert model.message == (
        "Review the selected files, then confirm moving them to the Windows Recycle Bin."
    )
    assert model.selectedCount == 1
    assert model.canConfirm
    assert not model.canCancel
    assert dialogs == [1]
    assert _results(model) == []
    assert env.service.calls == []
    assert env.journal_rows() == []
    assert (env.music / "sub" / "a.wav").is_file()


def test_a_second_request_is_ignored_while_preparing(env: _Env) -> None:
    first = env.add_track("a.wav")
    second = env.add_track("b.wav")
    model = env.make_model()
    model.request_recycle([first])
    model.request_recycle([first, second])
    assert model.selectedCount == 1
    env.wait(lambda: model.state != "preparing")
    assert model.state == "confirm"
    assert model.selectedCount == 1


def test_unknown_and_unreadable_files_are_reported_as_conflicts(env: _Env) -> None:
    track = env.add_track("a.wav")
    missing = env.add_track("b.wav")
    with env.database.transaction() as connection:
        connection.execute(
            "UPDATE track_locations SET status='unreadable' WHERE track_id=?", (missing,)
        )
    model = env.make_model()

    env.prepare(model, [track, missing, "no-such-track"])

    assert model.state == "confirm"
    assert model.selectedCount == 1
    results = _results(model)
    assert [item["status"] for item in results] == ["conflict", "conflict"]
    assert results[0]["trackId"] == missing
    assert results[0]["source"] == "b.wav"
    assert results[0]["message"] == "The file is no longer available in the library."
    assert results[1]["trackId"] == "no-such-track"
    assert results[1]["source"] == "no-such-track"


def test_when_nothing_is_recyclable_the_result_opens_without_confirmation(env: _Env) -> None:
    model = env.make_model()
    dialogs: list[int] = []
    model.dialogRequested.connect(lambda: dialogs.append(1))

    env.prepare(model, ["ghost"])

    assert model.state == "result"
    assert model.message == "No selected audio files are available to recycle."
    assert not model.canConfirm
    assert dialogs == [1]
    assert _statuses(model) == ["conflict"]
    model.confirm()
    assert model.state == "result"


def test_a_preparation_error_is_reported_without_opening_the_dialog(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    dialogs: list[int] = []
    model.dialogRequested.connect(lambda: dialogs.append(1))

    def broken(_track_id: str):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(env.library, "source_record", broken)
    env.prepare(model, [track])
    env.settle()

    assert model.state == "result"
    assert model.message == "Could not prepare the recycle operation: database unavailable"
    assert not model.canCancel
    assert dialogs == []  # characterization: the QML dialog is never asked to open
    status = env.job_status("Prepare recycle operation")
    assert status.state is JobState.FAILED


def test_cancelling_during_preparation_reports_a_cancellation(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = env.add_track("a.wav")
    second = env.add_track("b.wav")
    model = env.make_model()
    entered = threading.Event()
    gate = threading.Event()
    real = env.library.source_record

    def blocking(track_id: str):
        entered.set()
        assert gate.wait(_DEADLINE_SECONDS)
        return real(track_id)

    monkeypatch.setattr(env.library, "source_record", blocking)
    model.request_recycle([first, second])
    assert entered.wait(_DEADLINE_SECONDS)
    model.cancel()
    assert model.message == "Stopping after the current Shell operation…"
    gate.set()
    env.wait(lambda: model.state != "preparing")
    env.settle()

    assert model.state == "result"
    assert model.message == "Recycle preparation was cancelled."
    assert not model.canCancel
    assert env.job_status("Prepare recycle operation").state is JobState.CANCELLED


def test_a_request_while_jobs_are_shutting_down_ends_in_a_result_message(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    dialogs: list[int] = []
    model.dialogRequested.connect(lambda: dialogs.append(1))
    env.jobs.begin_shutdown()

    model.request_recycle([track])

    assert model.state == "result"
    assert model.message == "The application is shutting down; no new jobs are accepted."
    assert not model.canCancel
    assert dialogs == []


def test_a_new_request_replaces_a_finished_result(env: _Env) -> None:
    first = env.add_track("a.wav")
    second = env.add_track("b.wav")
    model = env.make_model()
    env.run_to_result(model, [first])
    assert _statuses(model) == ["recycled"]

    env.prepare(model, [second])

    assert model.state == "confirm"
    assert _results(model) == []
    assert model.selectedCount == 1


# --- happy path ----------------------------------------------------------------------------


def test_confirmed_files_are_recycled_journaled_and_hidden_from_the_library(env: _Env) -> None:
    nested = env.add_track("sub/a.wav")
    top = env.add_track("b.wav")
    model = env.make_model()
    recycled: list[Any] = []
    model.tracksRecycled.connect(recycled.append)

    model.request_recycle([nested, top])
    env.wait(lambda: model.state != "preparing")
    model.confirm()
    assert model.state == "running"
    assert model.message == "Recycling 2 audio file(s)…"
    env.wait(lambda: model.state == "result")
    env.settle()

    assert model.message == "Recycled 2 file(s) to the Windows Recycle Bin."
    assert model.selectedCount == 2
    assert not model.canCancel
    assert not model.hasBusyFiles
    results = _results(model)
    assert _statuses(model) == ["recycled", "recycled"]
    first = results[0]
    assert first["trackId"] == nested
    assert first["source"] == str((env.music / "sub" / "a.wav").resolve())
    assert first["rootId"] == env.root_id
    assert first["parentRelative"] == "sub"
    assert first["message"] == "Moved to the Windows Recycle Bin."
    assert first["recycleItemIdentity"].endswith("0001.wav")
    assert first["operationId"]
    assert results[1]["parentRelative"] == ""
    assert len(recycled) == 1
    assert [item["trackId"] for item in recycled[0]] == [nested, top]

    assert not (env.music / "sub" / "a.wav").exists()
    assert not (env.music / "b.wav").exists()
    assert len(env.service.calls) == 2
    assert env.present(nested) == [0]
    assert env.present(top) == [0]
    rows = env.journal_rows()
    assert [row[1] for row in rows] == ["recycled", "recycled"]
    assert [row[0] for row in rows] == [nested, top]
    assert rows[0][3] == first["recycleItemIdentity"]
    assert env.journal.interrupted() == []
    status = env.job_status("Move audio to Recycle Bin")
    assert status.state is JobState.SUCCEEDED
    assert status.progress == 1.0


def test_results_are_returned_as_copies(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    env.run_to_result(model, [track])
    snapshot = _results(model)
    snapshot[0]["status"] = "tampered"
    snapshot.clear()
    assert _statuses(model) == ["recycled"]


def test_the_confirmation_phase_keeps_conflicts_in_the_final_results(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    recycled: list[Any] = []
    model.tracksRecycled.connect(recycled.append)

    env.run_to_result(model, [track, "ghost"])

    assert _statuses(model) == ["conflict", "recycled"]
    assert model.message == "Recycled 1 file(s). 1 need attention."
    assert [item["trackId"] for item in recycled[0]] == [track]
    assert env.job_status("Move audio to Recycle Bin").state is JobState.FAILED


def test_confirm_and_request_are_ignored_while_the_shell_is_working(env: _Env) -> None:
    track = env.add_track("a.wav")
    other = env.add_track("b.wav")
    model = env.make_model()
    env.service.gate = threading.Event()
    env.prepare(model, [track])
    model.confirm()
    assert env.service.entered.wait(_DEADLINE_SECONDS)

    assert model.state == "running"
    assert model.canCancel
    assert not model.canConfirm
    model.confirm()
    model.request_recycle([other])
    model.retry_busy()
    assert model.state == "running"
    assert model.selectedCount == 1

    env.service.gate.set()
    env.wait(lambda: model.state == "result")
    env.settle()
    assert len(env.service.calls) == 1
    assert (env.music / "b.wav").is_file()


def test_cancel_stops_after_the_current_file_and_leaves_the_rest_untouched(env: _Env) -> None:
    first = env.add_track("a.wav")
    second = env.add_track("b.wav")
    model = env.make_model()
    recycled: list[Any] = []
    model.tracksRecycled.connect(recycled.append)
    env.service.gate = threading.Event()
    env.prepare(model, [first, second])
    model.confirm()
    assert env.service.entered.wait(_DEADLINE_SECONDS)

    model.cancel()
    assert model.message == "Stopping after the current Shell operation…"
    assert model.state == "running"
    env.service.gate.set()
    env.wait(lambda: model.state == "result")
    env.settle()

    assert _statuses(model) == ["recycled"]
    assert model.message == "Recycled 1 file(s) to the Windows Recycle Bin."
    assert [item["trackId"] for item in recycled[0]] == [first]
    assert (env.music / "b.wav").is_file()
    assert env.present(second) == [1]
    assert len(env.journal_rows()) == 1
    assert env.job_status("Move audio to Recycle Bin").state is JobState.CANCELLED


def test_a_shutdown_between_confirmation_and_start_ends_in_a_result_message(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    env.prepare(model, [track])
    env.jobs.begin_shutdown()

    model.confirm()

    assert model.state == "result"
    assert model.message == "The application is shutting down; no new jobs are accepted."
    assert not model.canCancel
    assert env.service.calls == []
    assert (env.music / "a.wav").is_file()


# --- refusals and failures -----------------------------------------------------------------


def test_a_file_modified_after_preparation_is_refused_and_not_recycled(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    recycled: list[Any] = []
    model.tracksRecycled.connect(recycled.append)
    env.prepare(model, [track])
    with (env.music / "a.wav").open("ab") as handle:
        handle.write(b"extra")

    model.confirm()
    env.wait(lambda: model.state == "result")
    env.settle()

    result = _results(model)[0]
    assert result["status"] == "conflict"
    assert result["message"] == "The file changed after confirmation."
    assert model.message == "Recycled 0 file(s). 1 need attention."
    assert not model.hasBusyFiles
    assert recycled == []
    assert env.service.calls == []
    assert (env.music / "a.wav").is_file()
    assert env.present(track) == [1]
    rows = env.journal_rows()
    assert [(row[1], row[2]) for row in rows] == [("conflict", "The file revision changed.")]
    status = env.job_status("Move audio to Recycle Bin")
    assert status.state is JobState.FAILED
    assert status.error is not None
    assert status.error.code == _TrashBatchError.code == "trash_partial_failure"
    assert status.failure_total == 1
    assert status.failures[0].name == "a.wav"


def test_a_library_revision_that_no_longer_matches_is_refused(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    env.prepare(model, [track])
    with env.database.transaction() as connection:
        connection.execute(
            "UPDATE track_locations SET size_bytes=size_bytes+1 WHERE track_id=?", (track,)
        )

    model.confirm()
    env.wait(lambda: model.state == "result")
    env.settle()

    assert _results(model)[0]["message"] == "The file changed after confirmation."
    assert env.service.calls == []
    assert (env.music / "a.wav").is_file()


def test_a_file_changing_while_the_lock_is_taken_is_refused_before_the_shell(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    env.prepare(model, [track])

    def touch() -> None:
        with (env.music / "a.wav").open("ab") as handle:
            handle.write(b"late")

    env.access.on_acquire = touch
    model.confirm()
    env.wait(lambda: model.state == "result")
    env.settle()

    result = _results(model)[0]
    assert result["status"] == "conflict"
    assert result["message"] == "The file changed before recycling."
    assert env.service.calls == []
    assert (env.music / "a.wav").is_file()


def test_a_file_deleted_after_preparation_fails_without_calling_the_shell(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    env.prepare(model, [track])
    (env.music / "a.wav").unlink()

    model.confirm()
    env.wait(lambda: model.state == "result")
    env.settle()

    result = _results(model)[0]
    assert result["status"] == "failed"
    assert result["message"].startswith("FileNotFoundError: ")
    assert model.message == "Recycled 0 file(s). 1 need attention."
    assert env.service.calls == []
    assert env.present(track) == [1]
    assert env.journal_rows()[0][1] == "failed"


def test_a_recycle_bin_failure_never_falls_back_to_deleting_the_file(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    recycled: list[Any] = []
    model.tracksRecycled.connect(recycled.append)
    env.service.errors["a.wav"] = TrashServiceError("The Recycle Bin is unavailable.")

    env.run_to_result(model, [track])

    result = _results(model)[0]
    assert result["status"] == "failed"
    assert result["message"] == "TrashServiceError: The Recycle Bin is unavailable."
    assert "recycleItemIdentity" not in result
    assert model.message == "Recycled 0 file(s). 1 need attention."
    assert (env.music / "a.wav").is_file()  # still on disk: no permanent deletion
    assert len(env.service.calls) == 1  # no retry and no alternative path
    assert recycled == []
    assert env.present(track) == [1]
    rows = env.journal_rows()
    assert [(row[1], row[2], row[3]) for row in rows] == [
        ("failed", "TrashServiceError: The Recycle Bin is unavailable.", "")
    ]
    assert env.journal.interrupted() == []


def test_a_partial_batch_recycles_the_good_files_and_reports_the_failure(env: _Env) -> None:
    first = env.add_track("a.wav")
    second = env.add_track("b.wav")
    third = env.add_track("c.wav")
    model = env.make_model()
    recycled: list[Any] = []
    model.tracksRecycled.connect(recycled.append)
    env.service.errors["b.wav"] = TrashServiceError("Access is denied.")

    env.run_to_result(model, [first, second, third])

    assert _statuses(model) == ["recycled", "failed", "recycled"]
    assert model.message == "Recycled 2 file(s). 1 need attention."
    assert [item["trackId"] for item in recycled[0]] == [first, third]
    assert (env.music / "b.wav").is_file()
    assert not (env.music / "a.wav").exists()
    assert not (env.music / "c.wav").exists()
    assert [row[1] for row in env.journal_rows()] == ["recycled", "failed", "recycled"]
    status = env.job_status("Move audio to Recycle Bin")
    assert status.state is JobState.FAILED
    assert status.error is not None
    assert status.error.code == "trash_partial_failure"
    assert status.failure_total == 1
    assert status.failures[0].name == "b.wav"
    assert status.completed == 3


@pytest.mark.parametrize(
    "error",
    [sqlite3.OperationalError("disk full"), OSError("disk full")],
    ids=["sqlite_error", "any_other_exception"],
)
def test_a_journal_failure_after_the_recycle_is_flagged_but_the_recycle_stands(
    env: _Env, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    real = env.journal.finish

    def failing(operation_id, status, message="", recycle_item_identity=""):
        if status == "recycled":
            raise error
        real(operation_id, status, message, recycle_item_identity=recycle_item_identity)

    monkeypatch.setattr(env.journal, "finish", failing)
    env.run_to_result(model, [track])

    result = _results(model)[0]
    assert result["status"] == "recycled"
    assert result["message"] == (
        "Moved to the Windows Recycle Bin. "
        "The recycle was confirmed, but its journal needs inspection."
    )
    assert env.present(track) == [0]
    assert [row[1] for row in env.journal_rows()] == ["prepared"]
    assert len(env.journal.interrupted()) == 1


@pytest.mark.parametrize(
    "error",
    [sqlite3.OperationalError("locked"), RuntimeError("locked")],
    ids=["sqlite_error", "any_other_exception"],
)
def test_a_library_update_error_after_the_recycle_is_flagged(
    env: _Env, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()

    def failing(_track_id, _revision):
        raise error

    monkeypatch.setattr(env.library, "mark_recycled", failing)
    env.run_to_result(model, [track])

    result = _results(model)[0]
    assert result["status"] == "recycled"
    assert result["message"] == (
        "Moved to the Windows Recycle Bin. "
        "The library could not be updated; it will be reconciled on the next scan."
    )
    assert env.present(track) == [1]
    assert [row[1] for row in env.journal_rows()] == ["recycled"]


def test_a_library_row_that_changed_during_the_recycle_is_left_for_the_next_scan(
    env: _Env,
) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()

    def bump(_path: Path) -> None:
        with env.database.transaction() as connection:
            connection.execute(
                "UPDATE track_locations SET size_bytes=size_bytes+1 WHERE track_id=?", (track,)
            )

    env.service.before_return = bump
    env.run_to_result(model, [track])

    result = _results(model)[0]
    assert result["status"] == "recycled"
    assert result["message"] == (
        "Moved to the Windows Recycle Bin. The library record will be reconciled on the next scan."
    )
    assert env.present(track) == [1]


# --- busy files, retry and playback --------------------------------------------------------


def test_a_file_in_use_is_reported_busy_and_can_be_retried(env: _Env) -> None:
    free = env.add_track("a.wav")
    held = env.add_track("b.wav")
    model = env.make_model()
    recycled: list[Any] = []
    model.tracksRecycled.connect(recycled.append)
    env.prepare(model, [free, held])

    with env.access.acquire(TrackId.parse(held), "playback"):
        model.confirm()
        env.wait(lambda: model.state == "result")
        env.settle()

        assert _statuses(model) == ["recycled", "busy"]
        busy = _results(model)[1]
        assert busy["message"] == "The file is in use. Stop playback, then retry this file."
        assert model.hasBusyFiles
        assert model.message == "Stop playback and retry the files that are still in use."
        assert model.selectedCount == 2
        assert (env.music / "b.wav").is_file()
        assert len(env.service.calls) == 1
        assert [row[1] for row in env.journal_rows()] == ["recycled", "failed"]
        status = env.job_status("Move audio to Recycle Bin")
        assert status.state is JobState.FAILED

        # Still held: a retry stays busy and recycles nothing new.
        model.retry_busy()
        assert model.state == "running"
        env.wait(lambda: model.state == "result")
        env.settle()
        assert _statuses(model) == ["recycled", "busy"]
        assert len(recycled) == 1

    model.retry_busy()
    assert model.state == "running"
    assert model.message == "Recycling 1 audio file(s)…"
    env.wait(lambda: model.state == "result")
    env.settle()

    assert not model.hasBusyFiles
    assert _statuses(model) == ["recycled", "recycled"]
    assert model.message == "Recycled 1 file(s) to the Windows Recycle Bin."
    assert model.selectedCount == 1
    assert [item["trackId"] for item in recycled[1]] == [held]
    assert len(recycled) == 2
    assert not (env.music / "b.wav").exists()
    assert env.present(held) == [0]


def test_retry_keeps_earlier_results_other_than_busy_ones(env: _Env) -> None:
    free = env.add_track("a.wav")
    held = env.add_track("b.wav")
    model = env.make_model()
    env.prepare(model, [free, held])
    with env.access.acquire(TrackId.parse(held), "playback"):
        model.confirm()
        env.wait(lambda: model.state == "result")
        env.settle()
        assert _statuses(model) == ["recycled", "busy"]
    model.retry_busy()
    assert [item["status"] for item in _results(model)] == ["recycled"]
    env.wait(lambda: model.state == "result")
    env.settle()
    assert _statuses(model) == ["recycled", "recycled"]
    assert [item["trackId"] for item in _results(model)] == [free, held]


def test_retry_without_busy_files_does_nothing(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    env.run_to_result(model, [track])
    model.retry_busy()
    assert model.state == "result"
    assert len(env.service.calls) == 1


def test_stop_playback_releases_the_playing_busy_file_then_retries(env: _Env) -> None:
    held = env.add_track("a.wav")
    player = _FakePlayer()
    model = env.make_model(player)
    env.prepare(model, [held])
    lease = env.access.acquire(TrackId.parse(held), "playback")
    lease.__enter__()
    try:
        model.confirm()
        env.wait(lambda: model.state == "result")
        env.settle()
        assert model.hasBusyFiles
        assert not model.canStopPlaybackAndContinue
        player.playing_id = held
        assert model.canStopPlaybackAndContinue

        model.stop_playback_and_continue()
        assert player.stop_calls == [held]
        assert model.message == "Stopping playback before retrying the recycle operation…"
        assert model.state == "result"

        player.trackAccessReleased.emit("another-track")
        assert model.state == "result"
    finally:
        lease.__exit__(None, None, None)

    player.trackAccessReleased.emit(held)
    assert model.state == "running"
    env.wait(lambda: model.state == "result")
    env.settle()
    assert _statuses(model) == ["recycled"]
    assert not (env.music / "a.wav").exists()

    # A late duplicate notification does nothing.
    player.trackAccessReleased.emit(held)
    assert model.state == "result"


def test_stop_playback_retries_at_once_when_nothing_needed_releasing(env: _Env) -> None:
    held = env.add_track("a.wav")
    player = _FakePlayer()
    player.stop_result = False
    model = env.make_model(player)
    env.prepare(model, [held])
    lease = env.access.acquire(TrackId.parse(held), "playback")
    lease.__enter__()
    try:
        model.confirm()
        env.wait(lambda: model.state == "result")
        env.settle()
        player.playing_id = held
    finally:
        lease.__exit__(None, None, None)

    model.stop_playback_and_continue()

    assert model.state == "running"
    env.wait(lambda: model.state == "result")
    env.settle()
    assert _statuses(model) == ["recycled"]


def test_stop_playback_is_ignored_when_the_playing_track_is_not_busy(env: _Env) -> None:
    held = env.add_track("a.wav")
    player = _FakePlayer()
    model = env.make_model(player)
    env.prepare(model, [held])
    lease = env.access.acquire(TrackId.parse(held), "playback")
    lease.__enter__()
    try:
        model.confirm()
        env.wait(lambda: model.state == "result")
        env.settle()
    finally:
        lease.__exit__(None, None, None)

    player.playing_id = ""
    model.stop_playback_and_continue()
    player.playing_id = "someone-else"
    model.stop_playback_and_continue()

    assert player.stop_calls == []
    assert not model.canStopPlaybackAndContinue
    assert model.state == "result"


def test_stop_playback_without_a_player_is_a_no_op(env: _Env) -> None:
    model = env.make_model()
    model.stop_playback_and_continue()
    assert model.state == "idle"
    assert not model.canStopPlaybackAndContinue


def test_player_playback_changes_notify_the_model(env: _Env) -> None:
    player = _FakePlayer()
    model = env.make_model(player)
    changes: list[int] = []
    model.changed.connect(lambda: changes.append(1))
    player.playbackChanged.emit()
    assert changes == [1]


# --- interrupted operations ----------------------------------------------------------------


def test_an_interrupted_operation_from_a_previous_run_is_surfaced_at_start(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = env.library.source_record(track)
    assert source is not None
    env.journal.prepare("op-1", track, str(source.path), source.revision)
    env.journal.prepare("op-2", "other", "C:\\music\\gone.wav", source.revision)
    env.journal.prepare("op-done", "third", "C:\\music\\done.wav", source.revision)
    env.journal.finish("op-done", "failed", "x")
    dialogs: list[int] = []

    model = TrashModel(
        env.library,
        env.jobs,
        cast(Any, env.service),
        env.access,
        env.journal,
    )
    model.dialogRequested.connect(lambda: dialogs.append(1))
    env.settle()

    assert model.state == "result"
    assert model.message == "2 interrupted recycle operation(s) need inspection."
    assert dialogs == [1]
    results = _results(model)
    assert [item["operationId"] for item in results] == ["op-1", "op-2"]
    assert {item["status"] for item in results} == {"interrupted"}
    assert results[0]["trackId"] == track
    assert results[0]["source"] == str(source.path)
    assert results[0]["recycleItemIdentity"] == ""
    assert "did not infer success" in results[0]["message"]
    assert env.service.calls == []
    assert source.path.is_file()


def test_no_interrupted_operation_leaves_the_model_idle(env: _Env) -> None:
    model = env.make_model()
    assert model.state == "idle"
    assert _results(model) == []


def test_interrupted_history_is_ignored_when_the_model_is_already_busy(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    env.prepare(model, [track])
    model.interruptedReady.emit([{"track_id": "x", "operation_id": "o", "source_path": "p"}])
    assert model.state == "confirm"
    assert _results(model) == []

    idle = env.make_model()
    idle.interruptedReady.emit([])
    idle.interruptedReady.emit("not a list")
    assert idle.state == "idle"


# --- stale or malformed internal signals ---------------------------------------------------


def test_stale_or_malformed_worker_signals_are_ignored(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    env.prepare(model, [track])
    assert model.state == "confirm"

    model.preparationReady.emit(999, [], [])
    model.preparationFailed.emit(999, "stale")
    model.resultsReady.emit(999, [{"status": "recycled", "trackId": "x"}])
    model.resultsReady.emit(1, "not a list")
    model.preparationReady.emit(1, "not a list", [])

    assert model.state == "confirm"
    assert cast(str, model.message).startswith("Review the selected files")
    assert _results(model) == []
    assert model.selectedCount == 1


def test_malformed_candidate_and_failure_payloads_are_filtered(env: _Env) -> None:
    model = env.make_model()
    model.request_recycle(["ghost"])
    env.wait(lambda: model.state != "preparing")
    assert model.state == "result"

    generation = model._generation
    model.preparationReady.emit(generation, ["junk", 3], "junk")

    assert model.state == "result"
    assert model.message == "No selected audio files are available to recycle."
    assert _results(model) == []


def test_a_cancellation_right_before_the_shell_leaves_the_journal_entry_prepared(
    env: _Env,
) -> None:
    track = env.add_track("a.wav")
    model = env.make_model()
    env.prepare(model, [track])

    def cancel_now() -> None:
        for status in env.jobs.statuses():
            if status.label == "Move audio to Recycle Bin":
                env.jobs.cancel(status.job_id)

    env.access.on_acquire = cancel_now
    model.confirm()
    env.wait(lambda: model.state == "result")
    env.settle()

    # Characterization: the cancelled operation is neither finished nor reported; it stays
    # "prepared" in the journal and will be listed as interrupted at the next start.
    assert _results(model) == []
    assert model.message == "Recycled 0 file(s) to the Windows Recycle Bin."
    assert env.service.calls == []
    assert (env.music / "a.wav").is_file()
    assert [row[1] for row in env.journal_rows()] == ["prepared"]
    assert len(env.journal.interrupted()) == 1
    assert env.job_status("Move audio to Recycle Bin").state is JobState.CANCELLED
