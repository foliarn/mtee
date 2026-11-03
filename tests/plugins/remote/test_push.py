"""The push end to end (plan 126.3): the real server, a fake local library and the real database.

The local folder is a folder of copies in a temporary directory; the source files are never written.
Each pass runs ``detect_changes`` and ``run_queue`` directly, with ``idle_delay_s=0`` unless the
test is about the idle delay. The engine (timer, modes, status bar) is tested in ``test_engine.py``.
"""

from __future__ import annotations

import dataclasses
import json
import os
import secrets
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import mutagen.flac
import pytest
from mtee.plugins.remote.client import RemoteClient  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.push import (  # pyright: ignore[reportMissingImports]
    DetectReport,
    QueueReport,
    detect_changes,
    pending_count,
    run_queue,
)
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    CONFLICT_DECIDE_LATER,
    CONFLICT_OPEN,
    FolderMapping,
    RemoteStore,
    insert_conflict,
)
from tests.plugins.remote.conftest import RemoteServer
from tests.plugins.remote.helpers import (
    FakeLibrary,
    copy_of,
    fake_job,
    make_context,
    make_sine,
    new_root,
    sha256_of,
    signed_in,
    track,
    tree_digests,
    upload_file,
)

from mtee.domain.jobs import JobCancelledError
from mtee.plugins.api import JobContext, PluginContext

CHUNK = 2048
MakeUser = Callable[[], tuple[str, str]]


class StopAfterChunk:
    """A job the test cancels once a chunk went out, as a user cancelling it in Tasks would."""

    def __init__(self) -> None:
        self.cancelled = False

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelledError("cancelled by the test")

    def report_progress(self, progress: float) -> None:
        return None


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Source audio, never written by a test: the tests copy them."""
    folder = tmp_path_factory.mktemp("push-sources")
    return {
        "short": make_sine(folder / "short.flac", 440, seconds=2),
        "long": make_sine(folder / "long.flac", 660, seconds=8),
        "other": make_sine(folder / "other.flac", 880, seconds=2),
    }


@dataclasses.dataclass
class Push:
    """One device of a test: its context, its folder of copies, and its signed-in client."""

    server: RemoteServer
    context: PluginContext
    store: RemoteStore
    library: FakeLibrary
    local: Path
    client: RemoteClient
    root_id: str

    def add_file(self, name: str, source: Path) -> str:
        """Copy ``source`` into the folder, written ten seconds ago; return its track id."""
        path = copy_of(source, self.local / name)
        written = time.time() - 10
        os.utime(path, (written, written))
        track_id = f"track-{name}"
        self.library.add(track(track_id, path))
        return track_id

    def path_of(self, track_id: str) -> Path:
        return self.library.tracks([track_id])[0].path

    def run(self, *, now: float | None = None, idle: float = 0) -> tuple[DetectReport, QueueReport]:
        detected = detect_changes(
            self.context,
            self.store,
            idle_delay_s=idle,
            now=time.time() if now is None else now,
            job=fake_job(),
        )
        queued = run_queue(self.context, self.store, self.client, fake_job(), chunk_bytes=CHUNK)
        return detected, queued

    def link(self, track_id: str) -> dict[str, Any] | None:
        row = (
            self.store.connection()
            .execute("SELECT * FROM remote_links WHERE track_id = ?", (track_id,))
            .fetchone()
        )
        return None if row is None else dict(row)

    def ops(self) -> list[dict[str, Any]]:
        rows = self.store.connection().execute("SELECT * FROM remote_queue ORDER BY rowid")
        return [dict(row) for row in rows.fetchall()]

    def conflicts(self) -> list[dict[str, Any]]:
        rows = self.store.connection().execute("SELECT * FROM remote_conflicts")
        return [dict(row) for row in rows.fetchall()]

    def items(self) -> list[dict[str, Any]]:
        return self.client.all_items(root_id=self.root_id)

    def wait_hashed(self) -> None:
        """Wait until the server has hashed its items.

        The server holds a file open while it hashes it, and on Windows it cannot move or replace
        that file until it lets go. A second operation on a fresh item must wait for the hashing,
        as a person working a little later would.
        """
        deadline = time.monotonic() + 60
        while any(item.get("hash_state") not in ("done", "error") for item in self.items()):
            if time.monotonic() > deadline:
                pytest.fail("The server did not hash the uploaded items in time.")
            time.sleep(0.2)


@pytest.fixture
def push(tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser) -> Iterator[Push]:
    username, password = make_user()
    with signed_in(remote_server, username, password) as client:
        root_id = new_root(client)
        local = tmp_path / "Music"
        local.mkdir()
        library = FakeLibrary([local], [])
        context = make_context(tmp_path, library)
        store = RemoteStore(context)
        store.save_mapping(FolderMapping(str(local), root_id, ""))
        yield Push(remote_server, context, store, library, local, client, root_id)


def test_a_new_file_is_uploaded_and_linked(push: Push, sources: dict[str, Path]) -> None:
    track_id = push.add_file("new.flac", sources["short"])

    detected, queued = push.run()

    assert (detected.uploads, queued.sent, queued.pending) == (1, 1, 0)
    (summary,) = push.items()
    item = push.client.get_item(str(summary["item_id"]))
    assert item["relative_path"] == "new.flac"
    assert item["sha256"] == sha256_of(sources["short"]) == sha256_of(push.path_of(track_id))
    link = push.link(track_id)
    assert link is not None
    assert link["item_id"] == item["item_id"]
    assert link["item_revision"] == item["revision"]
    assert link["server_path"] == "new.flac"
    assert link["local_sha256"] == item["sha256"]
    assert [op["state"] for op in push.ops()] == ["done"]


def test_a_tag_edit_sends_a_replacement_of_the_same_item(
    push: Push, sources: dict[str, Path]
) -> None:
    track_id = push.add_file("tagged.flac", sources["short"])
    push.run()
    push.wait_hashed()
    before = push.link(track_id)
    assert before is not None

    audio = mutagen.flac.FLAC(push.path_of(track_id))
    audio["title"] = "Edited on this computer"
    audio.save()
    detected, queued = push.run()

    assert (detected.replacements, queued.sent) == (1, 1)
    item = push.client.get_item(str(before["item_id"]))
    assert item["revision"] == before["item_revision"] + 1
    link = push.link(track_id)
    assert link is not None
    assert link["item_id"] == before["item_id"]
    assert link["item_revision"] == item["revision"]
    assert link["local_sha256"] == item["sha256"] == sha256_of(push.path_of(track_id))
    assert link["local_sha256"] != before["local_sha256"]
    assert link["audio_hash"] == before["audio_hash"]
    assert len(push.items()) == 1


def test_a_rename_sends_a_move_of_the_same_item(push: Push, sources: dict[str, Path]) -> None:
    track_id = push.add_file("first.flac", sources["short"])
    push.run()
    push.wait_hashed()
    before = push.link(track_id)
    assert before is not None

    renamed = push.local / "renamed.flac"
    os.replace(push.path_of(track_id), renamed)
    push.library.set_path(track_id, renamed)
    detected, queued = push.run()

    assert (detected.moves, queued.sent) == (1, 1)
    item = push.client.get_item(str(before["item_id"]))
    assert item["relative_path"] == "renamed.flac"
    assert [entry["item_id"] for entry in push.items()] == [before["item_id"]]
    link = push.link(track_id)
    assert link is not None
    assert link["server_path"] == "renamed.flac"


def test_a_file_changed_less_than_the_idle_delay_ago_is_not_sent(
    push: Push, sources: dict[str, Path]
) -> None:
    push.add_file("fresh.flac", sources["short"])
    now = time.time()

    detected, queued = push.run(now=now, idle=120)

    assert (detected.waiting, detected.uploads, queued.sent) == (1, 0, 0)
    assert push.items() == []

    detected, queued = push.run(now=now + 300, idle=120)

    assert (detected.uploads, queued.sent) == (1, 1)
    assert len(push.items()) == 1


def test_a_cut_upload_resumes_from_the_bytes_the_server_holds(
    push: Push, sources: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    source = sources["long"]
    assert source.stat().st_size > 2 * CHUNK
    track_id = push.add_file("long.flac", source)
    opened: list[dict[str, Any]] = []
    open_upload = push.client.open_upload

    def count_open(**fields: Any) -> dict[str, Any]:
        opened.append(fields)
        return open_upload(**fields)

    job = StopAfterChunk()
    send_chunk = push.client.upload_chunk

    def cancel_after_one_chunk(upload_id: str, start: int, data: bytes, total: int) -> int:
        received = send_chunk(upload_id, start, data, total)
        job.cancelled = True
        return received

    monkeypatch.setattr(push.client, "open_upload", count_open)
    monkeypatch.setattr(push.client, "upload_chunk", cancel_after_one_chunk)
    detected = detect_changes(push.context, push.store, idle_delay_s=0, now=time.time())
    assert detected.uploads == 1
    with pytest.raises(JobCancelledError):
        run_queue(
            push.context,
            push.store,
            push.client,
            cast(JobContext, job),
            chunk_bytes=CHUNK,
        )

    (op,) = push.ops()
    assert op["state"] == "pending"
    upload_id = json.loads(op["payload_json"])["upload_id"]
    assert push.client.upload_status(upload_id)["received_bytes"] == CHUNK
    assert push.items() == []

    monkeypatch.setattr(push.client, "upload_chunk", send_chunk)
    queued = run_queue(push.context, push.store, push.client, fake_job(), chunk_bytes=CHUNK)

    assert queued.sent == 1
    assert len(opened) == 1, "the second run must resume the upload, not open another"
    (item,) = push.items()
    assert item["sha256"] == sha256_of(source)
    link = push.link(track_id)
    assert link is not None
    assert link["local_sha256"] == item["sha256"]


def test_a_path_taken_on_the_server_blocks_the_upload_and_overwrites_nothing(
    push: Push, sources: dict[str, Path]
) -> None:
    taken = upload_file(push.client, push.root_id, "taken.flac", sources["other"])
    track_id = push.add_file("taken.flac", sources["short"])

    detected, queued = push.run()

    assert (detected.uploads, queued.blocked, queued.sent) == (1, 1, 0)
    (op,) = push.ops()
    assert op["state"] == "blocked"
    assert op["last_error"] == "A file already exists at that path."
    (conflict,) = push.conflicts()
    assert conflict["state"] == "open"
    assert json.loads(conflict["local_json"])["kind"] == "path_taken"
    assert push.link(track_id) is None
    (server_item,) = push.items()
    assert server_item["item_id"] == taken["item_id"]
    assert server_item["sha256"] == sha256_of(sources["other"])

    detected, queued = push.run()

    assert (detected.uploads, queued.sent) == (0, 0)
    assert len(push.conflicts()) == 1


def test_a_stale_revision_blocks_the_replacement_and_keeps_the_server_file(
    push: Push, sources: dict[str, Path]
) -> None:
    track_id = push.add_file("stale.flac", sources["short"])
    push.run()
    push.wait_hashed()
    before = push.link(track_id)
    assert before is not None
    # Another device replaces the item first, so this device's base revision is stale.
    replaced = upload_file(
        push.client,
        push.root_id,
        "stale.flac",
        sources["other"],
        base_item_id=str(before["item_id"]),
        base_revision=int(before["item_revision"]),
    )
    assert replaced["revision"] == before["item_revision"] + 1

    audio = mutagen.flac.FLAC(push.path_of(track_id))
    audio["title"] = "Edited here"
    audio.save()
    detected, queued = push.run()

    assert (detected.replacements, queued.blocked, queued.sent) == (1, 1, 0)
    op = push.ops()[-1]  # the first upload is done; the replacement is the second row
    assert (op["kind"], op["state"]) == ("replace", "blocked")
    (conflict,) = push.conflicts()
    assert json.loads(conflict["local_json"])["kind"] == "stale_revision"
    item = push.client.get_item(str(before["item_id"]))
    assert item["revision"] == replaced["revision"]
    assert item["sha256"] == sha256_of(sources["other"])
    link = push.link(track_id)
    assert link is not None
    assert link["item_revision"] == before["item_revision"]


def test_a_full_quota_fails_the_upload_with_a_readable_sentence(
    tmp_path: Path, remote_server: RemoteServer, sources: dict[str, Path]
) -> None:
    username = "tiny" + secrets.token_hex(4)
    password = secrets.token_urlsafe(18)
    admin = RemoteClient(remote_server.url)
    _, admin_token = admin.login(remote_server.username, remote_server.password, "Test: quota")
    admin_session = RemoteClient(remote_server.url, admin_token)
    admin_session.request(
        "POST",
        "/api/v1/admin/users",
        json={"username": username, "password": password, "quota_bytes": 1000},
    )
    admin_session.logout()

    with signed_in(remote_server, username, password) as client:
        root_id = new_root(client)
        local = tmp_path / "Music"
        local.mkdir()
        library = FakeLibrary([local], [])
        notices: list[str] = []
        context = dataclasses.replace(make_context(tmp_path, library), notify=notices.append)
        store = RemoteStore(context)
        store.save_mapping(FolderMapping(str(local), root_id, ""))
        push = Push(remote_server, context, store, library, local, client, root_id)
        push.add_file("big.flac", sources["short"])

        _, queued = push.run()

        assert (queued.failed, queued.sent) == (1, 0)
        (op,) = push.ops()
        assert op["state"] == "failed"
        assert op["last_error"] == "This upload would exceed the storage quota."
        assert notices == ["Not sent to the server: This upload would exceed the storage quota."]
        assert push.items() == []


def test_a_pass_reads_the_local_files_and_changes_none(
    push: Push, sources: dict[str, Path]
) -> None:
    push.add_file("a.flac", sources["short"])
    push.add_file("b.flac", sources["other"])
    before = tree_digests(push.local)
    source_before = tree_digests(sources["short"].parent)

    push.run()
    detected, queued = push.run()

    assert tree_digests(push.local) == before
    assert tree_digests(sources["short"].parent) == source_before
    assert (detected.uploads, queued.sent) == (0, 0)
    assert pending_count(push.store) == 0
    assert len(push.items()) == 2


def hold(push: Push, track_id: str, state: str) -> None:
    """A conflict row of the track that waits for the person, as a first match writes it."""
    with push.store.transaction() as conn:
        insert_conflict(
            conn,
            track_id=track_id,
            item_id="item-of-the-same-audio",
            local={"relative_path": "held.flac"},
            server={"relative_path": "Server copy.flac"},
            state=state,
        )


def test_a_track_waiting_for_an_open_first_match_conflict_is_not_uploaded(
    push: Push, sources: dict[str, Path]
) -> None:
    track_id = push.add_file("held.flac", sources["short"])
    hold(push, track_id, CONFLICT_OPEN)

    detected, queued = push.run()

    assert (detected.held, detected.uploads, queued.sent) == (1, 0, 0)
    assert push.ops() == []
    assert push.items() == []
    assert push.link(track_id) is None


def test_a_track_waiting_for_a_decide_later_conflict_is_not_uploaded(
    push: Push, sources: dict[str, Path]
) -> None:
    track_id = push.add_file("later.flac", sources["short"])
    hold(push, track_id, CONFLICT_DECIDE_LATER)

    detected, queued = push.run()

    assert (detected.held, detected.uploads, queued.sent) == (1, 0, 0)
    assert push.ops() == []
    assert push.items() == []


def test_a_resolved_conflict_releases_the_track_to_the_next_pass(
    push: Push, sources: dict[str, Path]
) -> None:
    track_id = push.add_file("released.flac", sources["short"])
    hold(push, track_id, CONFLICT_DECIDE_LATER)
    detected, queued = push.run()
    assert (detected.held, queued.sent) == (1, 0)

    with push.store.transaction() as conn:
        conn.execute(
            "UPDATE remote_conflicts SET state = 'resolved' WHERE track_id = ?", (track_id,)
        )
    detected, queued = push.run()

    assert (detected.held, detected.uploads, queued.sent) == (0, 1, 1)
    assert len(push.items()) == 1
    assert push.link(track_id) is not None


def test_a_held_track_keeps_its_pending_row_and_run_does_not_send_it(
    push: Push, sources: dict[str, Path]
) -> None:
    track_id = push.add_file("pending.flac", sources["short"])
    push.run()
    push.wait_hashed()
    before = push.link(track_id)
    assert before is not None
    audio = mutagen.flac.FLAC(push.path_of(track_id))
    audio["title"] = "Edited on this computer"
    audio.save()
    queued_by_detection = detect_changes(
        push.context, push.store, idle_delay_s=0, now=time.time(), job=fake_job()
    )
    assert queued_by_detection.replacements == 1
    rows_before = push.ops()
    hold(push, track_id, CONFLICT_OPEN)

    detected, queued = push.run()

    assert (detected.held, detected.replacements, queued.sent) == (1, 0, 0)
    assert push.ops() == rows_before, "the pending row is neither deleted nor refreshed"
    assert pending_count(push.store) == 1
    item = push.client.get_item(str(before["item_id"]))
    assert item["revision"] == before["item_revision"]
    assert push.link(track_id) == before
