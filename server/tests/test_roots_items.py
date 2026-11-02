"""The root and item routes, and the library service behind them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from conftest import MakeDevice, MakeUser
from helpers import make_audio
from mtee_remote.app import create_app
from mtee_remote.config import Settings
from mtee_remote.library import scanner
from test_scanner import add_root


def absolute_path_leaks(text: str, tmp_path: Path) -> bool:
    return (
        str(tmp_path) in text
        or tmp_path.as_posix() in text
        or str(tmp_path).replace("\\", "\\\\") in text
    )


@pytest.fixture
def alice(app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> dict[str, Any]:
    user = make_user(app, "alice")
    return {**user, **make_device(app, user)}


@pytest.fixture
def bob(app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> dict[str, Any]:
    user = make_user(app, "bob")
    return {**user, **make_device(app, user)}


def test_roots_need_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/roots").status_code == 401
    assert client.get("/api/v1/items").status_code == 401
    assert client.get("/api/v1/library/status").status_code == 401


def test_create_and_list_roots(
    client: TestClient, app: Starlette, alice: dict[str, Any], tmp_path: Path
) -> None:
    assert client.get("/api/v1/roots", headers=alice["headers"]).json() == {"roots": []}
    response = client.post("/api/v1/roots", json={"name": "rock"}, headers=alice["headers"])
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "rock"
    assert created["relative_dir"] == "rock"
    assert created["adopted"] is False
    assert (created["item_count"], created["total_bytes"]) == (0, 0)
    assert (app.state.settings.music_dir / "alice" / "rock").is_dir()
    listed = client.get("/api/v1/roots", headers=alice["headers"]).json()["roots"]
    assert listed == [created]
    assert not absolute_path_leaks(response.text, tmp_path)


def test_root_counts_follow_the_items(
    client: TestClient, app: Starlette, alice: dict[str, Any]
) -> None:
    root = client.post("/api/v1/roots", json={"name": "rock"}, headers=alice["headers"]).json()
    folder = app.state.settings.music_dir / "alice" / "rock"
    make_audio(folder / "a.flac", "flac")
    make_audio(folder / "b.flac", "flac")
    scanner.scan_root(app.state.db, app.state.settings, root["root_id"])
    listed = client.get("/api/v1/roots", headers=alice["headers"]).json()["roots"][0]
    assert listed["item_count"] == 2
    assert listed["total_bytes"] == sum(p.stat().st_size for p in folder.iterdir())


@pytest.mark.parametrize("name", ["a/b", "", "..", ".", "a\\b", "/abs"])
def test_create_root_refuses_bad_names(
    client: TestClient, alice: dict[str, Any], name: str
) -> None:
    response = client.post("/api/v1/roots", json={"name": name}, headers=alice["headers"])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_create_root_needs_a_name(client: TestClient, alice: dict[str, Any]) -> None:
    response = client.post("/api/v1/roots", json={}, headers=alice["headers"])
    assert response.status_code == 400


def test_create_root_conflicts(
    client: TestClient, app: Starlette, alice: dict[str, Any], bob: dict[str, Any]
) -> None:
    assert (
        client.post("/api/v1/roots", json={"name": "rock"}, headers=alice["headers"]).status_code
        == 201
    )
    taken = client.post("/api/v1/roots", json={"name": "rock"}, headers=alice["headers"])
    assert (taken.status_code, taken.json()["error"]["code"]) == (409, "conflict")
    # another user may use the same name
    assert (
        client.post("/api/v1/roots", json={"name": "rock"}, headers=bob["headers"]).status_code
        == 201
    )
    # a root nested inside the new folder blocks it
    add_root(app, bob, "jazz/cool")
    assert (
        client.post("/api/v1/roots", json={"name": "jazz"}, headers=bob["headers"]).status_code
        == 409
    )


def test_create_root_refused_when_the_library_is_one_root(
    client: TestClient, app: Starlette, alice: dict[str, Any]
) -> None:
    from mtee_remote import clock
    from mtee_remote.ids import new_id

    with app.state.db.transaction() as tx:
        tx.conn.execute(
            "INSERT INTO roots(root_id, user_id, name, relative_dir, adopted, created_at_utc)"
            " VALUES (?,?,?,'',1,?)",
            (new_id(), alice["user_id"], "everything", clock.to_iso(clock.utc_now())),
        )
    response = client.post("/api/v1/roots", json={"name": "new"}, headers=alice["headers"])
    assert (response.status_code, response.json()["error"]["code"]) == (409, "conflict")
    assert not (app.state.settings.music_dir / "alice" / "new").exists()


def test_scan_route_queues_a_scan_and_status_reports(
    client: TestClient, app: Starlette, alice: dict[str, Any]
) -> None:
    root = client.post("/api/v1/roots", json={"name": "rock"}, headers=alice["headers"]).json()
    make_audio(app.state.settings.music_dir / "alice" / "rock" / "a.flac", "flac", title="T")
    response = client.post(f"/api/v1/roots/{root['root_id']}/scan", headers=alice["headers"])
    assert (response.status_code, response.json()) == (202, {"queued": True})
    assert app.state.library.wait_idle(60)
    status = client.get("/api/v1/library/status", headers=alice["headers"]).json()
    assert status == {"scanning": False, "pending": 0, "done": 1, "errors": 0}
    items = client.get("/api/v1/items", headers=alice["headers"]).json()["items"]
    assert [i["relative_path"] for i in items] == ["a.flac"]
    assert items[0]["hash_state"] == "done"
    assert items[0]["metadata"]["title"] == ["T"]


def test_scan_route_is_404_for_another_users_root(
    client: TestClient, alice: dict[str, Any], bob: dict[str, Any]
) -> None:
    root = client.post("/api/v1/roots", json={"name": "rock"}, headers=alice["headers"]).json()
    assert (
        client.post(f"/api/v1/roots/{root['root_id']}/scan", headers=bob["headers"]).status_code
        == 404
    )
    assert client.post("/api/v1/roots/nope/scan", headers=alice["headers"]).status_code == 404
    assert client.get("/api/v1/roots", headers=bob["headers"]).json() == {"roots": []}


def fill(app: Starlette, user: dict[str, Any], root_name: str, names: list[str]) -> str:
    root_id, folder = add_root(app, user, root_name)
    for name in names:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" + name.encode())
    scanner.scan_root(app.state.db, app.state.settings, root_id)
    return root_id


def test_items_paging_and_filters(
    client: TestClient, app: Starlette, alice: dict[str, Any]
) -> None:
    first = fill(app, alice, "one", ["b.mp3", "a.mp3", "sub/c.mp3", "sub/d.mp3"])
    second = fill(app, alice, "two", ["z.mp3"])
    everything = client.get("/api/v1/items?limit=1000", headers=alice["headers"]).json()
    assert everything["next"] is None
    expected = sorted(
        [(first, p) for p in ("a.mp3", "b.mp3", "sub/c.mp3", "sub/d.mp3")] + [(second, "z.mp3")]
    )
    assert [(i["root_id"], i["relative_path"]) for i in everything["items"]] == expected

    seen: list[tuple[str, str]] = []
    url = "/api/v1/items?limit=2"
    pages = 0
    while True:
        page = client.get(url, headers=alice["headers"]).json()
        seen += [(i["root_id"], i["relative_path"]) for i in page["items"]]
        pages += 1
        if page["next"] is None:
            break
        url = f"/api/v1/items?limit=2&after={page['next']}"
    assert seen == expected
    assert pages == 3

    only_first = client.get(f"/api/v1/items?root_id={first}", headers=alice["headers"]).json()
    assert len(only_first["items"]) == 4
    by_prefix = client.get(f"/api/v1/items?root_id={first}&prefix=sub/", headers=alice["headers"])
    assert [i["relative_path"] for i in by_prefix.json()["items"]] == ["sub/c.mp3", "sub/d.mp3"]
    assert client.get("/api/v1/items?prefix=nothing", headers=alice["headers"]).json() == {
        "items": [],
        "next": None,
    }


def test_prefix_treats_wildcards_literally(
    client: TestClient, app: Starlette, alice: dict[str, Any]
) -> None:
    fill(app, alice, "wild", ["100%/a.mp3", "100x/b.mp3", "a_b/c.mp3", "aXb/d.mp3"])
    percent = client.get("/api/v1/items?prefix=100%25", headers=alice["headers"]).json()
    assert [i["relative_path"] for i in percent["items"]] == ["100%/a.mp3"]
    underscore = client.get("/api/v1/items?prefix=a_b", headers=alice["headers"]).json()
    assert [i["relative_path"] for i in underscore["items"]] == ["a_b/c.mp3"]


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=1001", "limit=abc", "after=!!!", "prefix=../x"]
)
def test_items_refuse_bad_parameters(client: TestClient, alice: dict[str, Any], query: str) -> None:
    response = client.get(f"/api/v1/items?{query}", headers=alice["headers"])
    assert response.status_code == 400


def test_items_are_private_to_their_owner(
    client: TestClient, app: Starlette, alice: dict[str, Any], bob: dict[str, Any], tmp_path: Path
) -> None:
    fill(app, alice, "mine", ["a.mp3"])
    items = client.get("/api/v1/items", headers=alice["headers"])
    assert not absolute_path_leaks(items.text, tmp_path)
    item = items.json()["items"][0]
    assert client.get("/api/v1/items", headers=bob["headers"]).json()["items"] == []
    one = client.get(f"/api/v1/items/{item['item_id']}", headers=alice["headers"])
    assert one.status_code == 200
    assert one.json() == item
    assert not absolute_path_leaks(one.text, tmp_path)
    other = client.get(f"/api/v1/items/{item['item_id']}", headers=bob["headers"])
    assert (other.status_code, other.json()["error"]["code"]) == (404, "not_found")
    assert client.get("/api/v1/items/unknown", headers=alice["headers"]).status_code == 404


def test_a_trashed_item_is_not_listed(
    client: TestClient, app: Starlette, alice: dict[str, Any]
) -> None:
    from mtee_remote.library import store

    fill(app, alice, "mine", ["a.mp3"])
    item = client.get("/api/v1/items", headers=alice["headers"]).json()["items"][0]
    with app.state.db.transaction() as tx:
        store.mark_trashed(tx, item["item_id"])
    assert client.get("/api/v1/items", headers=alice["headers"]).json()["items"] == []
    assert (
        client.get(f"/api/v1/items/{item['item_id']}", headers=alice["headers"]).status_code == 404
    )


def test_the_service_scans_and_hashes_on_request(tmp_path: Path, make_user: MakeUser) -> None:
    settings = Settings(data_dir=tmp_path / "data", music_dir=tmp_path / "music", scan_interval_s=0)
    settings.music_dir.mkdir()
    app = create_app(settings)
    user = make_user(app)
    root_id, folder = add_root(app, user)
    make_audio(folder / "before.flac", "flac")
    with TestClient(app):
        library = app.state.library
        assert library.wait_idle(10)
        # scan_interval_s == 0: no start scan, so nothing was found yet
        assert library.status() == {"scanning": False, "pending": 0, "done": 0, "errors": 0}
        library.request_scan(root_id)
        assert library.wait_idle(60)
        assert library.status() == {"scanning": False, "pending": 0, "done": 1, "errors": 0}
        make_audio(folder / "after.mp3", "mp3")
        library.request_scan(root_id)
        assert library.wait_idle(60)
        assert library.status()["done"] == 2


def test_the_service_scans_at_start_when_the_interval_is_set(
    tmp_path: Path, make_user: MakeUser
) -> None:
    settings = Settings(
        data_dir=tmp_path / "data", music_dir=tmp_path / "music", scan_interval_s=3600
    )
    settings.music_dir.mkdir()
    app = create_app(settings)
    user = make_user(app)
    _, folder = add_root(app, user)
    make_audio(folder / "a.flac", "flac")
    with TestClient(app):
        assert app.state.library.wait_idle(60)
        assert app.state.library.status()["done"] == 1


def test_stop_joins_the_threads(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", music_dir=tmp_path / "music", scan_interval_s=0)
    settings.music_dir.mkdir()
    app = create_app(settings)
    with TestClient(app):
        library = app.state.library
        threads = list(library._threads)  # pyright: ignore[reportPrivateUsage]
        assert all(t.is_alive() for t in threads)
    assert not any(t.is_alive() for t in threads)
