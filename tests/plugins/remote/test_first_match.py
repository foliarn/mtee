"""The first match end to end (plan 126.2): real server, fake local library, real database.

The local side is a folder of copies; the server side is a root of a fresh user, filled through the
API and hashed by the server itself. ``build_match`` stores nothing but the hash cache, so a Cancel
is "build and drop"; Start sync is ``apply_match``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import mutagen.flac
import pytest
from mtee.plugins.remote.connection import (  # pyright: ignore[reportMissingImports]
    ConnectionManager,
)
from mtee.plugins.remote.first_match import (  # pyright: ignore[reportMissingImports]
    FirstMatchController,
    MatchReport,
    apply_match,
    build_match,
    owned_tracks,
)
from mtee.plugins.remote.matcher import (  # pyright: ignore[reportMissingImports]
    DUPLICATE,
    UNREADABLE,
)
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    FolderMapping,
    RemoteStore,
)
from mtee.plugins.remote.ui.first_match_backend import (  # pyright: ignore[reportMissingImports]
    FirstMatchBackend,
)
from tests.plugins.remote.conftest import RemoteServer
from tests.plugins.remote.helpers import (
    FakeLibrary,
    ThreadJobs,
    copy_of,
    fake_job,
    make_context,
    make_sine,
    publish,
    signed_in,
    track,
)

from mtee.plugins.api import PluginContext

MakeUser = Callable[[], tuple[str, str]]
EXPECTED = {"matched": 1, "tags_differ": 1, "to_upload": 1, "server_only": 1, "not_matched": 2}
LINK_TABLES = (
    "remote_links",
    "remote_conflicts",
    "remote_queue",
    "remote_server_items",
    "remote_log",
)


def table_counts(context: PluginContext) -> dict[str, int]:
    conn = context.database.connection()
    return {
        name: int(conn.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"])
        for name in LINK_TABLES
    }


def retagged_copy(source: Path, destination: Path) -> Path:
    """A copy of a FLAC with another title: the tags change, the audio does not."""
    copy_of(source, destination)
    audio = mutagen.flac.FLAC(destination)
    audio["title"] = "Other title"
    audio.save()
    return destination


def scenario(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> tuple[PluginContext, FolderMapping, str, str]:
    """A folder with five local tracks, and a server with the same audio for three of them.

    Local: ``same`` (on the server too), ``dup`` (a second copy of ``same``), ``tagged`` (the server
    has its audio with other tags), ``only_local`` (not on the server) and ``missing`` (no file).
    Server only: ``only_server``.
    """
    username, password = make_user()
    local_dir = tmp_path / "Local"
    staging = tmp_path / "staging"
    same = make_sine(local_dir / "same.flac", frequency=300)
    copy_of(same, local_dir / "dup.flac")
    tagged = make_sine(local_dir / "tagged.flac", frequency=400)
    only_local = make_sine(local_dir / "only_local.flac", frequency=600)
    only_server = make_sine(staging / "only_server.flac", frequency=500)
    _, root_id = publish(
        remote_server,
        username,
        password,
        {
            "same.flac": same,
            "tagged.flac": retagged_copy(tagged, staging / "tagged.flac"),
            "only_server.flac": only_server,
        },
    )
    library = FakeLibrary(
        [local_dir],
        [
            track("same", same),
            track("dup", local_dir / "dup.flac"),
            track("tagged", tagged),
            track("only_local", only_local),
            track("missing", local_dir / "missing.flac"),
        ],
    )
    context = make_context(tmp_path / "plugin", library)
    return context, FolderMapping(str(local_dir), root_id, ""), username, password


def test_the_summary_counts_are_right(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> None:
    context, mapping, username, password = scenario(tmp_path, remote_server, make_user)
    with signed_in(remote_server, username, password) as client:
        report = build_match(context, client, [mapping], fake_job())

    assert report.result.counts == EXPECTED
    assert report.local_total == 5
    assert report.server_total == 3
    assert report.skipped == 1  # the missing file
    reasons = {entry.local.relative_path: entry.reason for entry in report.result.not_matched}
    assert reasons == {"dup.flac": DUPLICATE, "missing.flac": UNREADABLE}
    assert [pair.local.relative_path for pair in report.result.matched] == ["same.flac"]
    assert [item.relative_path for item in report.result.server_only] == ["only_server.flac"]
    assert [local.relative_path for local in report.result.to_upload] == ["only_local.flac"]


def test_cancel_writes_nothing(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> None:
    context, mapping, username, password = scenario(tmp_path, remote_server, make_user)
    with signed_in(remote_server, username, password) as client:
        build_match(context, client, [mapping], fake_job())

    assert table_counts(context) == {name: 0 for name in LINK_TABLES}


def test_start_sync_writes_the_expected_rows(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> None:
    context, mapping, username, password = scenario(tmp_path, remote_server, make_user)
    with signed_in(remote_server, username, password) as client:
        report = build_match(context, client, [mapping], fake_job())
    summary = apply_match(context, report)

    assert (summary.linked, summary.conflicts, summary.queued, summary.server_items) == (1, 1, 1, 1)
    conn = context.database.connection()

    (pair,) = report.result.matched
    link = conn.execute("SELECT * FROM remote_links").fetchone()
    assert link["track_id"] == "same"
    assert link["item_id"] == pair.server.item_id
    assert link["item_revision"] == pair.server.revision
    assert link["local_sha256"] == pair.local.sha256
    assert link["audio_hash"] == pair.local.audio_hash

    conflict = conn.execute("SELECT track_id, state FROM remote_conflicts").fetchone()
    assert (conflict["track_id"], conflict["state"]) == ("tagged", "decide_later")

    queued = conn.execute("SELECT kind, track_id, state FROM remote_queue").fetchone()
    assert (queued["kind"], queued["track_id"], queued["state"]) == (
        "upload",
        "only_local",
        "pending",
    )

    server_row = conn.execute("SELECT relative_path, sha256 FROM remote_server_items").fetchone()
    assert server_row["relative_path"] == "only_server.flac"
    assert server_row["sha256"] is not None

    log = conn.execute("SELECT text FROM remote_log").fetchall()
    assert len(log) == 1
    assert log[0]["text"].startswith("First match:")


def test_running_again_adds_nothing(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> None:
    context, mapping, username, password = scenario(tmp_path, remote_server, make_user)
    with signed_in(remote_server, username, password) as client:
        first = apply_match(context, build_match(context, client, [mapping], fake_job()))
        after_first = table_counts(context)
        second = apply_match(context, build_match(context, client, [mapping], fake_job()))
        after_second = table_counts(context)

    assert first.linked == 1
    assert (second.linked, second.conflicts, second.queued, second.server_items) == (0, 0, 0, 0)
    for name in ("remote_links", "remote_conflicts", "remote_queue", "remote_server_items"):
        assert after_second[name] == after_first[name], name


def test_a_subfolder_mapping_matches_only_inside_the_subfolder(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> None:
    username, password = make_user()
    local_dir = tmp_path / "Local"
    same = make_sine(local_dir / "same.flac", frequency=300)
    only = make_sine(tmp_path / "staging" / "only.flac", frequency=500)
    outside = make_sine(tmp_path / "staging" / "outside.flac", frequency=700)
    _, root_id = publish(
        remote_server,
        username,
        password,
        {"Incoming/same.flac": same, "Incoming/only.flac": only, "Other/outside.flac": outside},
    )
    context = make_context(tmp_path / "plugin", FakeLibrary([local_dir], [track("same", same)]))
    mapping = FolderMapping(str(local_dir), root_id, "Incoming")

    with signed_in(remote_server, username, password) as client:
        report = build_match(context, client, [mapping], fake_job())

    assert report.server_total == 2
    assert report.result.counts["matched"] == 1
    assert [item.relative_path for item in report.result.server_only] == ["only.flac"]


class _NoServerConnection:
    """A connection with no device held: the trigger asks for one and says so."""

    def client(self) -> None:
        return None


def test_the_first_connection_asks_once_and_only_with_a_linked_folder(tmp_path: Path) -> None:
    notices: list[str] = []
    library = FakeLibrary([tmp_path / "Local"], [])
    context = dataclasses.replace(make_context(tmp_path, library), notify=notices.append)
    controller = FirstMatchController(
        context, cast(ConnectionManager, _NoServerConnection()), FirstMatchBackend()
    )

    controller.on_state("connected")
    assert notices == []  # no folder is linked yet: nothing runs

    RemoteStore(context).save_mapping(FolderMapping(str(tmp_path / "Local"), "root-1", ""))
    controller.on_state("connected")
    assert notices == ["Connect to the server first."]  # the match was started, then refused

    context.settings.set("first_match_done", "true")
    notices.clear()
    controller.on_state("connected")
    assert notices == []  # done once: a later connection does not ask again


def test_a_local_subfolder_owns_only_the_tracks_inside_it(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    inside = root / "baile" / "a.flac"
    nested = root / "baile" / "deep" / "b.flac"
    outside = root / "rock" / "c.flac"
    for path in (inside, nested, outside):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    library = FakeLibrary(
        [root], [track("inside", inside), track("nested", nested), track("outside", outside)]
    )
    context = make_context(tmp_path / "plugin", library)

    owned = owned_tracks(context, [FolderMapping(str(root), "root-1", "", "baile")])

    assert {entry.track.track_id: entry.relative for entry in owned} == {
        "inside": "a.flac",
        "nested": "deep/b.flac",
    }
    assert {entry.mapping for entry in owned} == {0}


def test_the_deepest_local_folder_wins_and_relative_paths_follow_it(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    under_baile = root / "baile" / "a.flac"
    under_deep = root / "baile" / "deep" / "b.flac"
    for path in (under_baile, under_deep):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    library = FakeLibrary([root], [track("baile", under_baile), track("deep", under_deep)])
    context = make_context(tmp_path / "plugin", library)
    whole_baile = FolderMapping(str(root), "root-1", "", "baile")
    deep = FolderMapping(str(root / "baile" / "deep"), "root-2")

    owned = {
        entry.track.track_id: (entry.mapping, entry.relative)
        for entry in owned_tracks(context, [whole_baile, deep])
    }

    assert owned == {"baile": (0, "a.flac"), "deep": (1, "b.flac")}


# -- the global choice of the summary (plan 129.3) ------------------------------------------------
def conflict_ids(context: PluginContext) -> list[str]:
    rows = context.database.connection().execute("SELECT conflict_id FROM remote_conflicts")
    return [str(row["conflict_id"]) for row in rows.fetchall()]


def test_apply_match_returns_the_waiting_ids_and_a_second_run_returns_the_same_ones(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> None:
    context, mapping, username, password = scenario(tmp_path, remote_server, make_user)
    with signed_in(remote_server, username, password) as client:
        first = apply_match(context, build_match(context, client, [mapping], fake_job()))
        ids_after_first = conflict_ids(context)
        second = apply_match(context, build_match(context, client, [mapping], fake_job()))
        counts_after_second = table_counts(context)

    assert first.conflicts == 1
    assert len(first.waiting) == 1
    assert list(first.waiting) == ids_after_first
    owner = context.database.connection().execute(
        "SELECT track_id FROM remote_conflicts WHERE conflict_id = ?", (first.waiting[0],)
    )
    assert owner.fetchone()["track_id"] == "tagged"
    # The second run finds the same open conflict: nothing new is written, the ids are the same.
    assert second.conflicts == 0
    assert second.waiting == first.waiting
    assert counts_after_second["remote_conflicts"] == 1


def run_start_sync(
    context: PluginContext, report: MatchReport, choice: str
) -> tuple[list[tuple[tuple[str, ...], str]], list[str]]:
    """Press Start sync with ``choice`` in the summary; return the settle calls and the notices."""
    jobs = ThreadJobs()
    notices: list[str] = []
    running = dataclasses.replace(
        context,
        jobs=cast(Any, jobs),
        notify=notices.append,
        run_on_gui=lambda call: call(),
        refresh_ui=lambda: None,
        availability_changed=lambda _ids=None: None,
    )
    backend = FirstMatchBackend()
    controller = FirstMatchController(
        running, cast(ConnectionManager, _NoServerConnection()), backend
    )
    settled: list[tuple[tuple[str, ...], str]] = []
    controller.set_settle(lambda ids, how: settled.append((tuple(ids), how)))
    backend.show(report, "first")
    backend.setChoice(choice)
    backend.startSync()
    jobs.wait()
    assert jobs.errors == []
    return settled, notices


@pytest.mark.parametrize("choice", ["computer", "server"])
def test_a_side_chosen_for_the_summary_settles_the_waiting_pairs_once(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser, choice: str
) -> None:
    context, mapping, username, password = scenario(tmp_path, remote_server, make_user)
    with signed_in(remote_server, username, password) as client:
        report = build_match(context, client, [mapping], fake_job())

    settled, notices = run_start_sync(context, report, choice)

    waiting = conflict_ids(context)
    assert len(waiting) == 1
    assert settled == [(tuple(waiting), choice)]
    assert "1 with the same audio being settled" in notices[-1]


def test_later_settles_nothing_and_leaves_the_tags_to_decide(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> None:
    context, mapping, username, password = scenario(tmp_path, remote_server, make_user)
    with signed_in(remote_server, username, password) as client:
        report = build_match(context, client, [mapping], fake_job())

    settled, notices = run_start_sync(context, report, "later")

    assert settled == []
    assert "1 tags to decide." in notices[-1]


def test_no_tags_differ_settles_nothing(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> None:
    context, mapping, username, password = scenario(tmp_path, remote_server, make_user)
    with signed_in(remote_server, username, password) as client:
        report = build_match(context, client, [mapping], fake_job())
    no_tags = dataclasses.replace(report, result=dataclasses.replace(report.result, tags_differ=()))

    settled, notices = run_start_sync(context, no_tags, "computer")

    assert settled == []
    assert conflict_ids(context) == []
    assert "0 tags to decide." in notices[-1]
