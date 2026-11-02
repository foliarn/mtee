"""Resumable uploads: create, chunks, commit, replacement, quota, hard links (milestone 124.5)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from conftest import MakeDevice, MakeUser
from helpers import make_audio
from mtee_remote import uploads
from mtee_remote.library import scanner, store
from test_roots_items import absolute_path_leaks
from test_scanner import add_root


def blob(size: int, seed: str = "a") -> bytes:
    """Deterministic pseudo-random bytes; a different seed gives different content."""
    unit = hashlib.sha256(seed.encode()).digest()
    return (unit * (size // len(unit) + 1))[:size]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Env:
    """One user with one device and one root (`lib`), plus the helpers the tests share."""

    client: TestClient
    app: Starlette
    user_id: str
    headers: dict[str, str]
    root_id: str
    folder: Path  # the root's folder
    library: Path  # the user's library folder

    def create(
        self,
        relative_path: str,
        data: bytes,
        *,
        sha256: str | None = None,
        **extra: Any,
    ) -> Any:
        body = {
            "purpose": "item",
            "root_id": self.root_id,
            "relative_path": relative_path,
            "size_bytes": len(data),
            "sha256": sha256 or sha(data),
            **extra,
        }
        return self.client.post("/api/v1/uploads", json=body, headers=self.headers)

    def put(self, upload_id: str, data: bytes, start: int, total: int) -> Any:
        end = start + len(data) - 1
        return self.client.put(
            f"/api/v1/uploads/{upload_id}",
            content=data,
            headers={**self.headers, "Content-Range": f"bytes {start}-{end}/{total}"},
        )

    def commit(self, upload_id: str, **body: Any) -> Any:
        return self.client.post(
            f"/api/v1/uploads/{upload_id}/commit", json=body or None, headers=self.headers
        )

    def status(self, upload_id: str) -> dict[str, Any]:
        response = self.client.get(f"/api/v1/uploads/{upload_id}", headers=self.headers)
        assert response.status_code == 200
        return response.json()

    def upload(self, relative_path: str, data: bytes, **extra: Any) -> dict[str, Any]:
        """Create, send in one chunk and commit; return the item."""
        created = self.create(relative_path, data, **extra)
        assert created.status_code == 201, created.text
        upload_id = created.json()["upload_id"]
        if data:
            assert self.put(upload_id, data, 0, len(data)).status_code == 200
        committed = self.commit(upload_id)
        assert committed.status_code == 200, committed.text
        item: dict[str, Any] = committed.json()["item"]
        return item

    def trash_entries(self) -> list[dict[str, Any]]:
        response = self.client.get("/api/v1/trash", headers=self.headers)
        assert response.status_code == 200
        entries: list[dict[str, Any]] = response.json()["trash"]
        return entries

    def kinds(self) -> list[str]:
        """Journal kinds in order, without `metadata` (the hash thread adds those at any time)."""
        rows = self.app.state.db.conn().execute(
            "SELECT kind FROM journal WHERE user_id = ? AND kind != 'metadata' ORDER BY seq",
            (self.user_id,),
        )
        return [row["kind"] for row in rows]

    def payloads(self, kind: str) -> list[dict[str, Any]]:
        rows = self.app.state.db.conn().execute(
            "SELECT payload_json FROM journal WHERE user_id = ? AND kind = ? ORDER BY seq",
            (self.user_id, kind),
        )
        return [json.loads(row["payload_json"]) for row in rows]


def stop_background_threads(app: Starlette) -> None:
    """Stop the scan and hash threads so the tests are deterministic.

    A running hash thread adds `metadata` journal rows at any moment and, on Windows, keeps a
    file open while it hashes it, which makes a concurrent move fail. Hashing is tested by
    calling `scanner.hash_pending` directly.
    """
    app.state.library.stop()


def build_env(
    client: TestClient,
    app: Starlette,
    make_user: MakeUser,
    make_device: MakeDevice,
    username: str,
    **user_options: Any,
) -> Env:
    stop_background_threads(app)
    user = make_user(app, username, **user_options)
    device = make_device(app, user)
    root_id, folder = add_root(app, user)
    return Env(
        client=client,
        app=app,
        user_id=user["user_id"],
        headers=device["headers"],
        root_id=root_id,
        folder=folder,
        library=app.state.settings.music_dir / user["library_dir"],
    )


@pytest.fixture
def env(client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> Env:
    return build_env(client, app, make_user, make_device, "alice")


@pytest.fixture
def other(client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> Env:
    return build_env(client, app, make_user, make_device, "bob")


def snapshot_tree(base: Path) -> dict[str, int]:
    return {
        path.relative_to(base).as_posix(): path.stat().st_size
        for path in sorted(base.rglob("*"))
        if path.is_file() and path.relative_to(base).parts[0] != "data"
    }


def error_code(response: Any) -> str:
    code: str = response.json()["error"]["code"]
    return code


# -- the happy path ----------------------------------------------------------------


def test_full_upload_of_a_real_file(env: Env, tmp_path: Path) -> None:
    source = make_audio(tmp_path / "src" / "song.flac", "flac", title="Hello")
    data = source.read_bytes()
    created = env.create("rock/song.flac", data)
    assert created.status_code == 201
    upload_id = created.json()["upload_id"]
    assert created.json() == {"upload_id": upload_id, "received_bytes": 0, "size_bytes": len(data)}
    assert not absolute_path_leaks(created.text, tmp_path)

    sent = env.put(upload_id, data, 0, len(data))
    assert (sent.status_code, sent.json()) == (200, {"received_bytes": len(data)})
    committed = env.commit(upload_id)
    assert committed.status_code == 200
    item = committed.json()["item"]
    assert (item["relative_path"], item["revision"], item["sha256"]) == (
        "rock/song.flac",
        1,
        sha(data),
    )
    assert item["size_bytes"] == len(data)
    assert not absolute_path_leaks(committed.text, tmp_path)
    assert (env.folder / "rock" / "song.flac").read_bytes() == data
    assert not (env.library / ".mtee-tmp" / "uploads" / f"{upload_id}.part").exists()
    assert env.status(upload_id) == {
        "upload_id": upload_id,
        "state": "done",
        "received_bytes": len(data),
        "size_bytes": len(data),
    }
    listed = env.client.get("/api/v1/items", headers=env.headers).json()["items"]
    assert [i["item_id"] for i in listed] == [item["item_id"]]
    assert env.kinds() == ["added"]
    assert env.payloads("added")[0]["relative_path"] == "rock/song.flac"
    # a second commit of the same upload is refused, not repeated
    assert env.commit(upload_id).status_code == 409


def test_a_cut_upload_resumes_where_it_stopped(env: Env) -> None:
    data = blob(300_000)
    upload_id = env.create("a.flac", data).json()["upload_id"]
    half = len(data) // 2
    assert env.put(upload_id, data[:half], 0, len(data)).json() == {"received_bytes": half}
    assert env.status(upload_id) == {
        "upload_id": upload_id,
        "state": "open",
        "received_bytes": half,
        "size_bytes": len(data),
    }
    # committing too early says how much is missing and keeps the upload open
    early = env.commit(upload_id)
    assert (early.status_code, error_code(early)) == (400, "bad_request")
    assert env.put(upload_id, data[half:], half, len(data)).json() == {"received_bytes": len(data)}
    assert env.commit(upload_id).status_code == 200
    assert (env.folder / "a.flac").read_bytes() == data


def test_a_wrong_start_is_416_with_the_current_offset(env: Env) -> None:
    data = blob(1000)
    upload_id = env.create("a.flac", data).json()["upload_id"]
    env.put(upload_id, data[:400], 0, 1000)
    for start in (0, 100, 700):
        response = env.put(upload_id, data[start : start + 100], start, 1000)
        assert (response.status_code, error_code(response)) == (416, "range_not_satisfiable")
        assert response.headers["Upload-Offset"] == "400"
    assert env.status(upload_id)["received_bytes"] == 400


@pytest.mark.parametrize(
    "header",
    [None, "", "bytes 0-9", "bytes 0-9/*", "items 0-9/100", "bytes 9-0/100", "bytes 0-100/100"],
)
def test_a_bad_content_range_is_400(env: Env, header: str | None) -> None:
    upload_id = env.create("a.flac", blob(100)).json()["upload_id"]
    headers = dict(env.headers)
    if header is not None:
        headers["Content-Range"] = header
    response = env.client.put(f"/api/v1/uploads/{upload_id}", content=b"x" * 10, headers=headers)
    assert (response.status_code, error_code(response)) == (400, "bad_request")
    assert env.status(upload_id)["received_bytes"] == 0


def test_a_total_that_is_not_the_upload_size_is_400(env: Env) -> None:
    upload_id = env.create("a.flac", blob(100)).json()["upload_id"]
    response = env.put(upload_id, blob(10), 0, 200)
    assert response.status_code == 400
    assert env.status(upload_id)["received_bytes"] == 0


def test_more_bytes_than_announced_is_400_and_only_the_announced_part_is_kept(env: Env) -> None:
    upload_id = env.create("a.flac", blob(100)).json()["upload_id"]
    headers = {**env.headers, "Content-Range": "bytes 0-9/100"}
    response = env.client.put(f"/api/v1/uploads/{upload_id}", content=blob(50), headers=headers)
    assert response.status_code == 400
    assert env.status(upload_id)["received_bytes"] == 10


def test_a_client_that_disconnects_keeps_what_arrived(env: Env, app: Starlette) -> None:
    data = blob(1000)
    upload_id = env.create("a.flac", data).json()["upload_id"]
    token = env.headers["Authorization"].encode()
    sent: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = [
        {"type": "http.request", "body": data[:300], "more_body": True},
        {"type": "http.disconnect"},
    ]

    async def receive() -> dict[str, Any]:
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "PUT",
        "scheme": "http",
        "path": f"/api/v1/uploads/{upload_id}",
        "raw_path": f"/api/v1/uploads/{upload_id}".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"authorization", token),
            (b"content-range", b"bytes 0-999/1000"),
            (b"host", b"test"),
        ],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }
    asyncio.run(app(scope, receive, send))  # pyright: ignore[reportArgumentType]
    assert env.status(upload_id)["received_bytes"] == 300
    # the client comes back, asks, and continues from there
    assert env.put(upload_id, data[300:], 300, 1000).json() == {"received_bytes": 1000}
    assert env.commit(upload_id).status_code == 200
    assert (env.folder / "a.flac").read_bytes() == data


def test_a_second_put_on_the_same_upload_is_refused(env: Env) -> None:
    data = blob(100)
    upload_id = env.create("a.flac", data).json()["upload_id"]
    uploads._busy.add(f"upload:{upload_id}")  # pyright: ignore[reportPrivateUsage]
    try:
        response = env.put(upload_id, data, 0, 100)
        assert (response.status_code, error_code(response)) == (409, "conflict")
        assert env.commit(upload_id).status_code == 409
        assert (
            env.client.delete(f"/api/v1/uploads/{upload_id}", headers=env.headers).status_code
            == 409
        )
    finally:
        uploads._busy.discard(f"upload:{upload_id}")  # pyright: ignore[reportPrivateUsage]
    assert env.put(upload_id, data, 0, 100).status_code == 200


def test_a_large_upload_arrives_in_batches(env: Env) -> None:
    data = blob(2_500_000, "big")
    upload_id = env.create("big.flac", data).json()["upload_id"]
    assert env.put(upload_id, data, 0, len(data)).json() == {"received_bytes": len(data)}
    assert env.commit(upload_id).status_code == 200
    assert (env.folder / "big.flac").read_bytes() == data


def test_an_empty_file_can_be_committed_without_a_put(env: Env) -> None:
    item = env.upload("empty.flac", b"")
    assert item["size_bytes"] == 0


# -- hash and size ----------------------------------------------------------------


def test_a_wrong_sha256_is_422_and_empties_the_part_file(env: Env) -> None:
    data = blob(2000)
    upload_id = env.create("a.flac", data, sha256=sha(b"something else")).json()["upload_id"]
    env.put(upload_id, data, 0, len(data))
    response = env.commit(upload_id)
    assert (response.status_code, error_code(response)) == (422, "bad_hash")
    assert env.status(upload_id)["received_bytes"] == 0
    assert not (env.folder / "a.flac").exists()
    assert env.kinds() == []
    # the upload stays open: sending the same bytes again fails the same way, not silently
    env.put(upload_id, data, 0, len(data))
    assert env.commit(upload_id).status_code == 422


def test_a_bad_sha256_value_is_refused_at_creation(env: Env) -> None:
    for bad in ("", "abc", sha(b"x").upper(), "g" * 64, sha(b"x") + "0"):
        assert env.create("a.flac", b"x", sha256=bad or "x").status_code == 400
    body = {
        "purpose": "item",
        "root_id": env.root_id,
        "relative_path": "a.flac",
        "size_bytes": 1,
    }
    response = env.client.post("/api/v1/uploads", json=body, headers=env.headers)
    assert response.status_code == 400


# -- paths -----------------------------------------------------------------------


def test_path_taken_by_an_item_or_by_a_file_on_disk_at_creation(env: Env) -> None:
    env.upload("a.flac", blob(50, "1"))
    taken = env.create("a.flac", blob(60, "2"))
    assert (taken.status_code, error_code(taken)) == (409, "path_taken")
    (env.folder / "by-hand.flac").write_bytes(b"hand")
    taken = env.create("by-hand.flac", blob(60, "3"))
    assert (taken.status_code, error_code(taken)) == (409, "path_taken")
    assert (env.folder / "by-hand.flac").read_bytes() == b"hand"
    (env.folder / "folder.flac").mkdir()
    assert env.create("folder.flac", blob(10)).status_code == 409


def test_commit_with_path_taken_keeps_the_upload_and_a_new_name_works(env: Env) -> None:
    data = blob(5000)
    upload_id = env.create("song.flac", data).json()["upload_id"]
    env.put(upload_id, data, 0, len(data))
    # somebody copies a file there by hand after the upload was opened
    (env.folder / "song.flac").write_bytes(b"precious")
    taken = env.commit(upload_id)
    assert (taken.status_code, error_code(taken)) == (409, "path_taken")
    assert (env.folder / "song.flac").read_bytes() == b"precious"
    assert env.status(upload_id)["state"] == "open"
    assert env.status(upload_id)["received_bytes"] == len(data)

    again = env.commit(upload_id, relative_path="new/folder/song (2).flac")
    assert again.status_code == 200
    assert again.json()["item"]["relative_path"] == "new/folder/song (2).flac"
    assert (env.folder / "new" / "folder" / "song (2).flac").read_bytes() == data
    assert (env.folder / "song.flac").read_bytes() == b"precious"


def test_commit_never_overwrites_a_present_item_either(env: Env) -> None:
    env.upload("a.flac", blob(100, "old"))
    data = blob(100, "new")
    # open the upload for a free name, then take the item name by moving another item there
    upload_id = env.create("b.flac", data).json()["upload_id"]
    env.put(upload_id, data, 0, 100)
    assert env.commit(upload_id, relative_path="a.flac").status_code == 409
    assert (env.folder / "a.flac").read_bytes() == blob(100, "old")


BAD_PATHS = [
    "../evil.flac",
    "a/../../evil.flac",
    "/etc/evil.flac",
    "a\\..\\evil.flac",
    "C:/evil.flac",
    "c:evil.flac",
    "\uff0e\uff0e/evil.flac",
    "a/\uff0e\uff0e/evil.flac",
    "a//b.flac",
    "./a.flac",
    "a/./b.flac",
    "",
    ".mtee-tmp/evil.flac",
    ".mtee-trash/evil.flac",
    "a/.hidden/evil.flac",
    "notes.txt",
    "no-extension",
]


@pytest.mark.parametrize("path", BAD_PATHS)
def test_bad_paths_are_refused_and_nothing_is_written(env: Env, tmp_path: Path, path: str) -> None:
    before = snapshot_tree(tmp_path)
    response = env.create(path, blob(10))
    assert (response.status_code, error_code(response)) == (400, "bad_request")
    assert snapshot_tree(tmp_path) == before
    assert not list((tmp_path / "music").rglob("*.part"))


@pytest.mark.parametrize("path", BAD_PATHS[:-3])
def test_bad_paths_at_commit_are_refused_and_the_upload_stays(
    env: Env, tmp_path: Path, path: str
) -> None:
    data = blob(100)
    upload_id = env.create("ok.flac", data).json()["upload_id"]
    env.put(upload_id, data, 0, 100)
    before = snapshot_tree(tmp_path)
    response = env.commit(upload_id, relative_path=path)
    assert (response.status_code, error_code(response)) == (400, "bad_request")
    assert snapshot_tree(tmp_path) == before
    assert env.status(upload_id)["state"] == "open"


def test_a_symlinked_folder_cannot_lead_outside(env: Env, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (env.folder / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")
    data = blob(100)
    upload_id = env.create("ok.flac", data).json()["upload_id"]
    env.put(upload_id, data, 0, 100)
    assert env.create("link/evil.flac", data).status_code == 400
    assert env.commit(upload_id, relative_path="link/evil.flac").status_code == 400
    assert list(outside.iterdir()) == []


def test_another_purpose_is_refused_for_now(env: Env) -> None:
    for purpose in ("backup", "other", ""):
        body = {
            "purpose": purpose,
            "root_id": env.root_id,
            "relative_path": "a.flac",
            "size_bytes": 1,
            "sha256": sha(b"x"),
        }
        response = env.client.post("/api/v1/uploads", json=body, headers=env.headers)
        assert response.status_code == 400, purpose


def test_base_item_and_base_revision_go_together(env: Env) -> None:
    item = env.upload("a.flac", blob(10))
    assert env.create("a.flac", blob(11), base_item_id=item["item_id"]).status_code == 400
    assert env.create("a.flac", blob(11), base_revision=1).status_code == 400
    assert (
        env.create("a.flac", blob(11), base_item_id=item["item_id"], base_revision=0).status_code
        == 400
    )


# -- replacement -----------------------------------------------------------------


def test_a_replacement_moves_the_old_file_to_the_trash(env: Env) -> None:
    old, new = blob(1000, "old"), blob(1500, "new")
    item = env.upload("rock/a.flac", old)
    created = env.create("rock/a.flac", new, base_item_id=item["item_id"], base_revision=1)
    assert created.status_code == 201
    upload_id = created.json()["upload_id"]
    env.put(upload_id, new, 0, len(new))
    committed = env.commit(upload_id)
    assert committed.status_code == 200, committed.text
    replaced = committed.json()["item"]
    assert (replaced["item_id"], replaced["revision"], replaced["sha256"]) == (
        item["item_id"],
        2,
        sha(new),
    )
    assert replaced["size_bytes"] == 1500
    assert (env.folder / "rock" / "a.flac").read_bytes() == new

    entries = env.trash_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert (entry["kind"], entry["item_id"], entry["size_bytes"]) == ("item", item["item_id"], 1000)
    assert (entry["original_root_id"], entry["original_relative_path"]) == (
        env.root_id,
        "rock/a.flac",
    )
    row = env.app.state.db.conn().execute("SELECT * FROM trash").fetchone()
    assert row["stored_path"] == f".mtee-trash/{row['trash_id']}/a.flac"
    assert (env.library / row["stored_path"]).read_bytes() == old
    assert row["trashed_by_device_id"] is not None
    assert env.kinds() == ["added", "replaced"]
    assert env.payloads("replaced")[0]["revision"] == 2
    # the item is still one item at the same path
    listed = env.client.get("/api/v1/items", headers=env.headers).json()["items"]
    assert [(i["item_id"], i["revision"]) for i in listed] == [(item["item_id"], 2)]


def test_a_replacement_ignores_the_path_the_client_sent(env: Env) -> None:
    item = env.upload("a.flac", blob(100, "1"))
    new = blob(120, "2")
    created = env.create("elsewhere/b.flac", new, base_item_id=item["item_id"], base_revision=1)
    upload_id = created.json()["upload_id"]
    env.put(upload_id, new, 0, 120)
    assert env.commit(upload_id).json()["item"]["relative_path"] == "a.flac"
    assert not (env.folder / "elsewhere").exists()
    assert env.commit(upload_id).status_code == 409


def test_a_replacement_from_an_old_revision_is_a_conflict(env: Env) -> None:
    item = env.upload("a.flac", blob(100, "1"))
    # a second device replaces the file first
    env.upload("a.flac", blob(110, "2"), base_item_id=item["item_id"], base_revision=1)
    stale = blob(120, "3")
    created = env.create("a.flac", stale, base_item_id=item["item_id"], base_revision=1)
    assert created.status_code == 201
    upload_id = created.json()["upload_id"]
    env.put(upload_id, stale, 0, len(stale))
    response = env.commit(upload_id)
    assert (response.status_code, error_code(response)) == (409, "conflict")
    message = response.json()["error"]["message"]
    assert "revision 2" in message and "revision 1" in message
    assert env.status(upload_id)["state"] == "conflict"
    assert env.status(upload_id)["received_bytes"] == len(stale)  # kept for the client
    assert (env.folder / "a.flac").read_bytes() == blob(110, "2")
    assert len(env.trash_entries()) == 1
    assert env.kinds() == ["added", "replaced"]
    # a conflicting upload stays conflicting, and can be cancelled
    assert env.commit(upload_id).status_code == 409
    assert env.client.delete(f"/api/v1/uploads/{upload_id}", headers=env.headers).status_code == 204


def test_a_replacement_of_a_trashed_or_missing_item_is_refused(env: Env) -> None:
    item = env.upload("a.flac", blob(100))
    created = env.create("a.flac", blob(100, "n"), base_item_id=item["item_id"], base_revision=1)
    upload_id = created.json()["upload_id"]
    env.put(upload_id, blob(100, "n"), 0, 100)
    env.client.post(f"/api/v1/items/{item['item_id']}/trash", headers=env.headers)
    response = env.commit(upload_id)
    assert (response.status_code, error_code(response)) == (409, "conflict")
    assert (
        env.create("a.flac", blob(5), base_item_id=item["item_id"], base_revision=1).status_code
        == 404
    )
    assert env.create("a.flac", blob(5), base_item_id="0" * 32, base_revision=1).status_code == 404


def test_a_failed_database_step_undoes_a_replacement(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    old, new = blob(100, "old"), blob(100, "new")
    item = env.upload("a.flac", old)
    created = env.create("a.flac", new, base_item_id=item["item_id"], base_revision=1)
    upload_id = created.json()["upload_id"]
    env.put(upload_id, new, 0, 100)

    def boom(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("database failure")

    monkeypatch.setattr(store, "replace_item_file", boom)
    with pytest.raises(RuntimeError):
        env.commit(upload_id)
    monkeypatch.undo()
    assert (env.folder / "a.flac").read_bytes() == old
    assert env.trash_entries() == []
    assert not list((env.library / ".mtee-trash").glob("*/*"))
    # the new bytes are back in the part file and the upload can be committed again
    assert env.status(upload_id)["received_bytes"] == 100
    assert env.commit(upload_id).status_code == 200
    assert (env.folder / "a.flac").read_bytes() == new


# -- quota -----------------------------------------------------------------------


def test_quota_exceeded_is_413(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    env = build_env(client, app, make_user, make_device, "carol", quota_bytes=1000)
    env.upload("a.flac", blob(600, "1"))
    response = env.create("b.flac", blob(500, "2"))
    assert (response.status_code, error_code(response)) == (413, "quota_exceeded")
    assert not list(env.library.rglob("*.part"))
    ok = env.create("b.flac", blob(400, "2"))
    assert ok.status_code == 201
    # an open upload counts too
    again = env.create("c.flac", blob(1, "3"))
    assert (again.status_code, error_code(again)) == (413, "quota_exceeded")
    env.client.delete(f"/api/v1/uploads/{ok.json()['upload_id']}", headers=env.headers)
    assert env.create("c.flac", blob(400, "3")).status_code == 201


def test_a_replacement_may_be_as_big_as_the_quota_minus_the_other_files(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    env = build_env(client, app, make_user, make_device, "carol", quota_bytes=1000)
    item = env.upload("a.flac", blob(900, "1"))
    big = blob(950, "2")
    # without the replaced size this would be 900 + 950 > 1000
    created = env.create("a.flac", big, base_item_id=item["item_id"], base_revision=1)
    assert created.status_code == 201
    too_big = env.create("a.flac", blob(1001, "3"), base_item_id=item["item_id"], base_revision=1)
    assert too_big.status_code == 413


def test_used_bytes_counts_items_trash_and_open_uploads(env: Env) -> None:
    item = env.upload("a.flac", blob(100, "1"))
    env.upload("b.flac", blob(50, "2"))
    env.client.post(f"/api/v1/items/{item['item_id']}/trash", headers=env.headers)
    env.create("c.flac", blob(7, "3"))
    conn = env.app.state.db.conn()
    assert uploads.used_bytes(conn, env.user_id) == 100 + 50 + 7


# -- hard links ------------------------------------------------------------------


def test_identical_content_becomes_a_hard_link_split_by_a_replacement(env: Env) -> None:
    data = blob(4000, "same")
    env.upload("one/a.flac", data)
    # the hash worker may not have run: the upload recorded the sha256, which is enough
    item_b = env.upload("two/b.flac", data)
    a, b = env.folder / "one" / "a.flac", env.folder / "two" / "b.flac"
    assert a.stat().st_ino == b.stat().st_ino
    assert a.stat().st_nlink == 2
    assert item_b["revision"] == 1
    assert not list(env.library.rglob("*.part"))

    item_a = env.client.get("/api/v1/items", headers=env.headers).json()["items"][0]
    assert item_a["relative_path"] == "one/a.flac"
    new = blob(4100, "changed")
    created = env.create("one/a.flac", new, base_item_id=item_a["item_id"], base_revision=1)
    upload_id = created.json()["upload_id"]
    env.put(upload_id, new, 0, len(new))
    assert env.commit(upload_id).status_code == 200
    assert a.read_bytes() == new
    assert b.read_bytes() == data  # the other path is untouched
    assert a.stat().st_ino != b.stat().st_ino


def test_a_link_across_users_on_the_same_disk_is_created_too(env: Env, other: Env) -> None:
    data = blob(3000, "shared")
    env.upload("a.flac", data)
    other.upload("b.flac", data)
    assert (env.folder / "a.flac").stat().st_ino == (other.folder / "b.flac").stat().st_ino
    # a replacement by one user never changes the other's file
    item = other.client.get("/api/v1/items", headers=other.headers).json()["items"][0]
    new = blob(3000, "bob-edit")
    other.upload("b.flac", new, base_item_id=item["item_id"], base_revision=1)
    assert (env.folder / "a.flac").read_bytes() == data
    assert (other.folder / "b.flac").read_bytes() == new


def test_no_link_is_made_when_the_known_file_changed_on_disk(env: Env) -> None:
    data = blob(2000, "x")
    env.upload("a.flac", data)
    # the file was edited by hand: the stored sha256 no longer describes it
    (env.folder / "a.flac").write_bytes(blob(2000, "y"))
    item_b = env.upload("b.flac", data)
    assert item_b["sha256"] == sha(data)
    assert (env.folder / "b.flac").read_bytes() == data
    assert (env.folder / "a.flac").stat().st_ino != (env.folder / "b.flac").stat().st_ino


def test_without_hard_links_the_file_is_simply_placed(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = blob(1000, "z")
    env.upload("a.flac", data)

    def no_links(*args: Any, **kwargs: Any) -> None:
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    env.upload("b.flac", data)  # dedupe fails, the rename fallback places the part file
    assert (env.folder / "b.flac").read_bytes() == data
    assert (env.folder / "a.flac").stat().st_ino != (env.folder / "b.flac").stat().st_ino
    # the fallback still never overwrites
    (env.folder / "c.flac").write_bytes(b"hand")
    created = env.create("d.flac", data)
    upload_id = created.json()["upload_id"]
    env.put(upload_id, data, 0, len(data))
    (env.folder / "d.flac").write_bytes(b"hand too")
    assert env.commit(upload_id).status_code == 409
    assert (env.folder / "d.flac").read_bytes() == b"hand too"


# -- cancel, isolation, scan ------------------------------------------------------


def test_cancel_removes_the_part_file(env: Env) -> None:
    data = blob(500)
    upload_id = env.create("a.flac", data).json()["upload_id"]
    env.put(upload_id, data[:100], 0, 500)
    part = env.library / ".mtee-tmp" / "uploads" / f"{upload_id}.part"
    assert part.is_file()
    assert env.client.delete(f"/api/v1/uploads/{upload_id}", headers=env.headers).status_code == 204
    assert not part.exists()
    status = env.status(upload_id)
    assert (status["state"], status["received_bytes"]) == ("cancelled", 0)
    assert env.put(upload_id, data[100:], 100, 500).status_code == 409
    assert env.commit(upload_id).status_code == 409
    # a done upload cannot be cancelled
    done = env.create("b.flac", data).json()["upload_id"]
    env.put(done, data, 0, 500)
    env.commit(done)
    assert env.client.delete(f"/api/v1/uploads/{done}", headers=env.headers).status_code == 409


def test_another_user_cannot_reach_an_upload_or_an_item_or_a_root(env: Env, other: Env) -> None:
    data = blob(200)
    upload_id = env.create("a.flac", data).json()["upload_id"]
    env.put(upload_id, data[:50], 0, 200)
    url = f"/api/v1/uploads/{upload_id}"
    assert other.client.get(url, headers=other.headers).status_code == 404
    assert other.put(upload_id, data[50:], 50, 200).status_code == 404
    assert other.client.post(url + "/commit", headers=other.headers).status_code == 404
    assert other.client.delete(url, headers=other.headers).status_code == 404
    assert env.status(upload_id)["received_bytes"] == 50

    # bob cannot upload into alice's root, nor replace alice's item
    body = {
        "purpose": "item",
        "root_id": env.root_id,
        "relative_path": "x.flac",
        "size_bytes": 1,
        "sha256": sha(b"x"),
    }
    assert other.client.post("/api/v1/uploads", json=body, headers=other.headers).status_code == 404
    env.put(upload_id, data[50:], 50, 200)
    item = env.commit(upload_id).json()["item"]
    own_root = other.create("a.flac", b"x", base_item_id=item["item_id"], base_revision=1)
    assert own_root.status_code == 404
    forced = other.client.post(
        "/api/v1/uploads",
        json={
            **body,
            "root_id": other.root_id,
            "base_item_id": item["item_id"],
            "base_revision": 1,
        },
        headers=other.headers,
    )
    assert forced.status_code == 404


def test_the_routes_need_a_token(client: TestClient) -> None:
    assert client.post("/api/v1/uploads", json={}).status_code == 401
    assert client.get("/api/v1/uploads/abc").status_code == 401
    assert client.put("/api/v1/uploads/abc", content=b"x").status_code == 401
    assert client.post("/api/v1/uploads/abc/commit").status_code == 401
    assert client.delete("/api/v1/uploads/abc").status_code == 401


def test_a_scan_after_uploads_finds_nothing_new(env: Env) -> None:
    env.upload("a.flac", blob(100, "1"))
    env.upload("sub/b.flac", blob(100, "1"))  # hard link
    item = env.upload("c.flac", blob(100, "2"))
    new = blob(100, "3")
    env.upload("c.flac", new, base_item_id=item["item_id"], base_revision=1)
    open_upload = env.create("d.flac", blob(100, "4")).json()["upload_id"]
    assert (env.library / ".mtee-tmp").is_dir() and (env.library / ".mtee-trash").is_dir()
    db, settings = env.app.state.db, env.app.state.settings
    result = scanner.scan_root(db, settings, env.root_id)
    assert result == scanner.ScanResult(unchanged=3)
    assert (
        env.client.delete(f"/api/v1/uploads/{open_upload}", headers=env.headers).status_code == 204
    )


def test_a_scan_of_a_whole_library_root_skips_the_part_and_trash_folders(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    from mtee_remote import clock
    from mtee_remote.ids import new_id

    stop_background_threads(app)
    user = make_user(app, "dora")
    device = make_device(app, user)
    root_id = new_id()
    with app.state.db.transaction() as tx:
        tx.conn.execute(
            "INSERT INTO roots(root_id, user_id, name, relative_dir, adopted, created_at_utc)"
            " VALUES (?,?,?,'',1,?)",
            (root_id, user["user_id"], "all", clock.to_iso(clock.utc_now())),
        )
    env = Env(
        client, app, user["user_id"], device["headers"], root_id,
        app.state.settings.music_dir / "dora", app.state.settings.music_dir / "dora",
    )  # fmt: skip
    first = env.upload("one.flac", blob(100, "1"))
    env.upload("two.flac", blob(100, "2"))
    env.upload("one.flac", blob(110, "3"), base_item_id=first["item_id"], base_revision=1)
    env.create("three.flac", blob(100, "4"))
    assert (env.library / ".mtee-tmp").is_dir() and (env.library / ".mtee-trash").is_dir()
    result = scanner.scan_root(app.state.db, app.state.settings, root_id)
    assert result == scanner.ScanResult(unchanged=2)


def test_no_absolute_path_in_any_response(env: Env, tmp_path: Path) -> None:
    data = blob(100)
    created = env.create("a.flac", data)
    upload_id = created.json()["upload_id"]
    texts = [
        created.text,
        env.put(upload_id, data, 0, 100).text,
        env.client.get(f"/api/v1/uploads/{upload_id}", headers=env.headers).text,
        env.commit(upload_id).text,
        env.create("a.flac", data).text,
    ]
    assert not any(absolute_path_leaks(text, tmp_path) for text in texts)


def test_committed_items_are_hashed_later_by_the_hash_worker(env: Env) -> None:
    data = blob(2000, "hash me")
    item = env.upload("a.flac", data)
    row = env.app.state.db.conn().execute("SELECT hash_state FROM items").fetchone()
    assert row["hash_state"] == "pending"
    assert scanner.hash_pending(env.app.state.db, env.app.state.settings) == 1
    stored = env.client.get(f"/api/v1/items/{item['item_id']}", headers=env.headers).json()
    assert (stored["hash_state"], stored["sha256"]) == ("done", sha(data))
    assert env.kinds() == ["added"]
