"""The indexes of migration 007 and the daily housekeeping of the tables (review of 0.3.0)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mtee.plugins.remote import maintenance  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    RemoteStore,
    write_log,
)
from tests.plugins.remote.helpers import FakeLibrary, make_context, track

from mtee.plugins.api import PluginContext

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def setup(tmp_path: Path) -> tuple[PluginContext, RemoteStore, Path]:
    music = tmp_path / "music"
    kept = music / "kept.flac"
    library = FakeLibrary([music], [track("t1", kept)])
    context = make_context(tmp_path, library)
    return context, RemoteStore(context), kept


def _plan(store: RemoteStore, sql: str, *args: object) -> str:
    rows = store.connection().execute(f"EXPLAIN QUERY PLAN {sql}", args).fetchall()
    return " ".join(str(row["detail"]) for row in rows)


def test_the_lookups_of_every_pass_use_an_index(
    setup: tuple[PluginContext, RemoteStore, Path],
) -> None:
    _context, store, _kept = setup
    assert "remote_queue_track" in _plan(
        store, "SELECT op_id FROM remote_queue WHERE track_id = ? AND state <> 'done'", "t1"
    )
    assert "remote_server_items_source_track" in _plan(
        store, "SELECT item_id FROM remote_server_items WHERE source_track_id = ?", "t1"
    )
    assert "remote_conflicts_state" in _plan(
        store, "SELECT COUNT(*) FROM remote_conflicts WHERE state IN ('open', 'decide_later')"
    )


def _queue(store: RemoteStore, op_id: str, state: str, updated: datetime) -> None:
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO remote_queue (op_id, kind, track_id, state, created_at_utc,"
            " updated_at_utc) VALUES (?, 'upload', 't1', ?, ?, ?)",
            (op_id, state, updated.isoformat(), updated.isoformat()),
        )


def test_housekeeping_deletes_old_done_operations_only(
    setup: tuple[PluginContext, RemoteStore, Path],
) -> None:
    context, store, _kept = setup
    old = NOW - timedelta(days=8)
    _queue(store, "old-done", "done", old)
    _queue(store, "new-done", "done", NOW - timedelta(days=1))
    _queue(store, "old-failed", "failed", old)
    _queue(store, "old-pending", "pending", old)

    report = maintenance.run(context, store, now=NOW)

    left = {row["op_id"] for row in store.connection().execute("SELECT op_id FROM remote_queue")}
    assert left == {"new-done", "old-failed", "old-pending"}
    assert report.done_deleted == 1


def test_housekeeping_keeps_the_newest_log_lines(
    setup: tuple[PluginContext, RemoteStore, Path],
) -> None:
    context, store, _kept = setup
    with store.transaction() as conn:
        for index in range(maintenance.LOG_KEPT + 25):
            write_log(conn, f"line {index}")

    report = maintenance.run(context, store, now=NOW)

    rows = store.connection().execute("SELECT text FROM remote_log ORDER BY log_id").fetchall()
    assert len(rows) == maintenance.LOG_KEPT
    assert rows[0]["text"] == "line 25"
    assert rows[-1]["text"] == f"line {maintenance.LOG_KEPT + 24}"
    assert report.log_deleted == 25
    # A short log is left as it is.
    assert maintenance.run(context, store, now=NOW).log_deleted == 0


def test_housekeeping_forgets_the_hashes_of_files_that_left(
    setup: tuple[PluginContext, RemoteStore, Path], tmp_path: Path
) -> None:
    context, store, kept = setup
    waiting = tmp_path / "music" / "download.flac"
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO remote_imports (item_id, local_path, relative_path, sha256,"
            " created_at_utc) VALUES ('i1', ?, 'download.flac', 'aa', '')",
            (str(waiting),),
        )
    for path in (kept, waiting, tmp_path / "music" / "renamed away.flac"):
        key = os.path.normcase(os.path.abspath(path))
        with store.transaction() as conn:
            conn.execute(
                "INSERT INTO remote_hash_cache (path, size_bytes, mtime_ns, sha256)"
                " VALUES (?, 1, 1, 'aa')",
                (key,),
            )

    report = maintenance.run(context, store, now=NOW)

    left = {
        Path(row["path"]).name
        for row in store.connection().execute("SELECT path FROM remote_hash_cache")
    }
    assert left == {"kept.flac", "download.flac"}
    assert report.hashes_deleted == 1


def test_housekeeping_is_due_once_a_day(setup: tuple[PluginContext, RemoteStore, Path]) -> None:
    context, store, _kept = setup
    assert maintenance.is_due(context, NOW)
    maintenance.run(context, store, now=NOW)
    assert not maintenance.is_due(context, NOW + timedelta(hours=23))
    assert maintenance.is_due(context, NOW + timedelta(hours=24))
