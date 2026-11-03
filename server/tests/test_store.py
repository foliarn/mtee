"""The item store: revisions, hashes, moves, trash state and the journal entries they write."""

from __future__ import annotations

import json
from typing import Any

import pytest
from starlette.applications import Starlette

from conftest import MakeUser
from mtee_remote import clock
from mtee_remote.db import Database
from mtee_remote.errors import ApiError
from mtee_remote.ids import new_id
from mtee_remote.library import store

FACTS: dict[str, Any] = {"size_bytes": 10, "mtime_ns": 1, "inode": 7}


class Env:
    def __init__(self, app: Starlette, make_user: MakeUser) -> None:
        self.app = app
        self.db: Database = app.state.db
        self.user = make_user(app)
        self.user_id: str = self.user["user_id"]
        self.root_id = new_id()
        with self.db.transaction() as tx:
            tx.conn.execute(
                "INSERT INTO roots(root_id, user_id, name, relative_dir, adopted, created_at_utc)"
                " VALUES (?,?,?,?,0,?)",
                (self.root_id, self.user_id, "music", "music", clock.to_iso(clock.utc_now())),
            )

    def insert(self, path: str = "a.flac", **extra: Any) -> str:
        with self.db.transaction() as tx:
            return store.insert_item(
                tx,
                user_id=self.user_id,
                root_id=self.root_id,
                relative_path=path,
                **{**FACTS, **extra},
            )

    def journal(self) -> list[tuple[str, dict[str, Any]]]:
        rows = self.db.conn().execute(
            "SELECT kind, payload_json FROM journal WHERE user_id = ? ORDER BY seq",
            (self.user_id,),
        )
        return [(row["kind"], json.loads(row["payload_json"])) for row in rows]

    def item(self, item_id: str) -> Any:
        return (
            self.db.conn().execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
        )


@pytest.fixture
def env(app: Starlette, make_user: MakeUser) -> Env:
    return Env(app, make_user)


def test_insert_item_starts_pending_at_revision_1(env: Env) -> None:
    item_id = env.insert("rock/a.flac", sha256="ab" * 32)
    row = env.item(item_id)
    assert row["revision"] == 1
    assert row["hash_state"] == "pending"
    assert row["state"] == "present"
    assert row["sha256"] == "ab" * 32
    revision = (
        env.db.conn()
        .execute(
            "SELECT revision, sha256, size_bytes, device_id FROM item_revisions WHERE item_id = ?",
            (item_id,),
        )
        .fetchone()
    )
    assert tuple(revision) == (1, "ab" * 32, 10, None)
    assert env.journal() == [
        (
            "added",
            {
                "root_id": env.root_id,
                "relative_path": "rock/a.flac",
                "size_bytes": 10,
                "revision": 1,
            },
        )
    ]


def test_insert_item_refuses_a_second_present_item_at_the_same_path(env: Env) -> None:
    env.insert("a.flac")
    with pytest.raises(Exception, match="UNIQUE"):
        env.insert("a.flac")


def test_replace_item_file_bumps_the_revision_and_clears_hashes(env: Env) -> None:
    item_id = env.insert()
    with env.db.transaction() as tx:
        assert store.set_hashes(
            tx, item_id, 1, sha256="aa", audio_hash="bb", metadata_json="{}", duration_us=5, ok=True
        )
    with env.db.transaction() as tx:
        revision = store.replace_item_file(
            tx, item_id, size_bytes=20, mtime_ns=2, inode=8, device_id="dev"
        )
    assert revision == 2
    row = env.item(item_id)
    assert (row["revision"], row["size_bytes"], row["mtime_ns"], row["inode"]) == (2, 20, 2, 8)
    assert row["hash_state"] == "pending"
    assert row["sha256"] is None
    assert row["audio_hash"] is None
    assert row["metadata_json"] is None
    assert row["duration_us"] is None
    revisions = (
        env.db.conn()
        .execute(
            "SELECT revision, device_id FROM item_revisions WHERE item_id = ? ORDER BY revision",
            (item_id,),
        )
        .fetchall()
    )
    assert [tuple(r) for r in revisions] == [(1, None), (2, "dev")]
    assert env.journal()[-1] == (
        "replaced",
        {"root_id": env.root_id, "relative_path": "a.flac", "size_bytes": 20, "revision": 2},
    )
    with env.db.transaction() as tx:
        assert store.replace_item_file(tx, item_id, sha256="cc", **FACTS) == 3
    assert env.item(item_id)["sha256"] == "cc"


def test_set_hashes_done_and_error(env: Env) -> None:
    first = env.insert("a.flac")
    second = env.insert("b.flac")
    with env.db.transaction() as tx:
        assert store.set_hashes(
            tx,
            first,
            1,
            sha256="s1",
            audio_hash="h1",
            metadata_json='{"title": ["x"]}',
            duration_us=1_000_000,
            ok=True,
        )
        assert store.set_hashes(
            tx,
            second,
            1,
            sha256=None,
            audio_hash=None,
            metadata_json=None,
            duration_us=None,
            ok=False,
        )
    row = env.item(first)
    assert (row["hash_state"], row["sha256"], row["audio_hash"], row["duration_us"]) == (
        "done",
        "s1",
        "h1",
        1_000_000,
    )
    assert env.item(second)["hash_state"] == "error"
    sha = (
        env.db.conn()
        .execute("SELECT sha256 FROM item_revisions WHERE item_id = ? AND revision = 1", (first,))
        .fetchone()[0]
    )
    assert sha == "s1"
    assert ("metadata", {"revision": 1, "sha256": "s1", "audio_hash": "h1"}) in env.journal()


def test_set_hashes_is_refused_after_the_file_was_replaced(env: Env) -> None:
    item_id = env.insert()
    with env.db.transaction() as tx:
        store.replace_item_file(tx, item_id, **FACTS)
    before = len(env.journal())
    with env.db.transaction() as tx:
        applied = store.set_hashes(
            tx,
            item_id,
            1,
            sha256="old",
            audio_hash="old",
            metadata_json="{}",
            duration_us=1,
            ok=True,
        )
    assert applied is False
    row = env.item(item_id)
    assert row["hash_state"] == "pending"
    assert row["sha256"] is None
    assert len(env.journal()) == before
    with env.db.transaction() as tx:
        assert not store.set_hashes(
            tx,
            "missing",
            1,
            sha256="x",
            audio_hash=None,
            metadata_json=None,
            duration_us=None,
            ok=True,
        )


def test_move_item_changes_the_path_only(env: Env) -> None:
    item_id = env.insert("a.flac")
    other = env.insert("b.flac")
    with env.db.transaction() as tx:
        store.move_item(tx, item_id, "sub/c.flac")
    row = env.item(item_id)
    assert (row["relative_path"], row["revision"]) == ("sub/c.flac", 1)
    assert env.journal()[-1] == ("moved", {"from": "a.flac", "to": "sub/c.flac"})
    with pytest.raises(ApiError) as caught, env.db.transaction() as tx:
        store.move_item(tx, other, "sub/c.flac")
    assert caught.value.code == "path_taken"
    assert caught.value.status == 409
    assert env.item(other)["relative_path"] == "b.flac"


def test_trash_frees_the_path_and_restore_checks_it(env: Env) -> None:
    item_id = env.insert("a.flac")
    with env.db.transaction() as tx:
        store.mark_trashed(tx, item_id)
    assert env.item(item_id)["state"] == "trashed"
    assert env.journal()[-1] == ("trashed", {"relative_path": "a.flac"})
    replacement = env.insert("a.flac")  # the path is free again
    with pytest.raises(ApiError) as caught, env.db.transaction() as tx:
        store.mark_restored(tx, item_id, "a.flac")
    assert caught.value.code == "path_taken"
    with env.db.transaction() as tx:
        store.mark_restored(tx, item_id, "restored/a.flac")
    row = env.item(item_id)
    assert (row["state"], row["relative_path"]) == ("present", "restored/a.flac")
    assert env.journal()[-1] == ("restored", {"relative_path": "restored/a.flac"})
    assert env.item(replacement)["state"] == "present"


def test_remove_missing_deletes_the_row_and_its_revisions(env: Env) -> None:
    item_id = env.insert("a.flac")
    with env.db.transaction() as tx:
        store.remove_missing(tx, item_id)
    assert env.item(item_id) is None
    count = (
        env.db.conn()
        .execute("SELECT COUNT(*) FROM item_revisions WHERE item_id = ?", (item_id,))
        .fetchone()[0]
    )
    assert count == 0
    assert env.journal()[-1] == ("purged", {"relative_path": "a.flac", "reason": "missing"})


def test_unknown_item_is_not_found(env: Env) -> None:
    with pytest.raises(ApiError) as caught, env.db.transaction() as tx:
        store.mark_trashed(tx, "nope")
    assert caught.value.code == "not_found"


def test_item_public_has_the_documented_fields(env: Env) -> None:
    item_id = env.insert("a.flac")
    with env.db.transaction() as tx:
        store.set_hashes(
            tx,
            item_id,
            1,
            sha256="s",
            audio_hash="h",
            metadata_json='{"title": ["T"]}',
            duration_us=3,
            ok=True,
        )
    row = (
        env.db.conn()
        .execute(f"SELECT {store.ITEM_COLUMNS} FROM items WHERE item_id = ?", (item_id,))
        .fetchone()
    )
    public = store.item_public(row)
    assert set(public) == {
        "item_id",
        "root_id",
        "relative_path",
        "size_bytes",
        "sha256",
        "audio_hash",
        "hash_state",
        "revision",
        "metadata",
        "duration_us",
        "updated_at_utc",
        "loudness",
    }
    assert public["loudness"] is None
    assert public["metadata"] == {"title": ["T"]}
    assert public["hash_state"] == "done"
    pending = env.insert("b.flac")
    row = (
        env.db.conn()
        .execute(f"SELECT {store.ITEM_COLUMNS} FROM items WHERE item_id = ?", (pending,))
        .fetchone()
    )
    assert store.item_public(row)["metadata"] is None


def test_root_lock_is_one_lock_per_root() -> None:
    assert store.root_lock("r1") is store.root_lock("r1")
    assert store.root_lock("r1") is not store.root_lock("r2")


def test_root_path_joins_the_library_dir(env: Env) -> None:
    settings = env.app.state.settings
    conn = env.db.conn()
    assert store.root_path(settings, conn, env.root_id) == settings.music_dir / "alice" / "music"
    whole = new_id()
    with env.db.transaction() as tx:
        tx.conn.execute(
            "INSERT INTO roots(root_id, user_id, name, relative_dir, adopted, created_at_utc)"
            " VALUES (?,?,?,?,1,?)",
            (whole, env.user_id, "all", "", clock.to_iso(clock.utc_now())),
        )
    assert store.root_path(settings, conn, whole) == settings.music_dir / "alice"
    with pytest.raises(ApiError):
        store.root_path(settings, conn, "unknown")


def test_user_library_dir_and_overlap_rule(env: Env) -> None:
    settings = env.app.state.settings
    assert store.user_library_dir(settings, "bob") == settings.music_dir / "bob"
    assert store.roots_overlap("", "x")
    assert store.roots_overlap("a/b", "a")
    assert store.roots_overlap("A", "a")
    assert not store.roots_overlap("a", "ab")
    assert ".flac" in store.AUDIO_EXTENSIONS
