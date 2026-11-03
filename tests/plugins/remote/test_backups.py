"""Database backups (plan 126.8): the real server, the real database and the plugin's own backups.

Each backup is taken by the real ``database_snapshot`` on a worker thread, as a job would: the
test thread counts as the graphical thread of the harness, and the snapshot refuses that thread. A
restore only records its request, through a wrapper of the real capability, because the restore
path of MTEE (Settings > Data & privacy) is not part of the plugin's tests.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from mtee.plugins.remote.backups import (  # pyright: ignore[reportMissingImports]
    LAST_AUTO_KEY,
    MANUAL,
    PENDING_KEY,
    BackupError,
    backup_rows,
    is_due,
    keep_counts,
    last_backup_text,
    make_backup,
    restore,
    run_automatic,
    schedule,
    set_keep,
    set_schedule,
    size_text,
)
from mtee.plugins.remote.client import (  # pyright: ignore[reportMissingImports]
    DownloadError,
    RemoteClient,
)
from mtee.plugins.remote.store import RemoteStore  # pyright: ignore[reportMissingImports]
from tests.plugins.remote.conftest import RemoteServer
from tests.plugins.remote.helpers import (
    FakeLibrary,
    fake_job,
    make_context,
    sha256_of,
    signed_in,
)

from mtee.domain.jobs import JobCancelledError
from mtee.plugins.api import JobContext, PluginContext

CHUNK = 2048
MakeUser = Callable[[], tuple[str, str]]


def on_job_thread[T](call: Callable[[], T]) -> T:
    """Run ``call`` on a worker thread, as a plugin job would, and return or raise its result."""
    outcome: list[Any] = []

    def work() -> None:
        try:
            outcome.append((True, call()))
        except BaseException as error:  # handed back to the test thread
            outcome.append((False, error))

    thread = threading.Thread(target=work)
    thread.start()
    thread.join(120)
    if not outcome:
        pytest.fail("The job did not finish in time.")
    succeeded, value = outcome[0]
    if succeeded:
        return cast(T, value)
    raise cast(BaseException, value)


class StopAfterChunk:
    """A job the test cancels once a chunk went out, as a user cancelling it in Tasks would."""

    def __init__(self) -> None:
        self.cancelled = False

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelledError("cancelled by the test")

    def report_progress(self, progress: float) -> None:
        return None


class RecordingSnapshots:
    """The real ``database_snapshot``, with the restore requests recorded instead of offered."""

    def __init__(self, real: Any) -> None:
        self._real = real
        self.restores: list[Path] = []

    def snapshot(self, target_path: Path) -> Path:
        return cast(Path, self._real.snapshot(target_path))

    def request_restore(self, path: Path) -> None:
        self.restores.append(Path(path))


@dataclasses.dataclass
class Device:
    """A signed-in device of a test: its plugin context, and its client."""

    server: RemoteServer
    context: PluginContext
    client: RemoteClient

    def backup(
        self, kind: str = MANUAL, label: str | None = None, **options: Any
    ) -> dict[str, Any]:
        """Make a backup on a worker thread; return the server's record of it."""
        context, client = self.context, self.client
        return on_job_thread(
            lambda: make_backup(context, client, fake_job(), kind=kind, label=label, **options)
        )

    def pending(self) -> dict[str, Any] | None:
        value = self.context.settings.get_json(PENDING_KEY, None)
        return value if isinstance(value, dict) else None

    def local_copies(self) -> list[Path]:
        folder = self.context.base_dir / "backups"
        return sorted(folder.glob("*.db")) if folder.is_dir() else []

    def log_lines(self) -> list[str]:
        rows = RemoteStore(self.context).connection().execute("SELECT text FROM remote_log")
        return [str(row["text"]) for row in rows.fetchall()]


@pytest.fixture
def device(tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser) -> Iterator[Device]:
    username, password = make_user()
    with signed_in(remote_server, username, password) as client:
        context = make_context(tmp_path, FakeLibrary([], []))
        yield Device(remote_server, context, client)


def test_a_backup_is_uploaded_with_its_hash_and_kind_and_its_copy_is_removed(
    device: Device,
) -> None:
    backup = device.backup(MANUAL, label="Before the move")

    (listed,) = device.client.backups()
    assert listed["backup_id"] == backup["backup_id"]
    assert listed["kind"] == "manual"
    assert listed["label"] == "Before the move"
    assert listed["sha256"] == backup["sha256"]
    assert int(listed["size_bytes"]) > 2 * CHUNK

    downloaded = device.client.download_backup(
        str(listed["backup_id"]),
        device.context.base_dir / "check" / "copy.db",
        expected_sha256=str(listed["sha256"]),
    )
    assert sha256_of(downloaded) == listed["sha256"]
    with sqlite3.connect(downloaded) as connection:
        tables = connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
    assert tables[0] > 0, "the uploaded copy is a database with its tables"

    assert device.local_copies() == [], "the local copy is removed after the commit"
    assert device.pending() is None
    assert any("Saved a manual database backup" in line for line in device.log_lines())


def test_a_cut_upload_resumes_from_the_bytes_the_server_holds(
    device: Device, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[dict[str, Any]] = []
    open_backup_upload = device.client.open_backup_upload

    def count_open(**fields: Any) -> dict[str, Any]:
        opened.append(fields)
        return open_backup_upload(**fields)

    job = StopAfterChunk()
    send_chunk = device.client.upload_chunk

    def cancel_after_one_chunk(upload_id: str, start: int, data: bytes, total: int) -> int:
        received = send_chunk(upload_id, start, data, total)
        job.cancelled = True
        return received

    monkeypatch.setattr(device.client, "open_backup_upload", count_open)
    monkeypatch.setattr(device.client, "upload_chunk", cancel_after_one_chunk)
    context, client = device.context, device.client
    with pytest.raises(JobCancelledError):
        on_job_thread(
            lambda: make_backup(
                context,
                client,
                cast(JobContext, job),
                kind=MANUAL,
                chunk_bytes=CHUNK,
            )
        )

    pending = device.pending()
    assert pending is not None
    assert int(pending["size"]) > 2 * CHUNK
    upload_id = str(pending["upload_id"])
    assert device.client.upload_status(upload_id)["received_bytes"] == CHUNK
    assert device.client.backups() == []
    assert len(device.local_copies()) == 1, "the copy stays until the server has it"

    monkeypatch.setattr(device.client, "upload_chunk", send_chunk)
    backup = on_job_thread(
        lambda: make_backup(context, client, fake_job(), kind=MANUAL, chunk_bytes=CHUNK)
    )

    assert len(opened) == 1, "the second try resumes the upload, it opens no other"
    (listed,) = device.client.backups()
    assert listed["backup_id"] == backup["backup_id"]
    assert device.local_copies() == []
    assert device.pending() is None


def test_an_automatic_backup_is_due_only_when_the_schedule_says_so(device: Device) -> None:
    context = device.context
    now = datetime.now(UTC)
    assert schedule(context) == "daily", "daily is the default schedule"
    assert is_due(context, now) is True, "no backup yet: one is due"

    set_schedule(context, "daily")
    context.settings.set(LAST_AUTO_KEY, (now - timedelta(hours=1)).isoformat(timespec="seconds"))
    assert is_due(context, now) is False, "a backup an hour ago is not due for daily"

    context.settings.set(LAST_AUTO_KEY, (now - timedelta(days=2)).isoformat(timespec="seconds"))
    assert is_due(context, now) is True, "a backup two days ago is due for daily"

    set_schedule(context, "weekly")
    assert is_due(context, now) is False, "two days ago is not due for weekly"
    context.settings.set(LAST_AUTO_KEY, (now - timedelta(days=8)).isoformat(timespec="seconds"))
    assert is_due(context, now) is True, "eight days ago is due for weekly"

    set_schedule(context, "off")
    assert is_due(context, now) is False, "off never makes a backup"
    assert device.client.backups() == [], "nothing was made by the schedule checks"


def test_a_due_automatic_backup_is_made_and_recorded(device: Device) -> None:
    context = device.context
    context.settings.set(LAST_AUTO_KEY, "2020-01-01T00:00:00+00:00")
    assert is_due(context) is True

    client = device.client
    on_job_thread(lambda: run_automatic(context, client, fake_job()))

    (listed,) = device.client.backups()
    assert listed["kind"] == "automatic"
    last = datetime.fromisoformat(str(context.settings.get(LAST_AUTO_KEY)))
    assert datetime.now(UTC) - last < timedelta(minutes=5)
    assert is_due(context) is False, "the backup just made is not due again"


def test_a_restore_downloads_verifies_and_offers_the_file_to_mtee(device: Device) -> None:
    backup = device.backup(MANUAL)
    recorder = RecordingSnapshots(device.context.database_snapshot)
    context = dataclasses.replace(device.context, database_snapshot=cast(Any, recorder))
    client = device.client

    target = on_job_thread(lambda: restore(context, client, fake_job(), str(backup["backup_id"])))

    assert recorder.restores == [target]
    assert target.parent == device.context.base_dir / "restore"
    assert sha256_of(target) == backup["sha256"]
    assert not target.with_name(target.name + ".part").exists()


def test_a_corrupted_download_offers_no_restore_and_says_why(
    device: Device, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = device.backup(MANUAL)
    recorder = RecordingSnapshots(device.context.database_snapshot)
    context = dataclasses.replace(device.context, database_snapshot=cast(Any, recorder))
    client = device.client
    listed_backups = client.backups

    def listed_with_another_hash() -> list[dict[str, Any]]:
        return [dict(item, sha256="0" * 64) for item in listed_backups()]

    monkeypatch.setattr(client, "backups", listed_with_another_hash)
    backup_id = str(backup["backup_id"])
    with pytest.raises(DownloadError, match="did not match the SHA-256"):
        on_job_thread(lambda: restore(context, client, fake_job(), backup_id))

    assert recorder.restores == []
    target = device.context.base_dir / "restore" / f"{backup_id}.db"
    assert not target.exists()
    assert not target.with_name(target.name + ".part").exists()


def test_a_restore_of_an_unknown_backup_is_refused_readably(device: Device) -> None:
    recorder = RecordingSnapshots(device.context.database_snapshot)
    context = dataclasses.replace(device.context, database_snapshot=cast(Any, recorder))
    client = device.client
    with pytest.raises(BackupError, match="no longer on the server"):
        on_job_thread(lambda: restore(context, client, fake_job(), "0123456789abcdef"))
    assert recorder.restores == []


def test_the_retention_settings_round_trip_on_the_server(device: Device) -> None:
    assert keep_counts(device.client) == {"daily": 30, "weekly": 12}, "the server defaults"

    assert set_keep(device.client, daily=5, weekly=3) == {"daily": 5, "weekly": 3}
    assert keep_counts(device.client) == {"daily": 5, "weekly": 3}

    with pytest.raises(ValueError, match="daily"):
        set_keep(device.client, daily=366, weekly=3)
    with pytest.raises(ValueError, match="weekly"):
        set_keep(device.client, daily=5, weekly=105)
    assert keep_counts(device.client) == {"daily": 5, "weekly": 3}


def test_deleting_a_backup_removes_it_from_the_list(device: Device) -> None:
    first = device.backup(MANUAL)
    second = device.backup(MANUAL)
    assert len(device.client.backups()) == 2

    device.client.delete_backup(str(first["backup_id"]))

    remaining = [item["backup_id"] for item in device.client.backups()]
    assert remaining == [second["backup_id"]]


def test_the_rows_and_the_summary_read_as_the_page_shows_them() -> None:
    raw = [
        {
            "backup_id": "b2",
            "kind": "automatic",
            "device_id": "d1",
            "size_bytes": 86 * 1024 * 1024,
            "created_at_utc": "2026-11-03T02:00:00+00:00",
        },
        {
            "backup_id": "b1",
            "kind": "manual",
            "device_id": "gone",
            "size_bytes": 512,
            "created_at_utc": "2026-11-01T10:30:00+00:00",
        },
    ]
    rows = backup_rows(raw, {"d1": "Studio PC"})
    assert [row["kind"] for row in rows] == ["Automatic", "Manual"]
    assert rows[0]["device"] == "Studio PC"
    assert rows[1]["device"] == "Unknown device"
    assert rows[0]["size"] == "86 MB"
    assert size_text(512) == "512 B"
    assert size_text(3 * 1024**3) == "3.0 GB"
    assert last_backup_text(raw).startswith("Last backup: ")
    assert "86 MB" in last_backup_text(raw)
    assert last_backup_text([]).startswith("No backup on the server yet")
