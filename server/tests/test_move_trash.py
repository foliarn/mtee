"""Moving, trashing and restoring items, the purge, and `place_file` (milestone 124.5)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from conftest import MakeDevice, MakeUser
from mtee_remote import uploads
from mtee_remote.errors import ApiError
from mtee_remote.library import scanner, store
from test_uploads import Env, blob, build_env, error_code, sha, snapshot_tree
from test_uploads import env as env
from test_uploads import other as other


def move(env: Env, item_id: str, relative_path: str) -> Any:
    return env.client.post(
        f"/api/v1/items/{item_id}/move", json={"relative_path": relative_path}, headers=env.headers
    )


def trash(env: Env, item_id: str) -> Any:
    return env.client.post(f"/api/v1/items/{item_id}/trash", headers=env.headers)


def restore(env: Env, trash_id: str, relative_path: str | None = None) -> Any:
    body = None if relative_path is None else {"relative_path": relative_path}
    return env.client.post(f"/api/v1/trash/{trash_id}/restore", json=body, headers=env.headers)


def purge(env: Env, trash_id: str, query: str = "?confirm=yes") -> Any:
    return env.client.delete(f"/api/v1/trash/{trash_id}{query}", headers=env.headers)


@pytest.fixture
def admin_env(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> Env:
    return build_env(client, app, make_user, make_device, "boss", is_admin=True)


def boom(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("database failure")


# -- place_file ---------------------------------------------------------------------


def test_place_file_moves_and_never_overwrites(tmp_path: Path) -> None:
    src, dst = tmp_path / "src.bin", tmp_path / "dst.bin"
    src.write_bytes(b"new")
    uploads.place_file(src, dst)
    assert (src.exists(), dst.read_bytes()) == (False, b"new")
    src.write_bytes(b"other")
    with pytest.raises(ApiError) as caught:
        uploads.place_file(src, dst)
    assert caught.value.code == "path_taken"
    assert (src.read_bytes(), dst.read_bytes()) == (b"other", b"new")


def test_place_file_falls_back_to_rename_and_still_never_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_links(*args: Any, **kwargs: Any) -> None:
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    src, dst = tmp_path / "src.bin", tmp_path / "dst.bin"
    src.write_bytes(b"new")
    uploads.place_file(src, dst)
    assert (src.exists(), dst.read_bytes()) == (False, b"new")
    src.write_bytes(b"other")
    with pytest.raises(ApiError) as caught:
        uploads.place_file(src, dst)
    assert caught.value.code == "path_taken"
    assert (src.read_bytes(), dst.read_bytes()) == (b"other", b"new")


def test_place_file_with_a_missing_source_changes_nothing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        uploads.place_file(tmp_path / "missing.bin", tmp_path / "dst.bin")
    assert not (tmp_path / "dst.bin").exists()


def test_place_file_removes_its_new_link_when_the_source_cannot_be_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src, dst = tmp_path / "src.bin", tmp_path / "dst.bin"
    src.write_bytes(b"data")
    real_unlink = os.unlink

    def selective(path: Any, *args: Any, **kwargs: Any) -> None:
        if Path(path) == src:
            raise PermissionError(13, "denied")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", selective)
    with pytest.raises(PermissionError):
        uploads.place_file(src, dst)
    monkeypatch.undo()
    assert (src.read_bytes(), dst.exists()) == (b"data", False)


# -- move ---------------------------------------------------------------------------


def test_move_changes_the_path_the_file_and_the_journal(env: Env) -> None:
    data = blob(500)
    item = env.upload("old/a.flac", data)
    response = move(env, item["item_id"], "new/deep/b.flac")
    assert response.status_code == 200
    moved = response.json()["item"]
    assert (moved["item_id"], moved["relative_path"], moved["revision"]) == (
        item["item_id"],
        "new/deep/b.flac",
        1,
    )
    assert (env.folder / "new" / "deep" / "b.flac").read_bytes() == data
    assert not (env.folder / "old" / "a.flac").exists()
    assert (env.folder / "old").is_dir()  # empty source folders are left as they are
    assert env.kinds() == ["added", "moved"]
    assert env.payloads("moved") == [{"from": "old/a.flac", "to": "new/deep/b.flac"}]
    stored = env.client.get(f"/api/v1/items/{item['item_id']}", headers=env.headers).json()
    assert stored["relative_path"] == "new/deep/b.flac"
    # the old path is free again, and a scan agrees with the database
    assert env.create("old/a.flac", data).status_code == 201
    result = scanner.scan_root(env.app.state.db, env.app.state.settings, env.root_id)
    assert result == scanner.ScanResult(unchanged=1)


def test_move_to_the_same_path_changes_nothing(env: Env) -> None:
    item = env.upload("a.flac", blob(50))
    response = move(env, item["item_id"], "a.flac")
    assert response.status_code == 200
    assert env.kinds() == ["added"]


def test_move_never_overwrites(env: Env) -> None:
    one, two = blob(50, "1"), blob(60, "2")
    item_one = env.upload("one.flac", one)
    env.upload("two.flac", two)
    taken = move(env, item_one["item_id"], "two.flac")
    assert (taken.status_code, error_code(taken)) == (409, "path_taken")
    (env.folder / "by-hand.flac").write_bytes(b"hand")
    taken = move(env, item_one["item_id"], "by-hand.flac")
    assert (taken.status_code, error_code(taken)) == (409, "path_taken")
    (env.folder / "dir.flac").mkdir()
    assert move(env, item_one["item_id"], "dir.flac").status_code == 409
    assert (env.folder / "one.flac").read_bytes() == one
    assert (env.folder / "two.flac").read_bytes() == two
    assert (env.folder / "by-hand.flac").read_bytes() == b"hand"
    assert env.kinds() == ["added", "added"]


@pytest.mark.parametrize(
    "path",
    [
        "../evil.flac",
        "a/../../evil.flac",
        "/etc/evil.flac",
        "a\\evil.flac",
        "C:/evil.flac",
        "\uff0e\uff0e/evil.flac",
        ".mtee-trash/evil.flac",
        "evil.txt",
        "",
    ],
)
def test_move_refuses_bad_paths(env: Env, tmp_path: Path, path: str) -> None:
    item = env.upload("a.flac", blob(50))
    before = snapshot_tree(tmp_path)
    response = move(env, item["item_id"], path)
    assert (response.status_code, error_code(response)) == (400, "bad_request")
    assert snapshot_tree(tmp_path) == before
    assert env.kinds() == ["added"]


def test_move_of_a_missing_file_is_a_conflict(env: Env) -> None:
    item = env.upload("a.flac", blob(50))
    (env.folder / "a.flac").unlink()
    response = move(env, item["item_id"], "b.flac")
    assert (response.status_code, error_code(response)) == (409, "conflict")


def test_move_undoes_the_file_when_the_database_step_fails(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = env.upload("a.flac", blob(50))
    monkeypatch.setattr(store, "move_item", boom)
    with pytest.raises(RuntimeError):
        move(env, item["item_id"], "b.flac")
    monkeypatch.undo()
    assert (env.folder / "a.flac").is_file() and not (env.folder / "b.flac").exists()


def test_move_and_trash_are_closed_to_other_users(env: Env, other: Env) -> None:
    item = env.upload("a.flac", blob(50))
    assert move(other, item["item_id"], "b.flac").status_code == 404
    assert trash(other, item["item_id"]).status_code == 404
    assert move(other, "0" * 32, "b.flac").status_code == 404
    assert (env.folder / "a.flac").is_file()
    assert env.client.post(f"/api/v1/items/{item['item_id']}/move", json={}).status_code == 401


# -- trash and restore --------------------------------------------------------------


def test_trash_moves_the_file_into_the_library_trash_folder(env: Env) -> None:
    data = blob(700)
    item = env.upload("rock/a.flac", data)
    response = trash(env, item["item_id"])
    assert response.status_code == 200
    trash_id = response.json()["trash_id"]
    assert not (env.folder / "rock" / "a.flac").exists()
    assert (env.library / ".mtee-trash" / trash_id / "a.flac").read_bytes() == data
    row = env.app.state.db.conn().execute("SELECT * FROM trash").fetchone()
    assert row["stored_path"] == f".mtee-trash/{trash_id}/a.flac"
    assert (row["kind"], row["item_id"], row["size_bytes"]) == ("item", item["item_id"], 700)
    assert env.client.get("/api/v1/items", headers=env.headers).json()["items"] == []
    gone = env.client.get(f"/api/v1/items/{item['item_id']}", headers=env.headers)
    assert gone.status_code == 404
    assert env.kinds() == ["added", "trashed"]
    assert env.payloads("trashed") == [{"relative_path": "rock/a.flac"}]
    entries = env.trash_entries()
    assert entries == [
        {
            "trash_id": trash_id,
            "kind": "item",
            "item_id": item["item_id"],
            "original_root_id": env.root_id,
            "original_relative_path": "rock/a.flac",
            "size_bytes": 700,
            "trashed_at_utc": entries[0]["trashed_at_utc"],
        }
    ]
    # trashing twice is refused, the path is free for a new file and a scan sees no change
    assert trash(env, item["item_id"]).status_code == 404
    env.upload("rock/a.flac", blob(10, "again"))
    result = scanner.scan_root(env.app.state.db, env.app.state.settings, env.root_id)
    assert result == scanner.ScanResult(unchanged=1)


def test_trash_list_is_newest_first_and_private(env: Env, other: Env) -> None:
    first = env.upload("a.flac", blob(10, "1"))
    second = env.upload("b.flac", blob(10, "2"))
    first_id = trash(env, first["item_id"]).json()["trash_id"]
    second_id = trash(env, second["item_id"]).json()["trash_id"]
    assert [e["trash_id"] for e in env.trash_entries()] == [second_id, first_id]
    assert other.trash_entries() == []
    assert restore(other, first_id).status_code == 404
    assert other.client.get("/api/v1/trash").status_code == 401


def test_trash_undoes_the_file_when_the_database_step_fails(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = env.upload("a.flac", blob(100))
    monkeypatch.setattr(store, "mark_trashed", boom)
    with pytest.raises(RuntimeError):
        trash(env, item["item_id"])
    monkeypatch.undo()
    assert (env.folder / "a.flac").is_file()
    assert env.trash_entries() == []
    assert not list((env.library / ".mtee-trash").glob("*/*"))


def test_restore_puts_the_item_back_at_its_old_path(env: Env) -> None:
    data = blob(400)
    item = env.upload("rock/a.flac", data)
    trash_id = trash(env, item["item_id"]).json()["trash_id"]
    response = restore(env, trash_id)
    assert response.status_code == 200
    back = response.json()["item"]
    assert (back["item_id"], back["relative_path"], back["revision"]) == (
        item["item_id"],
        "rock/a.flac",
        1,
    )
    assert (env.folder / "rock" / "a.flac").read_bytes() == data
    assert env.trash_entries() == []
    assert not (env.library / ".mtee-trash" / trash_id).exists()
    assert env.kinds() == ["added", "trashed", "restored"]
    downloaded = env.client.get(f"/api/v1/items/{item['item_id']}/file", headers=env.headers)
    assert downloaded.content == data
    # a restore of an entry that is gone
    assert restore(env, trash_id).status_code == 404


def test_restore_to_another_path(env: Env) -> None:
    item = env.upload("a.flac", blob(100))
    trash_id = trash(env, item["item_id"]).json()["trash_id"]
    response = restore(env, trash_id, "other/place.flac")
    assert response.status_code == 200
    assert response.json()["item"]["relative_path"] == "other/place.flac"
    assert response.json()["item"]["item_id"] == item["item_id"]
    assert (env.folder / "other" / "place.flac").is_file()
    assert env.payloads("restored") == [{"relative_path": "other/place.flac"}]


def test_restore_never_overwrites(env: Env) -> None:
    old = blob(100, "old")
    item = env.upload("a.flac", old)
    trash_id = trash(env, item["item_id"]).json()["trash_id"]
    env.upload("a.flac", blob(100, "new"))  # the path was reused
    taken = restore(env, trash_id)
    assert (taken.status_code, error_code(taken)) == (409, "path_taken")
    (env.folder / "by-hand.flac").write_bytes(b"hand")
    assert restore(env, trash_id, "by-hand.flac").status_code == 409
    assert (env.folder / "a.flac").read_bytes() == blob(100, "new")
    assert (env.folder / "by-hand.flac").read_bytes() == b"hand"
    assert len(env.trash_entries()) == 1
    assert restore(env, trash_id, "free.flac").status_code == 200
    assert (env.folder / "free.flac").read_bytes() == old


@pytest.mark.parametrize(
    "path",
    ["../evil.flac", "/etc/evil.flac", "a\\evil.flac", "C:/evil.flac", "\uff0e\uff0e/evil.flac"],
)
def test_restore_refuses_bad_paths(env: Env, tmp_path: Path, path: str) -> None:
    item = env.upload("a.flac", blob(100))
    trash_id = trash(env, item["item_id"]).json()["trash_id"]
    before = snapshot_tree(tmp_path)
    response = restore(env, trash_id, path)
    assert (response.status_code, error_code(response)) == (400, "bad_request")
    assert snapshot_tree(tmp_path) == before
    assert len(env.trash_entries()) == 1


def test_restore_of_an_older_version_becomes_a_new_item(env: Env) -> None:
    old, new = blob(100, "old"), blob(120, "new")
    item = env.upload("a.flac", old)
    env.upload("a.flac", new, base_item_id=item["item_id"], base_revision=1)
    entry = env.trash_entries()[0]
    # the path is in use by the current version
    assert restore(env, entry["trash_id"]).status_code == 409
    response = restore(env, entry["trash_id"], "a (old version).flac")
    assert response.status_code == 200
    restored = response.json()["item"]
    assert restored["item_id"] != item["item_id"]
    assert (restored["revision"], restored["relative_path"]) == (1, "a (old version).flac")
    assert (env.folder / "a (old version).flac").read_bytes() == old
    assert (env.folder / "a.flac").read_bytes() == new
    assert env.kinds() == ["added", "replaced", "added"]
    assert env.trash_entries() == []


def test_an_older_version_and_the_trashed_item_are_told_apart(env: Env) -> None:
    old, new = blob(100, "old"), blob(120, "new")
    item = env.upload("a.flac", old)
    env.upload("a.flac", new, base_item_id=item["item_id"], base_revision=1)
    older_id = env.trash_entries()[0]["trash_id"]
    current_id = trash(env, item["item_id"]).json()["trash_id"]
    # restoring the older version while the item is in the trash makes a NEW item
    first = restore(env, older_id)
    assert first.status_code == 200
    assert first.json()["item"]["item_id"] != item["item_id"]
    assert (env.folder / "a.flac").read_bytes() == old
    # the trashed item's own file comes back as the item itself, at another path
    second = restore(env, current_id, "a (current).flac")
    assert second.status_code == 200
    assert second.json()["item"]["item_id"] == item["item_id"]
    assert second.json()["item"]["revision"] == 2
    assert (env.folder / "a (current).flac").read_bytes() == new


def test_a_failed_database_step_leaves_the_file_in_the_trash(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = env.upload("a.flac", blob(100))
    trash_id = trash(env, item["item_id"]).json()["trash_id"]
    monkeypatch.setattr(store, "mark_restored", boom)
    with pytest.raises(RuntimeError):
        restore(env, trash_id)
    monkeypatch.undo()
    assert not (env.folder / "a.flac").exists()
    assert (env.library / ".mtee-trash" / trash_id / "a.flac").is_file()
    assert restore(env, trash_id).status_code == 200


def test_the_trash_counts_against_the_quota(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    env = build_env(client, app, make_user, make_device, "carol", quota_bytes=1000)
    item = env.upload("a.flac", blob(800, "1"))
    trash(env, item["item_id"])
    response = env.create("b.flac", blob(400, "2"))
    assert (response.status_code, error_code(response)) == (413, "quota_exceeded")


# -- purge --------------------------------------------------------------------------


def test_purge_is_for_administrators_with_a_confirmation(
    env: Env,
    admin_env: Env,
) -> None:
    item = env.upload("a.flac", blob(100))
    trash_id = trash(env, item["item_id"]).json()["trash_id"]
    refused = purge(env, trash_id)
    assert (refused.status_code, error_code(refused)) == (403, "forbidden")
    assert env.client.delete(f"/api/v1/trash/{trash_id}?confirm=yes").status_code == 401
    assert (env.library / ".mtee-trash" / trash_id / "a.flac").is_file()

    own = admin_env.upload("x.flac", blob(100, "x"))
    own_trash = trash(admin_env, own["item_id"]).json()["trash_id"]
    for query in ("", "?confirm=no", "?confirm=", "?confirm=YES"):
        response = purge(admin_env, own_trash, query)
        assert (response.status_code, error_code(response)) == (400, "bad_request"), query
    assert len(admin_env.trash_entries()) == 1
    # an administrator cannot reach another user's trash entry
    assert purge(admin_env, trash_id).status_code == 404
    assert (env.library / ".mtee-trash" / trash_id / "a.flac").is_file()


def test_purge_of_a_trashed_item_removes_file_row_and_item(admin_env: Env) -> None:
    item = admin_env.upload("a.flac", blob(100))
    trash_id = trash(admin_env, item["item_id"]).json()["trash_id"]
    response = purge(admin_env, trash_id)
    assert response.status_code == 204
    assert not (admin_env.library / ".mtee-trash" / trash_id).exists()
    assert admin_env.trash_entries() == []
    conn = admin_env.app.state.db.conn()
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
    assert admin_env.kinds() == ["added", "trashed", "purged"]
    assert admin_env.payloads("purged") == [{"relative_path": "a.flac", "reason": "purged"}]
    assert purge(admin_env, trash_id).status_code == 404


def test_purge_of_an_older_version_keeps_the_item(admin_env: Env) -> None:
    item = admin_env.upload("a.flac", blob(100, "old"))
    admin_env.upload("a.flac", blob(100, "new"), base_item_id=item["item_id"], base_revision=1)
    trash_id = admin_env.trash_entries()[0]["trash_id"]
    assert purge(admin_env, trash_id).status_code == 204
    assert admin_env.trash_entries() == []
    still = admin_env.client.get(f"/api/v1/items/{item['item_id']}", headers=admin_env.headers)
    assert still.status_code == 200
    assert (admin_env.folder / "a.flac").read_bytes() == blob(100, "new")
    assert admin_env.kinds() == ["added", "replaced"]


def test_purge_does_not_touch_a_hard_linked_copy(admin_env: Env) -> None:
    data = blob(1000, "same")
    one = admin_env.upload("one.flac", data)
    admin_env.upload("two.flac", data)  # hard link
    trash_id = trash(admin_env, one["item_id"]).json()["trash_id"]
    purge(admin_env, trash_id)
    assert (admin_env.folder / "two.flac").read_bytes() == data


# -- everything together ------------------------------------------------------------


def test_the_journal_kinds_after_each_operation(env: Env) -> None:
    item = env.upload("a.flac", blob(100, "1"))
    env.upload("a.flac", blob(100, "2"), base_item_id=item["item_id"], base_revision=1)
    move(env, item["item_id"], "b.flac")
    trash_id = trash(env, item["item_id"]).json()["trash_id"]
    restore(env, trash_id)
    assert env.kinds() == ["added", "replaced", "moved", "trashed", "restored"]
    since = env.client.get("/api/v1/changes?since=0", headers=env.headers).json()
    kinds = [c["kind"] for c in since["changes"] if c["kind"] != "metadata"]
    assert kinds == env.kinds()


def test_the_file_is_byte_identical_after_move_trash_and_restore(env: Env) -> None:
    data = blob(5000, "round trip")
    item = env.upload("a.flac", data)
    move(env, item["item_id"], "x/b.flac")
    trash_id = trash(env, item["item_id"]).json()["trash_id"]
    restore(env, trash_id, "y/c.flac")
    assert sha((env.folder / "y" / "c.flac").read_bytes()) == sha(data)
