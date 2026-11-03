"""Availability (plan 126.4) and the duplicates of the first match (follow-up A).

The statuses and the badge column read the plugin's tables, the library and the hash cache. A
second copy of a track that the first match left out must never be pushed.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from mtee.plugins.remote.availability import (  # pyright: ignore[reportMissingImports]
    LOCAL,
    REMOTE,
    SYNCED,
    availability_column,
    availability_of,
    availability_status,
)
from mtee.plugins.remote.first_match import (  # pyright: ignore[reportMissingImports]
    apply_match,
    build_match,
)
from mtee.plugins.remote.store import FolderMapping  # pyright: ignore[reportMissingImports]
from tests.plugins.remote.conftest import RemoteServer
from tests.plugins.remote.devices import (
    Computer,
    MakeUser,
    open_computer,
    source_files,
    wait_hashed,
)
from tests.plugins.remote.helpers import fake_job, sha256_of, upload_file

from mtee.plugins.api import CellValue


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return source_files(tmp_path_factory.mktemp("availability-sources"))


@pytest.fixture
def computer(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> Iterator[Computer]:
    with open_computer(tmp_path, remote_server, make_user) as device:
        yield device


def test_a_second_copy_left_out_by_the_first_match_is_never_pushed(
    computer: Computer, sources: dict[str, Path]
) -> None:
    kept = computer.add_file("a.flac", sources["short"])
    copy = computer.add_file("copy.flac", sources["short"])
    mapping = FolderMapping(str(computer.local), computer.root_id, "")
    report = build_match(computer.context, computer.client, [mapping], fake_job())

    summary = apply_match(computer.context, report)

    assert summary.queued == 1
    excluded = {
        row["track_id"]
        for row in computer.store.connection().execute("SELECT track_id FROM remote_excluded")
    }
    assert excluded == {copy}

    computer.push()
    wait_hashed(computer.client, computer.root_id)
    items = computer.client.all_items(root_id=computer.root_id)
    assert [item["relative_path"] for item in items] == ["a.flac"]
    assert items[0]["sha256"] == sha256_of(computer.path_of(kept))
    assert computer.link(kept)["item_id"] == items[0]["item_id"]
    # The excluded copy stays out of every later pass too.
    computer.detect()
    assert computer.link(kept)["item_id"] == items[0]["item_id"]
    assert (
        computer.store.connection()
        .execute("SELECT COUNT(*) AS n FROM remote_queue WHERE track_id = ?", (copy,))
        .fetchone()["n"]
        == 0
    )


def test_statuses_and_badges_follow_the_link_the_file_and_the_server(
    computer: Computer, sources: dict[str, Path]
) -> None:
    synced = computer.add_file("a.flac", sources["short"])
    computer.push()
    wait_hashed(computer.client, computer.root_id)
    local_only = computer.add_file("b.flac", sources["long"])
    peer_item = upload_file(computer.peer, computer.root_id, "Incoming/c.flac", sources["other"])
    wait_hashed(computer.client, computer.root_id)
    computer.fetch()
    remote = next(
        entry.track_id
        for entry in computer.context.track_sources.list()
        if entry.source_key == str(peer_item["item_id"])
    )

    statuses = availability_of(computer.context, computer.store, [synced, local_only, remote])
    assert statuses == {synced: SYNCED, local_only: LOCAL, remote: REMOTE}
    status = availability_status(computer.context, computer.store)
    assert dict(status([synced, local_only, remote])) == statuses

    column = availability_column(computer.context, computer.store)
    assert column.default_visible_for == ("playlist", "remote.folder")
    badges = [
        cast(CellValue, column.value_fn({"trackId": track_id}))
        for track_id in (synced, local_only, remote)
    ]
    assert [(badge.text, badge.tone) for badge in badges] == [
        ("Synced", "neutral"),
        ("On this device", "neutral"),
        ("Server only", "secondary"),
    ]
    assert column.value_fn({"trackId": ""}) is None


def test_a_linked_file_changed_on_this_computer_is_local_until_it_is_hashed(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id = computer.add_file("a.flac", sources["short"])
    computer.push()
    wait_hashed(computer.client, computer.root_id)
    assert availability_of(computer.context, computer.store, [track_id]) == {track_id: SYNCED}

    shutil.copyfile(sources["long"], computer.path_of(track_id))
    # A detection pass hashes the changed file and queues the replacement; it does not send it.
    computer.detect()

    assert availability_of(computer.context, computer.store, [track_id]) == {track_id: LOCAL}
    assert computer.link(track_id)["local_sha256"] != sha256_of(computer.path_of(track_id))


def test_a_track_with_no_link_and_no_server_item_is_local(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id = computer.add_file("a.flac", sources["short"])
    statuses = availability_of(computer.context, computer.store, [track_id, "unknown-track"])
    assert statuses == {track_id: LOCAL, "unknown-track": LOCAL}
