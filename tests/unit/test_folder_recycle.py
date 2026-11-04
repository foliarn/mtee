"""Moving a whole folder to the Recycle Bin: one Shell call, every track journaled (plan 132.2).

The Windows Shell is never reached: a fake service "recycles" a folder by deleting it inside
``tmp_path``. The library, the journal and the file access coordinator are real.
"""

from __future__ import annotations

import shutil
import time
import wave
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.models.trash_model import TrashModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.trash_repository import TrashRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.jobs import JobService
from mtee.services.trash_service import TrashServiceError

_DEADLINE_SECONDS = 15.0


class _FakeFolderService:
    """Stands in for the Shell: removes the folder like a recycle would, and records the call."""

    def __init__(self) -> None:
        self.calls: list[Path] = []
        self.error: Exception | None = None

    def recycle(self, path: Path | str) -> str:  # pragma: no cover - files are not used here
        raise AssertionError("A folder recycle must not send single files.")

    def recycle_folder(self, path: Path | str) -> str:
        source = Path(path)
        self.calls.append(source)
        if self.error is not None:
            raise self.error
        shutil.rmtree(source)
        return f"C:\\$Recycle.Bin\\S-1-5-21\\$F{len(self.calls):04d}"


class _Env:
    def __init__(self, qapp: Any, base: Path) -> None:
        self.qapp = qapp
        self.music = base / "music"
        (self.music / "sub").mkdir(parents=True)
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.root_id = str(self.library.add_root(self.music)["id"])
        self.access = FileAccessCoordinator()
        self.journal = TrashRepository(self.database)
        self.jobs = JobService(max_thread_count=2)
        self.service = _FakeFolderService()
        self.recycled: list[object] = []
        self.model = TrashModel(
            self.library, self.jobs, cast(Any, self.service), self.access, self.journal
        )
        self.model.folderRecycled.connect(self.recycled.append)
        self.model.dialogRequested.connect(lambda: None)
        self.write_tracks()

    def write_tracks(self) -> None:
        for name in ("a.wav", "b.wav"):
            path = self.music / "sub" / name
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(8000)
                handle.writeframes(b"\x00\x00" * 800)
        (self.music / "sub" / "cover.txt").write_text("kept with the folder", encoding="utf-8")
        entries = []
        for name in ("a.wav", "b.wav"):
            path = self.music / "sub" / name
            entries.append(
                (
                    f"sub/{name}",
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(
                        title=(path.stem,),
                        artist=("Test artist",),
                        technical=TechnicalInfo(duration_us=100_000),
                    ),
                )
            )
        generation = self.library.begin_scan(self.root_id)
        self.library.upsert_locations(self.root_id, entries, generation)
        self.library.finish_scan(self.root_id, generation, complete=True)

    def track_ids(self) -> list[str]:
        rows = self.database.connection().execute(
            "SELECT track_id FROM root_tracks WHERE root_id=? ORDER BY relative_path",
            (self.root_id,),
        )
        return [str(row[0]) for row in rows]

    def wait(self, condition: Callable[[], bool]) -> None:
        deadline = time.monotonic() + _DEADLINE_SECONDS
        while not condition():
            assert time.monotonic() < deadline, "the model did not reach the expected state"
            self.qapp.processEvents()
            time.sleep(0.005)

    def settle(self) -> None:
        assert self.jobs.wait_for_done(int(_DEADLINE_SECONDS * 1000))
        self.qapp.processEvents()

    def prepare(self) -> None:
        self.model.request_recycle_folder(self.root_id, "sub")
        self.wait(lambda: self.model.state != "preparing")

    def journal_rows(self) -> list[tuple[str, str, str]]:
        rows = self.database.connection().execute(
            "SELECT track_id,status,recycle_item_identity FROM trash_operations ORDER BY rowid"
        )
        return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]


@pytest.fixture
def env(qapp, tmp_path: Path) -> Iterator[_Env]:
    created = _Env(qapp, tmp_path)
    yield created
    created.jobs.shutdown()
    created.settle()


def test_a_folder_goes_to_the_recycle_bin_as_one_operation(env: _Env) -> None:
    env.prepare()
    assert env.model.state == "confirm"
    assert env.model.canConfirm
    assert "2 track(s)" in str(env.model.folderSummary)
    tracks = env.track_ids()
    assert len(tracks) == 2

    env.model.confirm()
    env.wait(lambda: env.model.state == "result")
    env.settle()

    assert env.service.calls == [env.music / "sub"]
    assert not (env.music / "sub").exists()
    rows = env.journal_rows()
    assert sorted(row[0] for row in rows) == sorted(tracks)
    assert all(row[1] == "recycled" for row in rows)
    assert all(row[2].startswith("C:\\$Recycle.Bin") for row in rows)
    assert env.model.message == "Moved folder “sub” to the Windows Recycle Bin."
    for track_id in tracks:
        present = (
            env.database.connection()
            .execute("SELECT present FROM root_tracks WHERE track_id=?", (track_id,))
            .fetchone()
        )
        assert present is None or int(present[0]) == 0
    assert "sub" not in env.library.folders(env.root_id)
    assert env.recycled == [
        {"rootId": env.root_id, "relative": "sub", "parentRelative": "", "name": "sub"}
    ]


def test_a_track_in_use_refuses_the_whole_folder(env: _Env) -> None:
    env.prepare()
    track = env.track_ids()[0]
    with env.access.acquire(TrackId.parse(track), "test playback", timeout_seconds=0):
        env.model.confirm()
        env.wait(lambda: env.model.state == "result")
        env.settle()

    assert env.service.calls == []
    assert (env.music / "sub" / "a.wav").is_file()
    assert any(row[1] == "failed" for row in env.journal_rows())
    assert not env.recycled


def test_a_shell_failure_recycles_nothing_and_keeps_the_folder(env: _Env) -> None:
    env.service.error = TrashServiceError("the Recycle Bin did not confirm")
    env.prepare()
    env.model.confirm()
    env.wait(lambda: env.model.state == "result")
    env.settle()

    assert (env.music / "sub" / "a.wav").is_file()
    assert (env.music / "sub" / "cover.txt").is_file()
    assert {row[1] for row in env.journal_rows()} == {"failed"}
    assert len(env.track_ids()) == 2
    assert not env.recycled


def test_a_source_itself_is_not_recycled_as_a_folder(env: _Env) -> None:
    env.model.request_recycle_folder(env.root_id, "")
    env.wait(lambda: env.model.state == "result")
    assert "removed from the library" in str(env.model.message)
    assert env.service.calls == []
    assert (env.music / "sub" / "a.wav").is_file()
