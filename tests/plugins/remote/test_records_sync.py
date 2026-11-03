"""The records end to end (plan 126.7): the real server, two devices, the real databases.

Device A and device B are two computers of one account (see ``records_helpers.py``). Each has a
mapped folder on the same server root, its own database, and the core records of sync. The file
operations are the fakes of ``helpers.FakeFiles``; the files are copies of synthetic audio.
"""

from __future__ import annotations

import dataclasses
import os
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from mtee.plugins.remote.client import RemoteClient  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.conflicts import (  # pyright: ignore[reportMissingImports]
    KEEP_BOTH,
    KEEP_LOCAL,
    KEEP_SERVER,
    ConflictWork,
)
from mtee.plugins.remote.fetch import fetch_once  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.push import (  # pyright: ignore[reportMissingImports]
    detect_changes,
    pending_count,
    run_queue,
)
from mtee.plugins.remote.records import (  # pyright: ignore[reportMissingImports]
    item_of_track,
    pull_play_events,
    push_play_events,
    push_settings,
    push_track_data,
    set_travel,
    sync_playlists,
    track_of_item,
    travel_rows,
)
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    FolderMapping,
    RemoteStore,
)
from tests.plugins.remote.conftest import RemoteServer
from tests.plugins.remote.devices import MakeUser, source_files, wait_hashed
from tests.plugins.remote.helpers import (
    FakeLibrary,
    copy_of,
    fake_job,
    new_root,
    signed_in,
    track,
)
from tests.plugins.remote.records_helpers import (
    SyncDevice,
    journal_kinds,
    local_playlist_of,
    log_texts,
    make_sync_context,
    new_device_id,
    record_play,
    register_track,
    server_playlist_of,
)

from mtee.plugins.api import CreditCorrection, TrackAnalysisData, TrackLoudnessData


@dataclasses.dataclass
class Pair:
    """Device A (the computer under test) and device B, another computer of the same account."""

    a: SyncDevice
    b: SyncDevice


class _Link:
    """What the conflicts need of the connection: the client of the signed-in device."""

    def __init__(self, client: RemoteClient) -> None:
        self._client = client

    def client(self) -> RemoteClient:
        return self._client


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Source audio, never written by a test: each test copies what it needs."""
    return source_files(tmp_path_factory.mktemp("records-sources"))


@pytest.fixture
def pair(tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser) -> Iterator[Pair]:
    username, password = make_user()
    with (
        signed_in(remote_server, username, password) as client_a,
        signed_in(remote_server, username, password) as client_b,
    ):
        root_id = new_root(client_a)
        devices = []
        for name, client in (("a", client_a), ("b", client_b)):
            folder = tmp_path / name
            local = folder / "Music"
            local.mkdir(parents=True)
            library = FakeLibrary([local], [])
            context, stub = make_sync_context(folder, library, new_device_id())
            store = RemoteStore(context)
            store.save_mapping(FolderMapping(str(local), root_id, ""))
            devices.append(
                SyncDevice(
                    context=context,
                    stub=stub,
                    store=store,
                    library=library,
                    local=local,
                    client=client,
                    root_id=root_id,
                    core_device_id=context.play_log.device_id,
                )
            )
        yield Pair(a=devices[0], b=devices[1])


def add_file(device: SyncDevice, name: str, source: Path) -> str:
    """Copy ``source`` into the device's watched folder, written long ago; return its track id."""
    path = copy_of(source, device.local / name)
    written = time.time() - 10
    os.utime(path, (written, written))
    track_id = f"track-{name}"
    device.library.add(track(track_id, path))
    register_track(device, track_id, Path(name).stem)
    return track_id


def push_files(device: SyncDevice) -> None:
    """One push pass of the files: what is new in the folder is uploaded (no idle delay)."""
    detect_changes(device.context, device.store, idle_delay_s=0, now=time.time(), job=fake_job())
    run_queue(device.context, device.store, device.client, fake_job())
    assert pending_count(device.store) == 0
    wait_hashed(device.client, device.root_id)


def fetch(device: SyncDevice) -> None:
    fetch_once(device.context, device.store, device.client, fake_job())


def item_of(device: SyncDevice, track_id: str) -> str:
    item_id = item_of_track(device.store, track_id)
    assert item_id is not None, f"{track_id} has no item"
    return item_id


def share_one_track(pair: Pair, sources: dict[str, Path]) -> str:
    """Device A uploads one track; device B fetches it, where it is a server-only track."""
    track_id = add_file(pair.a, "one.flac", sources["short"])
    push_files(pair.a)
    fetch(pair.b)
    return track_id


def items_of_entries(device: SyncDevice, playlist_id: str) -> list[str | None]:
    entries = device.context.playlists.entries(playlist_id)
    return [item_of_track(device.store, entry.track_id) for entry in entries]


# -- the play log -------------------------------------------------------------------------------
def test_plays_of_one_device_reach_the_other_once_and_are_not_pulled_back(
    pair: Pair, sources: dict[str, Path]
) -> None:
    track_id = share_one_track(pair, sources)
    item_id = item_of(pair.a, track_id)
    b_track = track_of_item(pair.b.store, item_id)
    assert b_track is not None
    record_play(pair.a, track_id)
    record_play(pair.a, track_id, seconds=120)

    assert push_play_events(pair.a.context, pair.a.store, pair.a.client) == 2
    assert push_play_events(pair.a.context, pair.a.store, pair.a.client) == 0
    stored = pair.a.client.play_events(since=0, limit=500)
    assert [event["payload"]["item_id"] for event in stored.events] == [item_id, item_id]

    assert pull_play_events(pair.b.context, pair.b.store, pair.b.client) == 2
    assert pull_play_events(pair.b.context, pair.b.store, pair.b.client) == 0
    received, _ = pair.b.context.play_log.events_since(None, 100)
    assert len(received) == 2
    assert {event.device_id for event in received} == {pair.a.core_device_id}
    assert {event.track_id for event in received} == {b_track}

    # The own events of device A come back from the server and are not stored a second time.
    assert pull_play_events(pair.a.context, pair.a.store, pair.a.client) == 0
    own, _ = pair.a.context.play_log.events_since(None, 100)
    assert len(own) == 2


def test_a_play_of_a_track_not_on_the_server_is_counted_as_skipped(
    pair: Pair, sources: dict[str, Path]
) -> None:
    local_only = add_file(pair.a, "local.flac", sources["other"])
    record_play(pair.a, local_only)

    assert push_play_events(pair.a.context, pair.a.store, pair.a.client) == 1
    stored = pair.a.client.play_events(since=0, limit=500)
    assert stored.events[0]["payload"]["item_id"] is None

    assert pull_play_events(pair.b.context, pair.b.store, pair.b.client) == 0
    received, _ = pair.b.context.play_log.events_since(None, 100)
    assert received == []
    assert any("skipped" in line for line in log_texts(pair.b.store))


# -- playlists ------------------------------------------------------------------------------------
def test_a_playlist_reaches_the_other_device_and_an_edit_comes_back(
    pair: Pair, sources: dict[str, Path]
) -> None:
    first = share_one_track(pair, sources)
    second = add_file(pair.a, "two.flac", sources["other"])
    push_files(pair.a)
    fetch(pair.b)
    playlist = pair.a.context.playlists.create("Mix", [first, second])
    assert sync_playlists(pair.a.context, pair.a.store, pair.a.client) == 1

    server = [meta for meta in pair.a.client.playlists() if meta["name"] == "Mix"]
    assert len(server) == 1
    server_id = str(server[0]["playlist_id"])
    assert server_playlist_of(pair.a.store, playlist) == server_id
    on_server = pair.a.client.playlist(server_id)["entries"]
    assert [entry["item_id"] for entry in on_server] == [
        item_of(pair.a, first),
        item_of(pair.a, second),
    ]

    fetch(pair.b)
    b_playlist = local_playlist_of(pair.b.store, server_id)
    assert b_playlist is not None
    assert items_of_entries(pair.b, b_playlist) == [item_of(pair.a, first), item_of(pair.a, second)]

    b_second_track = track_of_item(pair.b.store, item_of(pair.a, second))
    assert b_second_track is not None
    pair.b.context.playlists.replace_entries(
        b_playlist,
        [b_second_track],
        expected_revision=pair.b.context.playlists.revision(b_playlist),
    )
    assert sync_playlists(pair.b.context, pair.b.store, pair.b.client) == 1

    fetch(pair.a)
    assert items_of_entries(pair.a, playlist) == [item_of(pair.a, second)]


def test_a_playlist_with_a_track_not_on_the_server_is_skipped_and_logged(
    pair: Pair, sources: dict[str, Path]
) -> None:
    uploaded = add_file(pair.a, "one.flac", sources["short"])
    push_files(pair.a)
    local_only = add_file(pair.a, "local.flac", sources["other"])
    pair.a.context.playlists.create("Partly", [uploaded, local_only])

    assert sync_playlists(pair.a.context, pair.a.store, pair.a.client) == 0
    assert all(meta["name"] != "Partly" for meta in pair.a.client.playlists())
    assert "Partly is not synced: 1 track is not on the server." in log_texts(pair.a.store)


def _conflicting_playlist(pair: Pair, sources: dict[str, Path]) -> tuple[str, str, str]:
    """A playlist changed on both sides since the last sync.

    Returns the local playlist of A, its server playlist, and the conflict id.
    """
    first = share_one_track(pair, sources)
    second = add_file(pair.a, "two.flac", sources["other"])
    push_files(pair.a)
    fetch(pair.b)
    playlist = pair.a.context.playlists.create("Mix", [first])
    sync_playlists(pair.a.context, pair.a.store, pair.a.client)
    server_id = server_playlist_of(pair.a.store, playlist)
    assert server_id is not None
    fetch(pair.b)
    b_playlist = local_playlist_of(pair.b.store, server_id)
    assert b_playlist is not None
    b_second = track_of_item(pair.b.store, item_of(pair.a, second))
    assert b_second is not None
    # The title a server-only track has on device B (the core shows its tags).
    pair.b.stub.titles[b_second] = "two"

    pair.a.context.playlists.replace_entries(playlist, [first, second])
    pair.b.context.playlists.replace_entries(
        b_playlist,
        [b_second],
        expected_revision=pair.b.context.playlists.revision(b_playlist),
    )
    assert sync_playlists(pair.b.context, pair.b.store, pair.b.client) == 1
    assert sync_playlists(pair.a.context, pair.a.store, pair.a.client) == 0

    rows = (
        pair.a.store.connection()
        .execute("SELECT conflict_id, local_json, state FROM remote_conflicts")
        .fetchall()
    )
    assert len(rows) == 1
    assert rows[0]["state"] == "open"
    assert '"kind": "playlist_both_changed"' in rows[0]["local_json"]
    # A second pass does not open the same conflict again.
    assert sync_playlists(pair.a.context, pair.a.store, pair.a.client) == 0
    assert (
        pair.a.store.connection().execute("SELECT COUNT(*) FROM remote_conflicts").fetchone()[0]
        == 1
    )
    return playlist, server_id, str(rows[0]["conflict_id"])


def _work(pair: Pair) -> ConflictWork:
    return ConflictWork(pair.a.context, pair.a.store, _Link(pair.a.client), lambda: "Device A")


def test_a_playlist_changed_on_both_sides_is_a_conflict_and_keep_the_server_works(
    pair: Pair, sources: dict[str, Path]
) -> None:
    playlist, _, conflict_id = _conflicting_playlist(pair, sources)
    text = _work(pair).resolve(conflict_id, KEEP_SERVER, fake_job())
    assert "server's tracks" in text
    assert items_of_entries(pair.a, playlist) == [item_of(pair.a, _track_named(pair.a, "two"))]


def test_a_playlist_changed_on_both_sides_keep_this_computer_works(
    pair: Pair, sources: dict[str, Path]
) -> None:
    playlist, server_id, conflict_id = _conflicting_playlist(pair, sources)
    _work(pair).resolve(conflict_id, KEEP_LOCAL, fake_job())
    on_server = pair.a.client.playlist(server_id)["entries"]
    assert len(on_server) == 2
    assert items_of_entries(pair.a, playlist) == [entry["item_id"] for entry in on_server]


def test_a_playlist_changed_on_both_sides_keep_both_makes_a_copy(
    pair: Pair, sources: dict[str, Path]
) -> None:
    playlist, server_id, conflict_id = _conflicting_playlist(pair, sources)
    _work(pair).resolve(conflict_id, KEEP_BOTH, fake_job())
    names = sorted(meta["name"] for meta in pair.a.client.playlists() if not meta["deleted"])
    assert names == ["Mix", "Mix (server)"]
    copies = [
        local
        for local in _local_playlists(pair.a)
        if local != playlist and pair.a.context.playlists.name(local) == "Mix (server)"
    ]
    assert len(copies) == 1
    assert items_of_entries(pair.a, copies[0]) == [item_of(pair.a, _track_named(pair.a, "two"))]
    # The server's "Mix" now holds this computer's version: both tracks.
    assert len(pair.a.client.playlist(server_id)["entries"]) == 2


def test_a_playlist_renamed_on_the_server_is_renamed_here_and_not_sent_back(
    pair: Pair, sources: dict[str, Path]
) -> None:
    first = share_one_track(pair, sources)
    playlist = pair.a.context.playlists.create("Mix", [first])
    assert sync_playlists(pair.a.context, pair.a.store, pair.a.client) == 1
    server_id = server_playlist_of(pair.a.store, playlist)
    assert server_id is not None
    fetch(pair.b)
    b_playlist = local_playlist_of(pair.b.store, server_id)
    assert b_playlist is not None
    b_revision = pair.b.context.playlists.revision(b_playlist)
    pair.b.context.playlists.rename(b_playlist, "Renamed", expected_revision=b_revision)
    assert sync_playlists(pair.b.context, pair.b.store, pair.b.client) == 1

    fetch(pair.a)

    assert pair.a.context.playlists.name(playlist) == "Renamed"
    assert sync_playlists(pair.a.context, pair.a.store, pair.a.client) == 0  # nothing to send back


def _track_named(device: SyncDevice, stem: str) -> str:
    """The local track of ``device`` whose file is ``stem``.flac (the tests name their files so)."""
    del device
    return f"track-{stem}.flac"


def _local_playlists(device: SyncDevice) -> list[str]:
    rows = device.context.database.connection().execute("SELECT playlist_id FROM playlists")
    return [str(row[0]) for row in rows.fetchall()]


# -- track data ----------------------------------------------------------------------------------
def test_track_data_reaches_the_other_device_and_is_not_sent_back(
    pair: Pair, sources: dict[str, Path]
) -> None:
    track_id = share_one_track(pair, sources)
    item_id = item_of(pair.a, track_id)
    a_data = pair.a.context.track_data
    a_data.write_analysis(
        track_id,
        TrackAnalysisData(
            bpm=120.0,
            key_tonic=9,
            key_minor=True,
            algorithm_version=3,
            analyzed_at_utc="2026-10-01T10:00:00+00:00",
        ),
    )
    a_data.write_loudness(
        track_id,
        TrackLoudnessData(integrated_lufs=-14.2, sample_peak_dbfs=-1.0, loudness_version=2),
    )
    a_data.write_corrections(track_id, [CreditCorrection("Tester", "split")])

    assert push_track_data(pair.a.context, pair.a.store, pair.a.client) == 1
    assert push_track_data(pair.a.context, pair.a.store, pair.a.client) == 0
    assert set(pair.a.client.track_data(item_id)) == {"analysis", "loudness", "corrections"}

    b_track = track_of_item(pair.b.store, item_id)
    assert b_track is not None
    fetch(pair.b)
    received = pair.b.context.track_data.read(b_track)
    assert received.analysis is not None
    assert received.analysis.bpm == 120.0
    assert received.analysis.key_tonic == 9
    assert received.loudness is not None
    assert received.loudness.integrated_lufs == -14.2
    assert received.corrections == (CreditCorrection("Tester", "split"),)

    # Nothing that device B received is sent back: no new track data entry on the server.
    before = journal_kinds(pair.a.client).count("track_data")
    assert push_track_data(pair.b.context, pair.b.store, pair.b.client) == 0
    fetch(pair.a)
    assert push_track_data(pair.a.context, pair.a.store, pair.a.client) == 0
    assert journal_kinds(pair.a.client).count("track_data") == before


def test_a_track_data_push_after_one_change_reads_and_sends_only_that_track(
    pair: Pair, sources: dict[str, Path]
) -> None:
    first = share_one_track(pair, sources)
    second = add_file(pair.a, "two.flac", sources["other"])
    push_files(pair.a)
    data = pair.a.context.track_data
    client = pair.a.client
    data.write_analysis(first, TrackAnalysisData(bpm=100.0))
    data.write_analysis(second, TrackAnalysisData(bpm=110.0))
    assert push_track_data(pair.a.context, pair.a.store, client) == 2

    data.write_loudness(second, TrackLoudnessData(-12.0, -1.0, loudness_version=1))
    with (
        patch.object(client, "put_track_data", wraps=client.put_track_data) as put,
        patch.object(client, "track_data", wraps=client.track_data) as get,
    ):
        assert push_track_data(pair.a.context, pair.a.store, client) == 1

    assert [call.args[0] for call in put.call_args_list] == [item_of(pair.a, second)]
    assert [call.args[0] for call in get.call_args_list] == [item_of(pair.a, second)]


def test_a_track_linked_after_its_data_changed_is_pushed_on_the_next_pass(
    pair: Pair, sources: dict[str, Path]
) -> None:
    share_one_track(pair, sources)
    assert push_track_data(pair.a.context, pair.a.store, pair.a.client) == 0
    later = add_file(pair.a, "two.flac", sources["other"])
    pair.a.context.track_data.write_analysis(later, TrackAnalysisData(bpm=100.0))
    # The pass runs before the file is uploaded: its change is in the log, but no item exists yet.
    assert push_track_data(pair.a.context, pair.a.store, pair.a.client) == 0

    push_files(pair.a)  # the upload links the track to its item

    assert push_track_data(pair.a.context, pair.a.store, pair.a.client) == 1
    assert set(pair.a.client.track_data(item_of(pair.a, later))) == {"analysis"}


# -- synced settings -------------------------------------------------------------------------------
def test_an_enabled_synced_setting_travels_and_a_disabled_one_does_not(
    pair: Pair,
) -> None:
    a_settings = pair.a.context.synced_settings
    a_settings.write(
        {
            "profile/display_name": "Anna",
            "playlists/columns": '{"hidden":[],"order":["title"],"showArtwork":true,"widths":{}}',
        }
    )
    set_travel(pair.a.context, "playlists/columns", False)

    assert push_settings(pair.a.context, pair.a.store, pair.a.client) == 1
    server = pair.a.client.records_settings()
    assert server == {"profile/display_name": "Anna"}

    fetch(pair.b)
    b_values = pair.b.context.synced_settings.read()
    assert b_values.get("profile/display_name") == "Anna"
    assert "playlists/columns" not in b_values

    # The value received is not sent back: the server's settings and the journal are unchanged.
    before = journal_kinds(pair.a.client).count("settings")
    assert push_settings(pair.b.context, pair.b.store, pair.b.client) == 0
    assert journal_kinds(pair.a.client).count("settings") == before
    assert pair.a.client.records_settings() == {"profile/display_name": "Anna"}


def test_a_new_device_keeps_the_setting_of_the_server_on_first_contact(pair: Pair) -> None:
    pair.a.context.synced_settings.write({"profile/display_name": "Anna"})
    assert push_settings(pair.a.context, pair.a.store, pair.a.client) == 1

    pair.b.context.synced_settings.write({"profile/display_name": "Bea"})
    assert push_settings(pair.b.context, pair.b.store, pair.b.client) == 0
    assert pair.b.context.synced_settings.read()["profile/display_name"] == "Anna"
    assert pair.a.client.records_settings() == {"profile/display_name": "Anna"}


def test_the_playlist_conflict_view_shows_both_track_lists_and_the_choices(
    pair: Pair, sources: dict[str, Path]
) -> None:
    _, _, conflict_id = _conflicting_playlist(pair, sources)
    view = _work(pair).build_view(conflict_id, fake_job())
    assert view["kind"] == "playlist_both_changed"
    assert view["lists"]["thisSide"] == ["Tester - one", "Tester - two"]
    assert view["lists"]["serverSide"] == ["Tester - two"]
    tracks_row = next(row for row in view["rows"] if row["label"] == "Tracks")
    assert tracks_row["differs"] is True
    assert [choice["action"] for choice in view["choices"]] == [KEEP_LOCAL, KEEP_SERVER, KEEP_BOTH]


def test_the_travel_switches_follow_the_synced_keys(pair: Pair) -> None:
    rows = travel_rows(pair.a.context)
    assert {row["key"] for row in rows} == set(pair.a.context.synced_settings.keys)
    assert all(row["enabled"] for row in rows)
    set_travel(pair.a.context, "plugins.enabled", False)
    switched = {row["key"]: row["enabled"] for row in travel_rows(pair.a.context)}
    assert switched["plugins.enabled"] is False
    assert switched["profile/display_name"] is True
    with pytest.raises(ValueError):
        set_travel(pair.a.context, "analysis/settings", True)
