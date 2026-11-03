"""The conflicts of MTEE Remote (plan 126.6): each kind is made for real, then each choice is run.

Device A is the computer under test (``devices.Computer``), device B the second device of the same
account. Every test checks the server (items, revisions, bytes), the local calls on the fake files
(``replace_content``, ``recycle``), the link rows, the queue and the conflict row. A resolution runs
its job body directly (``ConflictWork.resolve``) with a fake job; the graphical part is checked in
``ConflictFeature`` and in the real window at the end of the file.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from mtee.plugins.remote.conflicts import (  # pyright: ignore[reportMissingImports]
    KEEP_BOTH,
    KEEP_LOCAL,
    KEEP_ONLY_HERE,
    KEEP_SERVER,
    LINK_EXISTING,
    OTHER_NAME,
    REMOVE_HERE,
    SKIP,
    UPLOAD_AGAIN,
    ConflictError,
    ConflictFeature,
    ConflictWork,
)
from mtee.plugins.remote.connection import (  # pyright: ignore[reportMissingImports]
    ConnectionManager,
)
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    CONFLICT_DECIDE_LATER,
    insert_conflict,
)
from tests.helpers.ui_plugin import (
    find_items,
    plugin_ui_of,
    settle,
    start_app,
    window_of,
    workspace_of,
)
from tests.plugins.remote.conftest import PLUGIN_DIR, RemoteServer
from tests.plugins.remote.devices import (
    Computer,
    MakeUser,
    open_computer,
    source_files,
    wait_hashed,
)
from tests.plugins.remote.helpers import fake_job, sha256_of, upload_file

from mtee.app import _shutdown
from mtee.persistence.database import Database
from mtee.plugins.api import PluginContext
from mtee.services.app_paths import resolve_app_paths

DEVICE = "Test device"


class _Link:
    """The connection of a test: the device A client, signed in."""

    def __init__(self, computer: Computer) -> None:
        self._computer = computer

    def client(self) -> Any:
        return self._computer.client


class _Status:
    """A status item that records what the connection shows."""

    def __init__(self) -> None:
        self.shown: list[tuple[str, str]] = []
        self.cleared = 0

    def update(self, text: str, tone: str = "neutral", **_: Any) -> None:
        self.shown.append((text, tone))

    def clear(self) -> None:
        self.cleared += 1


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Source audio, never written by a test: each test copies what it needs."""
    return source_files(tmp_path_factory.mktemp("conflict-sources"))


@pytest.fixture
def computer(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> Iterator[Computer]:
    with open_computer(tmp_path, remote_server, make_user) as device:
        yield device


def work_of(computer: Computer) -> ConflictWork:
    return ConflictWork(computer.context, computer.store, _Link(computer), lambda: DEVICE)


def feature_of(computer: Computer) -> ConflictFeature:
    return ConflictFeature(
        computer.context,
        computer.store,
        _Link(computer),
        lambda: DEVICE,
        lambda: None,
    )


def only_conflict(computer: Computer) -> Any:
    """The one conflict row of the store, read through the work's own reader."""
    rows = (
        computer.store.connection().execute("SELECT conflict_id FROM remote_conflicts").fetchall()
    )
    assert len(rows) == 1, f"expected one conflict row, found {len(rows)}"
    found = work_of(computer).conflict(str(rows[0]["conflict_id"]))
    assert found is not None
    return found


def queue_states(computer: Computer) -> list[tuple[str, str]]:
    rows = computer.store.connection().execute(
        "SELECT kind, state FROM remote_queue ORDER BY rowid"
    )
    return [(str(row["kind"]), str(row["state"])) for row in rows.fetchall()]


def item_of(computer: Computer, relative: str) -> dict[str, Any]:
    return computer.item_at(relative)


def stale_or_obsolete(computer: Computer, conflict_id: str) -> tuple[str, str]:
    found = work_of(computer).conflict(conflict_id)
    assert found is not None
    return found.state, str(found.local.get("resolved_action"))


# -- both_changed -----------------------------------------------------------------------------
def make_both_changed(computer: Computer, sources: dict[str, Path]) -> tuple[str, str]:
    """This computer and device B change the same file since the last sync; the fetch finds it."""
    track_id = computer.add_file("song.flac", sources["short"])
    computer.push()
    wait_hashed(computer.client, computer.root_id)
    link = computer.link(track_id)
    shutil.copyfile(sources["long"], computer.path_of(track_id))
    peer_version = upload_file(
        computer.peer,
        computer.root_id,
        "song.flac",
        sources["other"],
        base_item_id=str(link["item_id"]),
        base_revision=int(link["item_revision"]),
    )
    wait_hashed(computer.client, computer.root_id)
    result = computer.fetch()
    assert (result.conflicts, result.replaced) == (1, 0)
    conflict = only_conflict(computer)
    assert conflict.kind == "both_changed"
    return track_id, str(peer_version["item_id"])


def test_keep_this_computers_replaces_the_server_copy_with_the_base_revision(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, item_id = make_both_changed(computer, sources)
    before = computer.client.get_item(item_id)

    text = work_of(computer).resolve(only_conflict(computer).conflict_id, KEEP_LOCAL, fake_job())

    after = computer.client.get_item(item_id)
    assert after["revision"] == before["revision"] + 1
    assert after["sha256"] == sha256_of(computer.path_of(track_id))
    assert after["sha256"] == sha256_of(sources["long"])
    link = computer.link(track_id)
    assert link["item_revision"] == after["revision"]
    assert link["local_sha256"] == after["sha256"]
    conflict = only_conflict(computer)
    assert (conflict.state, conflict.local["resolved_action"]) == ("resolved", KEEP_LOCAL)
    assert conflict.local["outcome"] == text
    assert (
        computer.store.connection()
        .execute("SELECT COUNT(*) AS n FROM remote_log WHERE text LIKE ?", ("%song.flac%",))
        .fetchone()["n"]
        >= 1
    )


def test_keep_the_servers_moves_the_local_file_to_the_recycle_bin(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, _ = make_both_changed(computer, sources)
    local_before = sha256_of(computer.path_of(track_id))

    work_of(computer).resolve(only_conflict(computer).conflict_id, KEEP_SERVER, fake_job())

    assert ("replace", track_id) in computer.calls()
    assert sha256_of(computer.path_of(track_id)) == sha256_of(sources["other"])
    recycled = [sha256_of(path) for path in (computer.local.parent / "recycle").iterdir()]
    assert local_before in recycled
    link = computer.link(track_id)
    assert link["local_sha256"] == sha256_of(sources["other"])
    assert only_conflict(computer).state == "resolved"


def test_keep_both_uploads_the_local_file_under_the_device_name(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, server_item = make_both_changed(computer, sources)

    work_of(computer).resolve(only_conflict(computer).conflict_id, KEEP_BOTH, fake_job())

    copy = computer.item_at(f"song ({DEVICE}).flac")
    assert copy["sha256"] == sha256_of(computer.path_of(track_id))
    assert computer.link(track_id)["item_id"] == copy["item_id"]
    # The server's own copy keeps its name and becomes a server-only track of this computer.
    assert computer.item_at("song.flac")["item_id"] == server_item
    assert server_item in computer.available_sources()
    assert only_conflict(computer).state == "resolved"


def test_a_conflict_that_no_longer_holds_is_obsolete(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, _ = make_both_changed(computer, sources)
    conflict_id = only_conflict(computer).conflict_id
    computer.library.remove(track_id)

    text = work_of(computer).resolve(conflict_id, KEEP_LOCAL, fake_job())

    assert "no longer in the library" in text
    assert stale_or_obsolete(computer, conflict_id) == ("resolved", "obsolete")


# -- stale_revision ---------------------------------------------------------------------------
def test_a_stale_revision_is_kept_by_this_computer_on_the_current_revision(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id = computer.add_file("stale.flac", sources["short"])
    computer.push()
    wait_hashed(computer.client, computer.root_id)
    link = computer.link(track_id)
    peer_version = upload_file(
        computer.peer,
        computer.root_id,
        "stale.flac",
        sources["other"],
        base_item_id=str(link["item_id"]),
        base_revision=int(link["item_revision"]),
    )
    shutil.copyfile(sources["long"], computer.path_of(track_id))
    computer.push()
    conflict = only_conflict(computer)
    assert conflict.kind == "stale_revision"
    assert ("replace", "blocked") in queue_states(computer)

    work_of(computer).resolve(conflict.conflict_id, KEEP_LOCAL, fake_job())

    item = computer.client.get_item(str(link["item_id"]))
    assert item["revision"] == int(peer_version["revision"]) + 1
    assert item["sha256"] == sha256_of(sources["long"])
    # The blocked row is gone, so the next pass does not send the same replacement again.
    assert ("replace", "blocked") not in queue_states(computer)
    computer.push()
    assert computer.client.get_item(str(link["item_id"]))["revision"] == item["revision"]


# -- path_taken -------------------------------------------------------------------------------
def make_path_taken(computer: Computer, sources: dict[str, Path], other: Path) -> tuple[str, str]:
    """Device B has a file at the path this computer's track wants."""
    taken = upload_file(computer.peer, computer.root_id, "song.flac", other)
    track_id = computer.add_file("song.flac", sources["short"])
    computer.push()
    conflict = only_conflict(computer)
    assert conflict.kind == "path_taken"
    assert ("upload", "blocked") in queue_states(computer)
    assert computer.link_of_item(str(taken["item_id"])) is None
    return track_id, str(taken["item_id"])


def test_another_name_commits_the_upload_under_the_next_free_name(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, taken_item = make_path_taken(computer, sources, sources["other"])

    work_of(computer).resolve(only_conflict(computer).conflict_id, OTHER_NAME, fake_job())

    copy = computer.item_at("song (2).flac")
    assert copy["sha256"] == sha256_of(computer.path_of(track_id))
    assert computer.item_at("song.flac")["item_id"] == taken_item
    assert computer.item_at("song.flac")["sha256"] == sha256_of(sources["other"])
    assert computer.link(track_id)["item_id"] == copy["item_id"]
    assert ("upload", "blocked") not in queue_states(computer)


def test_link_to_the_existing_file_with_the_same_audio_uploads_nothing(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, taken_item = make_path_taken(computer, sources, sources["short"])
    wait_hashed(computer.client, computer.root_id)
    conflict_id = only_conflict(computer).conflict_id

    work = work_of(computer)
    offered = work.build_view(conflict_id, fake_job())["choices"]
    assert LINK_EXISTING in [choice["action"] for choice in offered]
    work.resolve(conflict_id, LINK_EXISTING, fake_job())

    assert computer.link(track_id)["item_id"] == taken_item
    assert computer.item_at("song.flac")["item_id"] == taken_item
    assert only_conflict(computer).state == "resolved"
    assert not [call for call in computer.calls() if call[0] == "attach"]


def test_link_to_an_existing_file_with_other_tags_keeps_a_tags_conflict(
    computer: Computer, sources: dict[str, Path], tmp_path: Path
) -> None:
    import mutagen.flac

    tagged = tmp_path / "tagged.flac"
    shutil.copyfile(sources["short"], tagged)
    audio = mutagen.flac.FLAC(tagged)
    audio["title"] = "Other title"
    audio.save()
    track_id, taken_item = make_path_taken(computer, sources, tagged)
    wait_hashed(computer.client, computer.root_id)

    work_of(computer).resolve(only_conflict(computer).conflict_id, LINK_EXISTING, fake_job())

    assert computer.link(track_id)["item_id"] == taken_item
    (tags,) = [c for c in computer.conflicts() if c["state"] != "resolved"]
    assert tags["state"] == CONFLICT_DECIDE_LATER
    assert tags["kind"] is None


def test_skip_leaves_the_track_out_of_the_sync(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, _ = make_path_taken(computer, sources, sources["other"])

    work_of(computer).resolve(only_conflict(computer).conflict_id, SKIP, fake_job())

    excluded = (
        computer.store.connection().execute("SELECT track_id FROM remote_excluded").fetchall()
    )
    assert [row["track_id"] for row in excluded] == [track_id]
    computer.push()
    assert computer.item_at("song.flac")["sha256"] == sha256_of(sources["other"])
    assert len([row for row in computer.client.all_items(root_id=computer.root_id)]) == 1


def test_a_failed_link_stays_open_with_the_readable_reason(
    computer: Computer, sources: dict[str, Path]
) -> None:
    make_path_taken(computer, sources, sources["other"])
    conflict_id = only_conflict(computer).conflict_id

    with pytest.raises(ConflictError, match="same audio"):
        work_of(computer).resolve(conflict_id, LINK_EXISTING, fake_job())

    conflict = only_conflict(computer)
    assert conflict.state == "open"
    assert "same audio" in conflict.local["last_error"]


# -- deleted_on_server ------------------------------------------------------------------------
def make_deleted(computer: Computer, sources: dict[str, Path]) -> tuple[str, str]:
    track_id = computer.add_file("song.flac", sources["short"])
    computer.push()
    wait_hashed(computer.client, computer.root_id)
    item = computer.item_at("song.flac")
    computer.peer.request("POST", f"/api/v1/items/{item['item_id']}/trash")
    assert computer.fetch().conflicts == 1
    conflict = only_conflict(computer)
    assert conflict.kind == "deleted_on_server"
    return track_id, str(item["item_id"])


def test_upload_again_puts_the_file_back_as_a_new_item(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, trashed = make_deleted(computer, sources)

    work_of(computer).resolve(only_conflict(computer).conflict_id, UPLOAD_AGAIN, fake_job())

    again = computer.item_at("song.flac")
    assert again["item_id"] != trashed
    assert again["sha256"] == sha256_of(computer.path_of(track_id))
    assert computer.link(track_id)["item_id"] == again["item_id"]
    assert only_conflict(computer).state == "resolved"


def test_keep_only_on_this_computer_unlinks_and_excludes_the_track(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, trashed = make_deleted(computer, sources)

    work_of(computer).resolve(only_conflict(computer).conflict_id, KEEP_ONLY_HERE, fake_job())

    assert computer.link_of_item(trashed) is None
    assert computer.path_of(track_id).is_file()
    computer.push()
    assert computer.client.all_items(root_id=computer.root_id) == []
    assert only_conflict(computer).state == "resolved"


def test_remove_from_this_computer_waits_for_the_core_confirmation(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, _ = make_deleted(computer, sources)
    feature = feature_of(computer)
    conflict_id = only_conflict(computer).conflict_id

    feature.choose(conflict_id, REMOVE_HERE)

    assert ("recycle", [track_id]) in computer.calls()
    waiting = only_conflict(computer)
    assert waiting.state == "open"
    assert waiting.local.get("awaiting_recycle") is True
    snapshot = feature.snapshot(conflict_id)
    assert snapshot["awaiting"] is True and snapshot["finished"] is True

    # The core removes the track once the file is in the Recycle Bin; the next pass closes it.
    computer.library.remove(track_id)
    feature.refresh()

    done = only_conflict(computer)
    assert (done.state, done.local["resolved_action"]) == ("resolved", REMOVE_HERE)
    assert computer.link_of_item(str(done.item_id)) is None


def test_an_unknown_action_for_the_kind_is_refused(
    computer: Computer, sources: dict[str, Path]
) -> None:
    make_deleted(computer, sources)

    with pytest.raises(ConflictError, match="does not apply"):
        work_of(computer).resolve(only_conflict(computer).conflict_id, KEEP_SERVER, fake_job())


# -- decide later, dismiss and reopen --------------------------------------------------------
def test_a_first_match_tags_conflict_is_listed_and_resolved_by_keeping_the_servers(
    computer: Computer, sources: dict[str, Path]
) -> None:
    """Same audio on both sides, tags differ: the first match leaves the track in Conflicts."""
    track_id = computer.add_file("tags.flac", sources["short"])
    computer.push()
    wait_hashed(computer.client, computer.root_id)
    item = computer.item_at("tags.flac")
    # Device B's copy has other bytes now (other tags, other audio), so keeping the server's
    # version downloads it and puts it in place of this file.
    replaced = upload_file(
        computer.peer,
        computer.root_id,
        "tags.flac",
        sources["other"],
        base_item_id=str(item["item_id"]),
        base_revision=int(item["revision"]),
    )
    with computer.store.transaction() as conn:
        conn.execute("DELETE FROM remote_links WHERE track_id = ?", (track_id,))
        insert_conflict(
            conn,
            track_id=track_id,
            item_id=str(item["item_id"]),
            local={"relative_path": "tags.flac", "sha256": sha256_of(computer.path_of(track_id))},
            server={"item_id": str(item["item_id"]), "sha256": item["sha256"]},
            state=CONFLICT_DECIDE_LATER,
        )
    feature = feature_of(computer)
    feature.refresh()
    (row,) = feature.model.rows()
    assert row["subtitle"] == "Tags differ" and row["action"] == "Resolve"

    work_of(computer).resolve(str(row["id"]), KEEP_SERVER, fake_job())

    assert sha256_of(computer.path_of(track_id)) == sha256_of(sources["other"])
    link = computer.link(track_id)
    assert (link["item_id"], link["item_revision"]) == (
        replaced["item_id"],
        replaced["revision"],
    )
    feature.refresh()
    assert feature.model.rows() == []


def test_dismissed_conflict_is_hidden_until_a_change_reopens_it(
    computer: Computer, sources: dict[str, Path]
) -> None:
    track_id, _ = make_both_changed(computer, sources)
    feature = feature_of(computer)
    feature.refresh()
    conflict_id = only_conflict(computer).conflict_id
    assert [row["id"] for row in feature.model.rows()] == [conflict_id]
    assert feature.open_count() == 1

    feature.dismiss_waiting(conflict_id)

    assert feature.model.rows() == []
    assert feature.open_count() == 0
    assert only_conflict(computer).state == "decide_later"

    # Device B changes the file again: the next fetch reopens the same conflict.
    link = computer.link(track_id)
    upload_file(
        computer.peer,
        computer.root_id,
        "song.flac",
        sources["short"],
        base_item_id=str(link["item_id"]),
        base_revision=int(computer.client.get_item(str(link["item_id"]))["revision"]),
    )
    wait_hashed(computer.client, computer.root_id)
    computer.fetch()
    feature.refresh()

    reopened = only_conflict(computer)
    assert (reopened.conflict_id, reopened.state) == (conflict_id, "open")
    assert [row["id"] for row in feature.model.rows()] == [conflict_id]


def test_waiting_row_title_subtitle_and_tab_request(
    computer: Computer, sources: dict[str, Path]
) -> None:
    make_both_changed(computer, sources)
    feature = feature_of(computer)
    feature.refresh()
    conflict_id = only_conflict(computer).conflict_id

    (row,) = feature.model.rows()
    assert row == {
        "id": conflict_id,
        "title": "song",
        "subtitle": "Changed on both sides",
        "action": "Resolve",
    }
    request = feature.run_waiting(conflict_id)
    assert request is not None
    assert (request.kind, request.ref) == ("remote.conflict", conflict_id)
    assert feature.tab_title(conflict_id) == "Conflict · song"


def test_the_status_item_shows_the_conflict_count_with_the_warning_tone(
    computer: Computer, sources: dict[str, Path]
) -> None:
    make_both_changed(computer, sources)
    feature = feature_of(computer)
    status = _Status()
    context = cast(PluginContext, dataclasses.replace(computer.context, status_item=status))
    connection = ConnectionManager(context)
    connection.set_open_conflicts(feature.open_count)

    connection.refresh_status()
    assert status.shown[-1] == ("1 conflict", "warning")

    connection.set_open_conflicts(lambda: 3)
    connection.refresh_status()
    assert status.shown[-1] == ("3 conflicts", "warning")

    connection.set_open_conflicts(lambda: 0)
    connection.refresh_status()
    assert status.cleared == 1


def test_the_snapshot_of_a_resolved_conflict_holds_the_outcome(
    computer: Computer, sources: dict[str, Path]
) -> None:
    make_both_changed(computer, sources)
    feature = feature_of(computer)
    conflict_id = only_conflict(computer).conflict_id
    work_of(computer).resolve(conflict_id, KEEP_LOCAL, fake_job())

    view = feature.snapshot(conflict_id)

    assert view["resolved"] is True and view["finished"] is True
    assert "replaced" in view["outcome"]
    assert view["choices"] == []
    json.dumps(view)  # the tab reads it as JSON


# -- the window ---------------------------------------------------------------------------------
def _insert_deleted_conflict(data_dir: Path) -> str:
    """Write one open conflict into the plugin's table of a stopped application."""
    paths = resolve_app_paths(data_dir).ensure()
    database = Database(paths.database_path)
    conflict_id = "ui-conflict-0001"
    local = {"kind": "deleted_on_server", "relative_path": "Artist/Song.flac", "sha256": "ab" * 32}
    server = {"kind": "deleted_on_server", "item_id": "0" * 32, "state": "trashed"}
    with database.transaction() as conn:
        conn.execute(
            "INSERT INTO remote_conflicts (conflict_id, track_id, item_id, local_json,"
            " server_json, created_at_utc, state) VALUES (?, ?, ?, ?, ?, ?, 'open')",
            (
                conflict_id,
                "ui-track-0001",
                "0" * 32,
                json.dumps(local, sort_keys=True),
                json.dumps(server, sort_keys=True),
                "2026-11-01T10:00:00+00:00",
            ),
        )
    database.close()
    return conflict_id


def test_the_conflict_tab_loads_with_both_columns_in_the_real_window(
    qapp: object, tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    _shutdown(start_app(data_dir, (PLUGIN_DIR,), ("remote",)))
    conflict_id = _insert_deleted_conflict(data_dir)

    runtime = start_app(data_dir, (PLUGIN_DIR,), ("remote",))
    try:
        ui = plugin_ui_of(workspace_of(runtime))
        settle(runtime)
        assert ui.waitingCount == 1

        ui.runWaiting("remote.conflicts", conflict_id)
        settle(runtime)

        window = window_of(runtime)
        sides = sorted(item.property("text") for item in find_items(window, "conflictSideCaption"))
        assert sides == ["Server", "This computer"]
        assert len(find_items(window, "conflictValue")) >= 16, "both columns of the rows"
        assert find_items(window, "conflictVersions")
        assert find_items(window, "conflictReason")
        # One visible button per choice: the ghost one, or the red one for a destructive choice.
        shown = [
            item
            for name in ("conflictChoice", "conflictChoiceDanger")
            for item in find_items(window, name)
            if item.property("visible") is True
        ]
        assert len(shown) == 3, "upload again, remove from this computer, keep only here"
        (outcome_card,) = find_items(window, "conflictOutcomeCard")
        assert outcome_card.property("visible") is False, "no outcome before a choice"
    finally:
        _shutdown(runtime)
