"""The records routes: play log, playlists, track data and synced settings (milestone 126.7)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from conftest import MakeDevice, MakeUser
from mtee_remote import clock
from mtee_remote.ids import new_id
from mtee_remote.library import store

RECORDS = "/api/v1/records"
PLAY_EVENTS = f"{RECORDS}/play-events"
PLAYLISTS = f"{RECORDS}/playlists"
TRACK_DATA = f"{RECORDS}/track-data"
SETTINGS = f"{RECORDS}/settings"


def _item(app: Starlette, user: dict[str, Any], relative_path: str = "track.flac") -> str:
    """Insert one present item for `user` in a new root and return its id."""
    now = clock.to_iso(clock.utc_now())
    root_id = new_id()
    with app.state.db.transaction() as tx:
        tx.conn.execute(
            "INSERT INTO roots(root_id, user_id, name, relative_dir, adopted, created_at_utc)"
            " VALUES (?,?,?,?,0,?)",
            (root_id, user["user_id"], f"root-{root_id[:8]}", "", now),
        )
        return store.insert_item(
            tx,
            user_id=user["user_id"],
            root_id=root_id,
            relative_path=relative_path,
            size_bytes=10,
            mtime_ns=1,
            inode=None,
        )


def _journal(app: Starlette, user: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    rows = (
        app.state.db.conn()
        .execute(
            "SELECT payload_json FROM journal WHERE user_id = ? AND kind = ? ORDER BY seq",
            (user["user_id"], kind),
        )
        .fetchall()
    )
    return [json.loads(row["payload_json"]) for row in rows]


# -- play log -----------------------------------------------------------------------------


def test_play_events_reach_the_other_device_once(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device_a = make_device(app, alice, name="A")
    device_b = make_device(app, alice, name="B")
    batch = [
        {"event_id": "e1", "track": "x", "played_at_utc": "2026-11-01T10:00:00Z"},
        {"event_id": "e2", "track": "y"},
    ]

    first = client.post(PLAY_EVENTS, json={"events": batch}, headers=device_a["headers"])
    assert first.status_code == 200
    assert first.json() == {"inserted": 2, "skipped": 0}

    again = client.post(PLAY_EVENTS, json={"events": batch}, headers=device_a["headers"])
    assert again.json() == {"inserted": 0, "skipped": 2}

    view = client.get(f"{PLAY_EVENTS}?since=0", headers=device_b["headers"]).json()
    assert [event["event_id"] for event in view["events"]] == ["e1", "e2"]
    assert {event["device_id"] for event in view["events"]} == {device_a["device_id"]}
    assert view["events"][0]["payload"] == batch[0]
    assert view["next"] == view["events"][-1]["seq"]
    assert view["more"] is False

    after = client.get(f"{PLAY_EVENTS}?since={view['next']}", headers=device_b["headers"])
    assert after.json() == {"events": [], "next": view["next"], "more": False}

    # Device B sends an overlap and one new event: only the new one is stored.
    mixed = [{"event_id": "e2", "track": "y"}, {"event_id": "e3", "track": "z"}]
    from_b = client.post(PLAY_EVENTS, json={"events": mixed}, headers=device_b["headers"])
    assert from_b.json() == {"inserted": 1, "skipped": 1}
    later = client.get(f"{PLAY_EVENTS}?since={view['next']}", headers=device_a["headers"]).json()
    assert [event["event_id"] for event in later["events"]] == ["e3"]
    assert later["events"][0]["device_id"] == device_b["device_id"]

    # One journal entry per call that stored something, with the count and the last sequence.
    entries = _journal(app, alice, "play_events")
    assert entries == [
        {"count": 2, "last_seq": 2},
        {"count": 1, "last_seq": later["events"][0]["seq"]},
    ]


def test_play_events_paging_and_bad_query(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    events = [{"event_id": f"p{index}"} for index in range(3)]
    client.post(PLAY_EVENTS, json={"events": events}, headers=device["headers"])

    page = client.get(f"{PLAY_EVENTS}?since=0&limit=2", headers=device["headers"]).json()
    assert len(page["events"]) == 2
    assert page["more"] is True
    rest = client.get(f"{PLAY_EVENTS}?since={page['next']}", headers=device["headers"]).json()
    assert [event["event_id"] for event in rest["events"]] == ["p2"]
    assert rest["more"] is False

    for query in ("limit=0", "limit=1001", "since=-1", "since=abc"):
        response = client.get(f"{PLAY_EVENTS}?{query}", headers=device["headers"])
        assert response.status_code == 400, query


def test_play_events_of_other_users_are_invisible(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    bob = make_user(app, "bob")
    alice_device = make_device(app, alice)
    bob_device = make_device(app, bob)
    client.post(
        PLAY_EVENTS, json={"events": [{"event_id": "same"}]}, headers=alice_device["headers"]
    )

    seen_by_bob = client.get(f"{PLAY_EVENTS}?since=0", headers=bob_device["headers"]).json()
    assert seen_by_bob["events"] == []
    # The same event id is a different event for another user.
    bob_post = client.post(
        PLAY_EVENTS, json={"events": [{"event_id": "same"}]}, headers=bob_device["headers"]
    )
    assert bob_post.json() == {"inserted": 1, "skipped": 0}


def test_play_events_size_and_count_limits(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    headers = device["headers"]

    too_big = {"event_id": "big", "blob": "x" * 17000}
    assert client.post(PLAY_EVENTS, json={"events": [too_big]}, headers=headers).status_code == 400
    fits = {"event_id": "fits", "blob": "x" * 15000}
    assert client.post(PLAY_EVENTS, json={"events": [fits]}, headers=headers).status_code == 200

    many = [{"event_id": f"m{index}"} for index in range(1001)]
    assert client.post(PLAY_EVENTS, json={"events": many}, headers=headers).status_code == 400
    assert client.post(PLAY_EVENTS, json={"events": [{}]}, headers=headers).status_code == 400
    assert client.post(PLAY_EVENTS, json={"events": "x"}, headers=headers).status_code == 400


# -- playlists ----------------------------------------------------------------------------


def test_playlist_revisions_and_conflicts(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device_a = make_device(app, alice, name="A")
    device_b = make_device(app, alice, name="B")
    item = _item(app, alice)
    url = f"{PLAYLISTS}/pl-1"

    created = client.put(
        url,
        json={"name": "Mix", "entries": [{"item_id": item}], "base_revision": None},
        headers=device_a["headers"],
    )
    assert created.status_code == 200
    assert created.json()["revision"] == 1
    assert created.json()["entries"] == [{"item_id": item}]

    # Device B updates from revision 1.
    updated = client.put(
        url,
        json={"name": "Mix 2", "entries": [], "base_revision": 1},
        headers=device_b["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert updated.json()["updated_by_device_id"] == device_b["device_id"]

    # Device A still believes revision 1: a conflict that names the current revision.
    stale = client.put(
        url,
        json={"name": "Mine", "entries": [], "base_revision": 1},
        headers=device_a["headers"],
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "conflict"
    assert "current revision 2" in stale.json()["error"]["message"]

    # Creating over an existing playlist without a base is also a conflict.
    recreate = client.put(
        url,
        json={"name": "Again", "entries": [], "base_revision": None},
        headers=device_a["headers"],
    )
    assert recreate.status_code == 409
    assert "current revision 2" in recreate.json()["error"]["message"]

    listing = client.get(PLAYLISTS, headers=device_a["headers"]).json()["playlists"]
    assert listing == [
        {
            "playlist_id": "pl-1",
            "name": "Mix 2",
            "revision": 2,
            "deleted": False,
            "updated_at_utc": listing[0]["updated_at_utc"],
            "updated_by_device_id": device_b["device_id"],
        }
    ]
    one = client.get(url, headers=device_a["headers"]).json()
    assert one["name"] == "Mix 2"
    assert one["entries"] == []

    assert _journal(app, alice, "playlist") == [
        {"playlist_id": "pl-1", "revision": 1, "deleted": False},
        {"playlist_id": "pl-1", "revision": 2, "deleted": False},
    ]


def test_playlist_delete_is_a_tombstone_with_revision(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    headers = device["headers"]
    url = f"{PLAYLISTS}/pl-2"
    client.put(url, json={"name": "Gone", "entries": [], "base_revision": None}, headers=headers)

    assert client.delete(url, headers=headers).status_code == 400  # base_revision is required
    assert client.delete(f"{url}?base_revision=5", headers=headers).status_code == 409
    deleted = client.delete(f"{url}?base_revision=1", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["revision"] == 2
    assert deleted.json()["deleted"] is True

    listing = client.get(PLAYLISTS, headers=headers).json()["playlists"]
    assert [(p["playlist_id"], p["deleted"], p["revision"]) for p in listing] == [("pl-2", True, 2)]
    assert client.get(url, headers=headers).json()["deleted"] is True

    # A later write from revision 2 brings the playlist back.
    revived = client.put(
        url, json={"name": "Back", "entries": [], "base_revision": 2}, headers=headers
    )
    assert revived.json()["revision"] == 3
    assert client.get(url, headers=headers).json()["deleted"] is False
    assert [p["deleted"] for p in _journal(app, alice, "playlist")] == [False, True, False]


def test_playlist_is_private_and_validated(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    bob = make_user(app, "bob")
    alice_device = make_device(app, alice)
    bob_device = make_device(app, bob)
    client.put(
        f"{PLAYLISTS}/shared",
        json={"name": "Alice", "entries": [], "base_revision": None},
        headers=alice_device["headers"],
    )

    assert client.get(f"{PLAYLISTS}/shared", headers=bob_device["headers"]).status_code == 404
    assert client.get(f"{PLAYLISTS}", headers=bob_device["headers"]).json() == {"playlists": []}
    # Bob's own playlist with the same id does not touch Alice's.
    bob_put = client.put(
        f"{PLAYLISTS}/shared",
        json={"name": "Bob", "entries": [], "base_revision": None},
        headers=bob_device["headers"],
    )
    assert bob_put.json()["revision"] == 1
    assert client.get(f"{PLAYLISTS}/shared", headers=alice_device["headers"]).json()["name"] == (
        "Alice"
    )

    bad_name = {"name": "", "entries": [], "base_revision": None}
    assert (
        client.put(f"{PLAYLISTS}/x1", json=bad_name, headers=alice_device["headers"]).status_code
        == 400
    )
    bad_entries = {"name": "n", "entries": "nope", "base_revision": None}
    assert (
        client.put(f"{PLAYLISTS}/x2", json=bad_entries, headers=alice_device["headers"]).status_code
        == 400
    )
    too_many = {"name": "n", "entries": [{}] * 20001, "base_revision": None}
    assert (
        client.put(f"{PLAYLISTS}/x3", json=too_many, headers=alice_device["headers"]).status_code
        == 400
    )
    bad_base = {"name": "n", "entries": [], "base_revision": "1"}
    assert (
        client.put(f"{PLAYLISTS}/x4", json=bad_base, headers=alice_device["headers"]).status_code
        == 400
    )
    bad_id = {"name": "n", "entries": [], "base_revision": None}
    assert (
        client.put(f"{PLAYLISTS}/bad.id", json=bad_id, headers=alice_device["headers"]).status_code
        == 400
    )


# -- track data --------------------------------------------------------------------------


def test_track_data_layers_replace_and_delete(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    headers = device["headers"]
    item = _item(app, alice)
    url = f"{TRACK_DATA}/{item}"

    empty = client.get(url, headers=headers)
    assert empty.json() == {"item_id": item, "layers": {}}

    put = client.put(
        url,
        json={"analysis": {"bpm": 120}, "loudness": {"lufs": -14.2}},
        headers=headers,
    )
    assert put.status_code == 200
    assert put.json() == {
        "item_id": item,
        "layers": {"analysis": {"bpm": 120}, "loudness": {"lufs": -14.2}},
    }

    # A layer that is not sent keeps its value; null deletes its layer.
    client.put(url, json={"corrections": {"title": "T"}, "loudness": None}, headers=headers)
    layers = client.get(url, headers=headers).json()["layers"]
    assert layers == {"analysis": {"bpm": 120}, "corrections": {"title": "T"}}

    assert _journal(app, alice, "track_data") == [
        {"item_id": item, "layers": ["analysis", "loudness"]},
        {"item_id": item, "layers": ["corrections", "loudness"]},
    ]
    assert client.put(url, json={"unknown": {}}, headers=headers).status_code == 400
    assert client.put(url, json={"analysis": "x" * 70000}, headers=headers).status_code == 400


def test_track_data_is_private_to_the_owner(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    bob = make_user(app, "bob")
    alice_device = make_device(app, alice)
    bob_device = make_device(app, bob)
    item = _item(app, alice)
    client.put(
        f"{TRACK_DATA}/{item}", json={"loudness": {"lufs": -9}}, headers=alice_device["headers"]
    )

    assert client.get(f"{TRACK_DATA}/{item}", headers=bob_device["headers"]).status_code == 404
    assert (
        client.put(
            f"{TRACK_DATA}/{item}", json={"loudness": None}, headers=bob_device["headers"]
        ).status_code
        == 404
    )
    assert (
        client.get(f"{TRACK_DATA}/{new_id()}", headers=alice_device["headers"]).status_code == 404
    )
    still = client.get(f"{TRACK_DATA}/{item}", headers=alice_device["headers"]).json()
    assert still["layers"] == {"loudness": {"lufs": -9}}


# -- synced settings ---------------------------------------------------------------------


def test_settings_round_trip_between_devices(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device_a = make_device(app, alice, name="A")
    device_b = make_device(app, alice, name="B")

    put = client.put(
        SETTINGS,
        json={"ui.theme": "dark", "player/volume": 0.5, "x_1": [1, 2]},
        headers=device_a["headers"],
    )
    expected = {"ui.theme": "dark", "player/volume": 0.5, "x_1": [1, 2]}
    assert put.json() == {"settings": expected}
    assert client.get(SETTINGS, headers=device_b["headers"]).json() == {"settings": expected}

    client.put(SETTINGS, json={"ui.theme": None}, headers=device_b["headers"])
    del expected["ui.theme"]
    assert client.get(SETTINGS, headers=device_a["headers"]).json() == {"settings": expected}
    assert _journal(app, alice, "settings") == [
        {"keys": ["player/volume", "ui.theme", "x_1"]},
        {"keys": ["ui.theme"]},
    ]


def test_settings_limits_and_key_rules(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    headers = make_device(app, alice)["headers"]

    for bad_key in ("Bad", "has space", "", "a" * 101):
        response = client.put(SETTINGS, json={bad_key: 1}, headers=headers)
        assert response.status_code == 400, bad_key
    assert client.put(SETTINGS, json={"big": "x" * 17000}, headers=headers).status_code == 400
    too_many = {f"k.{index}": 1 for index in range(201)}
    assert client.put(SETTINGS, json=too_many, headers=headers).status_code == 400
    assert client.get(SETTINGS, headers=headers).json() == {"settings": {}}


# -- item loudness -----------------------------------------------------------------------


def test_item_carries_loudness_after_a_put(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    headers = device["headers"]
    item = _item(app, alice, "one.flac")
    other = _item(app, alice, "two.flac")

    assert client.get(f"/api/v1/items/{item}", headers=headers).json()["loudness"] is None

    client.put(f"{TRACK_DATA}/{item}", json={"loudness": {"lufs": -14.0}}, headers=headers)
    assert client.get(f"/api/v1/items/{item}", headers=headers).json()["loudness"] == {
        "lufs": -14.0
    }
    listed = client.get("/api/v1/items", headers=headers).json()["items"]
    loudness = {entry["item_id"]: entry["loudness"] for entry in listed}
    assert loudness == {item: {"lufs": -14.0}, other: None}


# -- authentication -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", PLAY_EVENTS),
        ("GET", PLAY_EVENTS),
        ("GET", PLAYLISTS),
        ("GET", f"{PLAYLISTS}/pl-1"),
        ("PUT", f"{PLAYLISTS}/pl-1"),
        ("DELETE", f"{PLAYLISTS}/pl-1?base_revision=1"),
        ("GET", f"{TRACK_DATA}/abc"),
        ("PUT", f"{TRACK_DATA}/abc"),
        ("GET", SETTINGS),
        ("PUT", SETTINGS),
    ],
)
def test_every_records_route_needs_a_device_token(
    client: TestClient, make_user: MakeUser, app: Starlette, method: str, path: str
) -> None:
    make_user(app, "alice")
    assert client.request(method, path, json={}).status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.request(method, path, json={}, headers=bad).status_code == 401


def test_records_routes_write_their_journal_kinds(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    headers = make_device(app, alice)["headers"]
    item = _item(app, alice)
    client.post(PLAY_EVENTS, json={"events": [{"event_id": "k"}]}, headers=headers)
    client.put(
        f"{PLAYLISTS}/pl-k",
        json={"name": "k", "entries": [], "base_revision": None},
        headers=headers,
    )
    client.put(f"{TRACK_DATA}/{item}", json={"analysis": {}}, headers=headers)
    client.put(SETTINGS, json={"k": 1}, headers=headers)
    rows = (
        app.state.db.conn()
        .execute(
            "SELECT kind, item_id FROM journal WHERE user_id = ? ORDER BY seq", (alice["user_id"],)
        )
        .fetchall()
    )
    assert [(row["kind"], row["item_id"]) for row in rows] == [
        ("added", item),
        ("play_events", None),
        ("playlist", None),
        ("track_data", item),
        ("settings", None),
    ]
