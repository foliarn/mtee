"""Offload, download and the delete choices (plan 126.5): the real server and the real database.

Device A is the computer under test (``devices.Computer``, with a fake library over copies in a
temporary folder); device B is a second device of the same account that changes the server. The
file operations of device A are the fakes of ``helpers.FakeFiles``: ``attach_file`` and ``recycle``
move files on disk, ``recycle_now`` is the job side of ``DeleteRequest.recycle`` (the fake Recycle
Bin). ``track_sources.adopt`` is recorded by ``helpers.FakeTrackSources``.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from mtee.plugins.remote.availability import (  # pyright: ignore[reportMissingImports]
    REMOTE,
    SYNCED,
    availability_of,
)
from mtee.plugins.remote.client import ApiError  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.offload import (  # pyright: ignore[reportMissingImports]
    DELETE_EVERYWHERE,
    DOWNLOAD_ACTION,
    FREE_UP_ACTION,
    REMOVE_LOCAL,
    OffloadService,
    download_tracks,
    format_size,
)
from mtee.plugins.remote.sources import (  # pyright: ignore[reportMissingImports]
    ServerTracks,
)
from tests.plugins.remote.conftest import RemoteServer
from tests.plugins.remote.devices import (
    Computer,
    MakeUser,
    open_computer,
    source_files,
    wait_hashed,
)
from tests.plugins.remote.helpers import (
    FakeFiles,
    copy_of,
    fake_job,
    sha256_of,
    upload_file,
)

from mtee.plugins.api import DeleteRequest, JobContext


class _Link:
    """The connection of a test: a client, as the connection manager gives it while signed in."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def client(self) -> Any:
        return self._client


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Source audio, never written by a test: each test copies what it needs."""
    return source_files(tmp_path_factory.mktemp("offload-sources"))


@pytest.fixture
def computer(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> Iterator[Computer]:
    with open_computer(tmp_path, remote_server, make_user) as device:
        yield device


def service(device: Computer) -> OffloadService:
    return OffloadService(device.context, device.store, _Link(device.client))


def files_of(device: Computer) -> FakeFiles:
    return cast(FakeFiles, device.context.files)


def request_for(device: Computer, choice_id: str, track_ids: list[str]) -> DeleteRequest:
    """The request a delete choice receives: the selection, and the recycle of the fake Bin."""
    return DeleteRequest(
        choice_id=choice_id,
        track_ids=tuple(track_ids),
        job=cast(JobContext, fake_job()),
        _recycle=files_of(device).recycle_now,
    )


def add_and_push(device: Computer, sources: dict[str, Path], name: str = "a.flac") -> str:
    """A local track that is uploaded, so it is linked to its server item; return its track id."""
    track_id = device.add_file(name, sources["short"])
    device.push()
    return track_id


def add_server_track(
    device: Computer, sources: dict[str, Path], relative: str = "remote.flac"
) -> tuple[str, str]:
    """A track that the other device uploaded and this one fetched without a download.

    Return ``(track_id, item_id)``: the server-only track of this device.
    """
    upload_file(device.peer, device.root_id, relative, sources["other"])
    wait_hashed(device.client, device.root_id)
    device.fetch()
    return server_only_of(device, relative)


def server_only_of(device: Computer, relative: str) -> tuple[str, str]:
    row = (
        device.store.connection()
        .execute(
            "SELECT item_id, source_track_id FROM remote_server_items WHERE relative_path = ?",
            (relative,),
        )
        .fetchone()
    )
    assert row is not None and row["source_track_id"] is not None, f"{relative} is not server only"
    return str(row["source_track_id"]), str(row["item_id"])


def server_item_gone(device: Computer, item_id: str) -> bool:
    try:
        device.client.get_item(item_id)
    except ApiError as error:
        return error.status == 404
    return False


def adopted_of(device: Computer) -> list[tuple[str, Any]]:
    """The calls of ``track_sources.adopt`` on this device (see ``helpers.FakeTrackSources``)."""
    return list(cast(Any, device.context.track_sources).adopted)


def source_row(device: Computer, item_id: str) -> Any:
    return (
        device.store.connection()
        .execute("SELECT source_track_id FROM remote_server_items WHERE item_id = ?", (item_id,))
        .fetchone()
    )


def test_format_size_reads_like_the_mockups() -> None:
    assert format_size(0) == "0 B"
    assert format_size(2048) == "2.0 KB"
    assert format_size(59 * 1024**2) == "59 MB"
    assert format_size(int(1.2 * 1024**3)) == "1.2 GB"


# -- offer -----------------------------------------------------------------------------------
def test_a_linked_track_offers_remove_from_this_computer_first_and_delete_everywhere(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id = add_and_push(computer, sources)

    choices = service(computer).delete_choices().offer([track_id])

    assert [choice.choice_id for choice in choices] == [REMOVE_LOCAL, DELETE_EVERYWHERE]
    remove, delete = choices
    assert remove.label == "Remove from this computer"
    assert remove.tone == "normal" and remove.replaces_recycle
    assert remove.description.startswith("Frees ")
    assert remove.description.endswith("The tracks stay on the server and play from there.")
    assert delete.label == "Delete everywhere"
    assert delete.tone == "danger" and delete.replaces_recycle
    assert delete.description == "Moves the files to the Recycle Bin and the server trash."


def test_a_server_only_track_offers_delete_everywhere_only(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, _ = add_server_track(computer, sources)

    choices = service(computer).delete_choices().offer([track_id])

    assert [choice.choice_id for choice in choices] == [DELETE_EVERYWHERE]


def test_a_track_that_is_local_only_gets_no_choice(
    computer: Computer, sources: dict[str, Path]
) -> None:
    linked = add_and_push(computer, sources, "linked.flac")
    local_only = computer.add_file("local.flac", sources["short"])  # added after the push

    assert service(computer).delete_choices().offer([local_only]) == []
    assert service(computer).delete_choices().offer([linked, local_only]) == []


# -- remove from this computer ------------------------------------------------------------------
def test_remove_from_this_computer_frees_a_synced_track_and_keeps_its_id(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id = add_and_push(computer, sources)
    original = computer.path_of(track_id)
    item_id = str(computer.link(track_id)["item_id"])
    request = request_for(computer, REMOVE_LOCAL, [track_id])

    text = service(computer).delete_choices().run(request)

    assert text.startswith("Freed ")
    assert ("recycle_now", [track_id]) in files_of(computer).calls
    assert not original.exists()
    assert computer.link_of_item(item_id) is None
    adopted = adopted_of(computer)
    assert [track for track, _ in adopted] == [track_id]
    assert adopted[0][1].source_key == item_id
    assert source_row(computer, item_id)["source_track_id"] == track_id
    assert availability_of(computer.context, computer.store, [track_id]) == {track_id: REMOTE}
    assert not server_item_gone(computer, item_id)


def test_a_changed_server_copy_is_skipped_and_nothing_is_recycled(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id = add_and_push(computer, sources, "changed-server.flac")
    link = computer.link(track_id)
    item = computer.item_at("changed-server.flac")
    upload_file(
        computer.peer,
        computer.root_id,
        "changed-server.flac",
        sources["other"],
        base_item_id=str(item["item_id"]),
        base_revision=int(link["item_revision"]),
    )
    original = computer.path_of(track_id)
    request = request_for(computer, REMOVE_LOCAL, [track_id])

    text = service(computer).delete_choices().run(request)

    assert "skipped 1 track (changed since the last sync)" in text
    assert text.startswith("Nothing was freed")
    assert not any(call[0] == "recycle_now" for call in files_of(computer).calls)
    assert original.is_file()
    assert computer.link(track_id)["item_revision"] == link["item_revision"]


def test_a_changed_local_file_is_skipped_and_nothing_is_recycled(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id = add_and_push(computer, sources, "changed-local.flac")
    original = computer.path_of(track_id)
    copy_of(sources["other"], original)
    now = time.time()
    os.utime(original, (now, now))
    request = request_for(computer, REMOVE_LOCAL, [track_id])

    text = service(computer).delete_choices().run(request)

    assert "skipped 1 track (changed since the last sync)" in text
    assert not any(call[0] == "recycle_now" for call in files_of(computer).calls)
    assert original.is_file()
    assert sha256_of(original) == sha256_of(sources["other"])
    assert computer.link(track_id) is not None


# -- delete everywhere --------------------------------------------------------------------------
def test_delete_everywhere_recycles_the_local_file_and_trashes_the_server_copy(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id = add_and_push(computer, sources, "gone.flac")
    original = computer.path_of(track_id)
    item_id = str(computer.link(track_id)["item_id"])
    request = request_for(computer, DELETE_EVERYWHERE, [track_id])

    text = service(computer).delete_choices().run(request)

    assert "went to the Recycle Bin" in text and "server trash" in text
    assert not original.exists()
    assert computer.link_of_item(item_id) is None
    assert server_item_gone(computer, item_id)
    assert (
        computer.store.connection()
        .execute("SELECT 1 FROM remote_server_items WHERE item_id = ?", (item_id,))
        .fetchone()
        is None
    )


def test_delete_everywhere_trashes_a_server_only_track(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, item_id = add_server_track(computer, sources, "only-remote.flac")
    request = request_for(computer, DELETE_EVERYWHERE, [track_id])

    text = service(computer).delete_choices().run(request)

    assert text == "1 server copy went to the server trash."
    assert server_item_gone(computer, item_id)
    assert item_id not in computer.available_sources()
    assert not any(call[0] == "recycle_now" for call in files_of(computer).calls)


def test_a_server_error_is_reported_and_the_local_recycling_stays(
    computer: Computer, sources: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    track_id = add_and_push(computer, sources, "refused.flac")
    original = computer.path_of(track_id)
    item_id = str(computer.link(track_id)["item_id"])

    def refused(item: str) -> str:
        raise ApiError(409, "conflict", "The file is missing on the server; scan the root first.")

    monkeypatch.setattr(computer.client, "trash_item", refused)
    request = request_for(computer, DELETE_EVERYWHERE, [track_id])

    text = service(computer).delete_choices().run(request)

    assert "1 file went to the Recycle Bin" in text
    assert "1 server copy not deleted: The file is missing on the server" in text
    assert not original.exists()
    assert computer.link(track_id)["item_id"] == item_id
    assert not server_item_gone(computer, item_id)
    logged = computer.store.connection().execute(
        "SELECT level, text FROM remote_log WHERE text LIKE ?", (f"%{item_id}%",)
    )
    assert [(row["level"], row["text"]) for row in logged.fetchall()] == [
        (
            "error",
            f"Server copy {item_id} not deleted: The file is missing on the server; "
            "scan the root first.",
        )
    ]


# -- the track menu: Free up space and Download ---------------------------------------------------
def action(device: Computer, action_id: str) -> Any:
    return next(item for item in service(device).track_actions() if item.action_id == action_id)


def test_free_up_space_asks_the_core_for_its_confirmation_of_synced_rows(
    computer: Computer, sources: dict[str, Path]
) -> None:
    linked = add_and_push(computer, sources, "synced.flac")
    remote, _ = add_server_track(computer, sources, "elsewhere.flac")
    local_only = computer.add_file("unsent.flac", sources["short"])
    free = action(computer, FREE_UP_ACTION)

    assert free.enabled_fn([{"trackId": linked}]) is True
    assert free.enabled_fn([{"trackId": linked}, {"trackId": remote}]) is False
    assert free.enabled_fn([{"trackId": local_only}]) is False
    assert free.enabled_fn([{"trackId": ""}]) is False

    free.run([{"trackId": linked}])

    assert ("recycle", [linked]) in files_of(computer).calls


def test_download_is_enabled_for_server_only_rows_only(
    computer: Computer, sources: dict[str, Path]
) -> None:
    linked = add_and_push(computer, sources, "have.flac")
    remote, _ = add_server_track(computer, sources, "want.flac")
    download = action(computer, DOWNLOAD_ACTION)

    assert download.enabled_fn([{"trackId": remote}]) is True
    assert download.enabled_fn([{"trackId": remote}, {"trackId": linked}]) is False
    assert download.enabled_fn([{"trackId": linked}]) is False


def test_download_puts_the_file_in_its_folder_under_the_same_track_id(
    computer: Computer, sources: dict[str, Path]
) -> None:
    upload_file(computer.peer, computer.root_id, "Album/from-server.flac", sources["long"])
    wait_hashed(computer.client, computer.root_id)
    computer.fetch()
    track_id, item_id = server_only_of(computer, "Album/from-server.flac")
    item = computer.item_at("Album/from-server.flac")

    text = download_tracks(
        computer.context, computer.store, computer.client, fake_job(), [track_id]
    )

    final = computer.local / "Album" / "from-server.flac"
    assert text == "Downloaded 1 track."
    assert final.is_file()
    assert ("attach", track_id, computer.local / "Album") in files_of(computer).calls
    assert sha256_of(final) == item["sha256"]
    link = computer.link(track_id)
    assert link["item_id"] == item_id
    assert link["local_sha256"] == item["sha256"]
    assert link["server_path"] == "Album/from-server.flac"
    assert source_row(computer, item_id)["source_track_id"] is None
    assert availability_of(computer.context, computer.store, [track_id]) == {track_id: SYNCED}
    assert item_id not in computer.available_sources()


def test_a_cached_copy_is_reused_without_a_second_download(
    computer: Computer, sources: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    upload_file(computer.peer, computer.root_id, "Cached/played.flac", sources["short"])
    wait_hashed(computer.client, computer.root_id)
    computer.fetch()
    track_id, item_id = server_only_of(computer, "Cached/played.flac")
    downloads: list[str] = []
    original = computer.client.download

    def counting(item: str, target: Path, **options: Any) -> Path:
        downloads.append(item)
        return original(item, target, **options)

    monkeypatch.setattr(computer.client, "download", counting)
    # Playing the track downloads its original into the cache (plan 126.4).
    played = ServerTracks(computer.context, computer.store, cast(Any, _Link(computer.client)))
    played.open(item_id)
    assert downloads == [item_id]

    text = download_tracks(
        computer.context, computer.store, computer.client, fake_job(), [track_id]
    )

    assert text == "Downloaded 1 track."
    assert downloads == [item_id]  # the cached copy was used
    assert (computer.local / "Cached" / "played.flac").is_file()
    assert not (computer.context.data_dir / "cache" / f"{item_id}.flac").exists()


def test_download_refuses_a_track_that_is_not_server_only(
    computer: Computer, sources: dict[str, Path]
) -> None:
    linked = add_and_push(computer, sources, "already-here.flac")

    text = download_tracks(computer.context, computer.store, computer.client, fake_job(), [linked])

    assert text == "Nothing to download: the selected tracks are not server only."
    assert computer.link(linked) is not None
    assert not any(call[0] == "attach" for call in files_of(computer).calls)
