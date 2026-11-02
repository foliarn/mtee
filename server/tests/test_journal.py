from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from mtee_remote import clock, journal
from mtee_remote.db import Database
from mtee_remote.journal import ChangeNotifier


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db", tmp_path / "backups")
    database.migrate()
    now = clock.to_iso(clock.utc_now())
    with database.transaction() as tx:
        for user_id, name in (("u1", "alice"), ("u2", "bob")):
            tx.conn.execute(
                "INSERT INTO users VALUES (?,?,'!',0,0,NULL,?,?)", (user_id, name, name, now)
            )
    return database


def test_seq_increments_per_user_independently(db: Database) -> None:
    with db.transaction() as tx:
        assert journal.append(tx, "u1", "added", "i1", {"path": "a"}) == 1
        assert journal.append(tx, "u1", "moved", "i1", {"to": "b"}) == 2
        assert journal.append(tx, "u2", "added", "i9", {}) == 1
    with db.transaction() as tx:
        assert journal.append(tx, "u1", "trashed", "i1", {}) == 3
        assert journal.append(tx, "u2", "restored", None, {}) == 2
    rows = (
        db.conn()
        .execute(
            "SELECT seq, kind, item_id, payload_json, at_utc FROM journal WHERE user_id = 'u1'"
            " ORDER BY seq"
        )
        .fetchall()
    )
    assert [r["seq"] for r in rows] == [1, 2, 3]
    assert [r["kind"] for r in rows] == ["added", "moved", "trashed"]
    assert json.loads(rows[0]["payload_json"]) == {"path": "a"}
    assert rows[0]["at_utc"].endswith("Z")


def test_notify_users_is_filled(db: Database) -> None:
    with db.transaction() as tx:
        assert tx.notify_users == set()
        journal.append(tx, "u1", "added", None, {})
        journal.append(tx, "u2", "added", None, {})
        journal.append(tx, "u1", "added", None, {})
        assert tx.notify_users == {"u1", "u2"}


def test_unknown_kind_is_refused(db: Database) -> None:
    with db.transaction() as tx, pytest.raises(ValueError):
        journal.append(tx, "u1", "exploded", None, {})


def test_all_documented_kinds_are_accepted(db: Database) -> None:
    kinds = [
        "added",
        "replaced",
        "moved",
        "trashed",
        "restored",
        "metadata",
        "purged",
        "backup_added",
        "backup_trashed",
    ]
    with db.transaction() as tx:
        for kind in kinds:
            journal.append(tx, "u1", kind, None, {})


def test_rolled_back_append_leaves_no_trace(db: Database) -> None:
    seen: list[set[str]] = []
    db.on_commit = seen.append
    with pytest.raises(RuntimeError), db.transaction() as tx:
        journal.append(tx, "u1", "added", None, {})
        raise RuntimeError("boom")
    assert db.conn().execute("SELECT COUNT(*) FROM journal").fetchone()[0] == 0
    assert seen == []
    with db.transaction() as tx:
        assert journal.append(tx, "u1", "added", None, {}) == 1
    assert seen == [{"u1"}]


def test_commit_wakes_a_waiter_end_to_end(db: Database) -> None:
    async def scenario() -> bool:
        notifier = ChangeNotifier()
        notifier.attach_loop(asyncio.get_running_loop())
        db.on_commit = notifier.notify

        def write() -> None:
            with db.transaction() as tx:
                journal.append(tx, "u1", "added", None, {})

        waiter = asyncio.create_task(notifier.wait("u1", 5))
        await asyncio.sleep(0.05)
        threading.Thread(target=write).start()
        return await waiter

    assert asyncio.run(scenario()) is True


def test_notify_before_a_loop_is_attached_is_a_no_op() -> None:
    ChangeNotifier().notify({"u1"})


def test_wait_wakes_on_notify_from_another_thread() -> None:
    async def scenario() -> list[bool]:
        notifier = ChangeNotifier()
        notifier.attach_loop(asyncio.get_running_loop())
        waiters = [asyncio.create_task(notifier.wait("u1", 5)) for _ in range(3)]
        other = asyncio.create_task(notifier.wait("u2", 0.3))
        await asyncio.sleep(0.05)
        thread = threading.Thread(target=notifier.notify, args=({"u1"},))
        thread.start()
        results = [await w for w in waiters]
        results.append(await other)
        thread.join()
        return results

    assert asyncio.run(scenario()) == [True, True, True, False]


def test_wait_times_out() -> None:
    async def scenario() -> tuple[bool, dict[str, object]]:
        notifier = ChangeNotifier()
        notifier.attach_loop(asyncio.get_running_loop())
        result = await notifier.wait("u1", 0.1)
        return result, dict(notifier._waiters)  # pyright: ignore[reportPrivateUsage]

    result, leftovers = asyncio.run(scenario())
    assert result is False
    assert leftovers == {}


def test_notification_before_wait_is_not_remembered() -> None:
    async def scenario() -> bool:
        notifier = ChangeNotifier()
        notifier.attach_loop(asyncio.get_running_loop())
        notifier.notify({"u1"})
        await asyncio.sleep(0.05)
        return await notifier.wait("u1", 0.1)

    assert asyncio.run(scenario()) is False
