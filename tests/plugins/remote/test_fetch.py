"""The fetch end to end (plan 126.4): the real server, two devices, the real database.

Device A is the computer under test and device B a second device of the same account (see
``devices.py``). The file operations of device A are the fakes of ``helpers.FakeFiles``, which do
the moves on disk and record each call.
"""

from __future__ import annotations

import dataclasses
import shutil
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import mutagen.flac
import pytest
from mtee.plugins.remote.client import (  # pyright: ignore[reportMissingImports]
    ApiError,
    RemoteClient,
)
from mtee.plugins.remote.fetch import (  # pyright: ignore[reportMissingImports]
    FetchResult,
    link_pending_imports,
    set_download_new,
)
from mtee.plugins.remote.pull import AutoPull  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.sources import (  # pyright: ignore[reportMissingImports]
    ServerTrackError,
    ServerTracks,
)
from tests.plugins.remote.conftest import RemoteServer
from tests.plugins.remote.devices import (
    NO_ITEM,
    Computer,
    MakeUser,
    open_computer,
    source_files,
    wait_hashed,
)
from tests.plugins.remote.helpers import copy_of, fake_job, sha256_of, track, upload_file
from tests.plugins.remote.stream_helpers import item_facts, wait_for_copy

from mtee.domain.jobs import JobCancelledError
from mtee.plugins.api import JobContext, JobId


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Source audio, never written by a test: each test copies what it needs."""
    return source_files(tmp_path_factory.mktemp("fetch-sources"))


@pytest.fixture
def computer(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> Iterator[Computer]:
    with open_computer(tmp_path, remote_server, make_user) as device:
        yield device


def tagged_copy(source: Path, destination: Path, title: str, artist: str) -> Path:
    copy_of(source, destination)
    audio = mutagen.flac.FLAC(destination)
    audio["title"] = title
    audio["artist"] = artist
    audio.save()
    return destination


def test_a_new_upload_from_the_other_device_is_a_server_only_track(
    computer: Computer, sources: dict[str, Path], tmp_path: Path
) -> None:
    titled = tagged_copy(sources["short"], tmp_path / "t.flac", "Remote Title", "Remote Artist")
    item = upload_file(computer.peer, computer.root_id, "Incoming/titled.flac", titled)
    wait_hashed(computer.client, computer.root_id)

    result = computer.fetch()

    assert (result.server_only, result.downloaded, result.linked) == (1, 0, 0)
    item_id = str(item["item_id"])
    (entry,) = [e for e in computer.context.track_sources.list() if e.source_key == item_id]
    assert entry.available
    assert entry.track.title == "Remote Title"
    assert entry.track.artists == ("Remote Artist",)
    row = (
        computer.store.connection()
        .execute("SELECT source_track_id FROM remote_server_items WHERE item_id = ?", (item_id,))
        .fetchone()
    )
    assert row["source_track_id"] == entry.track_id
    assert computer.link_of_item(item_id) is None
    assert not list(computer.local.rglob("*.flac"))


def test_download_new_imports_the_file_into_the_mapped_folder_and_links_it(
    computer: Computer, sources: dict[str, Path]
) -> None:
    set_download_new(computer.context, True)
    item = upload_file(computer.peer, computer.root_id, "Incoming/new.flac", sources["other"])
    wait_hashed(computer.client, computer.root_id)

    result = computer.fetch()

    assert (result.downloaded, result.server_only) == (1, 0)
    imported = [call[1] for call in computer.calls() if call[0] == "import"]
    assert imported == [computer.local / "Incoming" / "new.flac"]
    assert sha256_of(imported[0]) == sha256_of(sources["other"])
    # The library scan finds the file; the link is made after it, by the same match.
    computer.library.add(track("track-new", imported[0]))
    assert link_pending_imports(computer.context, computer.store, fake_job()) == 1
    link = computer.link_of_item(str(item["item_id"]))
    assert link is not None
    assert link["track_id"] == "track-new"
    assert link["local_sha256"] == sha256_of(sources["other"]) == item["sha256"]
    assert link["server_path"] == "Incoming/new.flac"


def test_a_replacement_from_the_other_device_replaces_the_linked_file(
    computer: Computer, sources: dict[str, Path]
) -> None:
    computer.add_file("song.flac", sources["short"])
    computer.push()
    wait_hashed(computer.client, computer.root_id)
    link = computer.link("track-song.flac")
    replacement = upload_file(
        computer.peer,
        computer.root_id,
        "song.flac",
        sources["other"],
        base_item_id=str(link["item_id"]),
        base_revision=int(link["item_revision"]),
    )
    wait_hashed(computer.client, computer.root_id)

    result = computer.fetch()

    assert result.replaced == 1
    assert ("replace", "track-song.flac") in computer.calls()
    assert sha256_of(computer.path_of("track-song.flac")) == sha256_of(sources["other"])
    after = computer.link("track-song.flac")
    assert after["item_revision"] == replacement["revision"] == 2
    assert after["local_sha256"] == sha256_of(sources["other"])
    # The file it replaced went to the fake Recycle Bin, not into the void.
    recycled = list((computer.local.parent / "recycle").iterdir())
    assert [sha256_of(path) for path in recycled] == [sha256_of(sources["short"])]


def test_a_local_change_meanwhile_is_a_conflict_and_nothing_is_replaced(
    computer: Computer, sources: dict[str, Path]
) -> None:
    computer.add_file("song.flac", sources["short"])
    computer.push()
    wait_hashed(computer.client, computer.root_id)
    link = computer.link("track-song.flac")
    shutil.copyfile(sources["long"], computer.path_of("track-song.flac"))
    upload_file(
        computer.peer,
        computer.root_id,
        "song.flac",
        sources["other"],
        base_item_id=str(link["item_id"]),
        base_revision=int(link["item_revision"]),
    )
    wait_hashed(computer.client, computer.root_id)

    result = computer.fetch()

    assert (result.replaced, result.conflicts) == (0, 1)
    assert not [call for call in computer.calls() if call[0] == "replace"]
    (conflict,) = computer.conflicts()
    assert conflict["kind"] == "both_changed"
    assert conflict["track_id"] == "track-song.flac"
    assert computer.link("track-song.flac")["item_revision"] == link["item_revision"]
    assert sha256_of(computer.path_of("track-song.flac")) == sha256_of(sources["long"])


def test_a_move_from_the_other_device_moves_the_local_file_to_the_same_folder(
    computer: Computer, sources: dict[str, Path]
) -> None:
    computer.add_file("song.flac", sources["short"])
    computer.push()
    wait_hashed(computer.client, computer.root_id)
    item = computer.item_at("song.flac")
    computer.peer.move_item(str(item["item_id"]), "Moved/song.flac")

    result = computer.fetch()

    assert result.moved == 1
    assert ("move", "track-song.flac", "local-0", "Moved") in computer.calls()
    assert computer.path_of("track-song.flac") == computer.local / "Moved" / "song.flac"
    assert computer.link("track-song.flac")["server_path"] == "Moved/song.flac"
    # Both sides agree on the path now: the next push sends nothing back.
    computer.push()
    pending = computer.store.connection().execute(
        "SELECT COUNT(*) AS n FROM remote_queue WHERE state = 'pending'"
    )
    assert pending.fetchone()["n"] == 0


def test_a_trash_from_the_other_device_is_a_conflict_and_the_file_stays(
    computer: Computer, sources: dict[str, Path]
) -> None:
    computer.add_file("song.flac", sources["short"])
    computer.push()
    wait_hashed(computer.client, computer.root_id)
    item = computer.item_at("song.flac")
    computer.peer.request("POST", f"/api/v1/items/{item['item_id']}/trash")

    result = computer.fetch()

    assert result.conflicts == 1
    (conflict,) = computer.conflicts()
    assert conflict["kind"] == "deleted_on_server"
    assert computer.path_of("track-song.flac").read_bytes() == sources["short"].read_bytes()
    assert not [call for call in computer.calls() if call[0] in ("replace", "move")]


def test_a_trashed_server_only_track_leaves_the_library(
    computer: Computer, sources: dict[str, Path]
) -> None:
    item = upload_file(computer.peer, computer.root_id, "Incoming/only.flac", sources["short"])
    item_id = str(item["item_id"])
    wait_hashed(computer.client, computer.root_id)
    computer.fetch()
    assert item_id in computer.available_sources()

    computer.peer.request("POST", f"/api/v1/items/{item_id}/trash")
    result = computer.fetch()

    assert result.removed == 1
    assert item_id not in computer.available_sources()


def test_own_pushes_change_nothing_and_a_second_fetch_does_nothing(
    computer: Computer, sources: dict[str, Path]
) -> None:
    computer.add_file("song.flac", sources["short"])
    computer.push()
    wait_hashed(computer.client, computer.root_id)

    first = computer.fetch()

    assert first.entries >= 1
    assert (first.linked, first.downloaded, first.replaced, first.moved) == (0, 0, 0, 0)
    assert (first.removed, first.conflicts, first.server_only) == (0, 0, 0)
    assert computer.calls() == []
    assert computer.conflicts() == []
    assert computer.fetch() == FetchResult(pages=1)


def test_the_cursor_is_kept_here_and_on_the_server(
    computer: Computer, sources: dict[str, Path]
) -> None:
    upload_file(computer.peer, computer.root_id, "Incoming/cursor.flac", sources["short"])
    wait_hashed(computer.client, computer.root_id)

    computer.fetch()

    stored = (
        computer.store.connection()
        .execute("SELECT value FROM remote_cursors WHERE name = 'journal'")
        .fetchone()
    )
    server_seq = computer.client.get_cursor()
    assert server_seq > 0
    assert int(stored["value"]) == server_seq


class ThreadJob:
    """A job of the test: it stops at its next check once it is cancelled."""

    def __init__(self) -> None:
        self._cancel = threading.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def request_cancel(self) -> None:
        self._cancel.set()

    def raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise JobCancelledError("stopped by the test")

    def report_progress(self, value: float) -> None:
        del value


class ThreadJobs:
    """The job service of the test: each job runs on its own thread, so a test can wait for it."""

    def __init__(self) -> None:
        self.threads: list[threading.Thread] = []
        self._jobs: dict[JobId, ThreadJob] = {}

    def submit(
        self,
        task: Callable[[JobContext], None],
        *,
        label: str = "Background task",
        visible: bool = True,
        priority: int = 0,
        job_id: JobId | None = None,
        summary: object = None,
    ) -> JobId:
        del label, visible, priority, job_id, summary
        identifier = JobId.new()
        job = ThreadJob()
        self._jobs[identifier] = job

        def run() -> None:
            try:
                task(cast(JobContext, job))
            except BaseException:  # the loop logs its own errors; the thread simply ends
                return

        thread = threading.Thread(target=run, daemon=True)
        self.threads.append(thread)
        thread.start()
        return identifier

    def cancel(self, job_id: JobId) -> None:
        self._jobs[job_id].request_cancel()


def test_auto_pull_picks_up_a_change_and_stops_on_unload(
    computer: Computer, sources: dict[str, Path]
) -> None:
    jobs = ThreadJobs()
    context = dataclasses.replace(computer.context, jobs=cast(Any, jobs))
    pull = AutoPull(context, computer.store)
    pull.start(computer.client)
    try:
        item = upload_file(
            computer.peer, computer.root_id, "Incoming/pulled.flac", sources["other"]
        )
        wait_hashed(computer.client, computer.root_id)
        deadline = time.monotonic() + 20
        while str(item["item_id"]) not in computer.available_sources():
            if time.monotonic() > deadline:
                pytest.fail("The automatic pull did not bring the change in 20 seconds.")
            time.sleep(0.2)
    finally:
        started = time.monotonic()
        pull.stop()
    assert not pull.running
    for thread in jobs.threads:
        thread.join(timeout=30)
        assert not thread.is_alive()
    assert time.monotonic() - started < 30


def test_tracksource_open_streams_then_plays_the_verified_copy(
    computer: Computer, sources: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    item = upload_file(computer.peer, computer.root_id, "Incoming/played.flac", sources["other"])
    item_id = str(item["item_id"])
    wait_hashed(computer.client, computer.root_id)
    computer.fetch()

    class Link:
        """The connection as the track source sees it: a signed-in device."""

        state = "connected"

        def client(self) -> RemoteClient:
            return computer.client

    downloads: list[str] = []
    original = RemoteClient.download

    def counting(self: RemoteClient, item_id: str, target: Path, **kwargs: Any) -> Path:
        downloads.append(item_id)
        return original(self, item_id, target, **kwargs)

    monkeypatch.setattr(RemoteClient, "download", counting)
    tracks = ServerTracks(computer.context, computer.store, cast(Any, Link()))
    sha, ext = item_facts(computer.store, item_id)

    # At the Original level the first open streams the file and keeps a copy in the background.
    assert tracks.open(item_id).path is None
    first = wait_for_copy(computer.context, item_id, sha, ext)
    assert sha256_of(first) == sha256_of(sources["other"])
    assert tracks.open(item_id).path == first
    assert downloads == [item_id]
    # A cached file whose bytes are not the server's is discarded, and the track streams again.
    first.write_bytes(b"not the track")
    assert tracks.open(item_id).path is None
    assert sha256_of(wait_for_copy(computer.context, item_id, sha, ext)) == sha256_of(
        sources["other"]
    )
    assert downloads == [item_id, item_id]
    with pytest.raises(ServerTrackError):
        tracks.open(NO_ITEM)
    with pytest.raises(ApiError):
        computer.client.get_item(NO_ITEM)
